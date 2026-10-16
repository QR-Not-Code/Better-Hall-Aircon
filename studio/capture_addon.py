"""Runs only in the child capture engine. No unredacted traffic is persisted."""
import datetime
import json
from pathlib import Path
from mitmproxy import ctx, http
from studio.storage import protect, atomic_write


class Capture:
    def root(self):
        return Path(ctx.options.confdir)

    def event(self, kind, **data):
        path = self.root() / 'events.jsonl'
        if path.exists() and path.stat().st_size > 200000:
            path.write_text('', encoding='utf-8')
        with path.open('a', encoding='utf-8') as f:
            f.write(json.dumps({'kind': kind, 'time': datetime.datetime.now(datetime.timezone.utc).isoformat(), **data}) + '\n')

    def running(self):
        atomic_write(self.root() / 'ready', 'ready')

    def client_connected(self, client):
        atomic_write(self.root() / 'phone-seen', str(datetime.datetime.now().timestamp()))

    def request(self, flow: http.HTTPFlow):
        if flow.request.pretty_host != 'apintu-prod.daikinpayu.com':
            return
        auth = flow.request.headers.get('authorization', '')
        if auth.lower().startswith('bearer '):
            token = auth[7:].strip()
            if token and not any(c.isspace() for c in token):
                atomic_write(self.root() / 'candidate.bin', protect(token.encode()))
        self.event('api', method=flow.request.method, path=flow.request.path.split('?')[0])

    def response(self, flow: http.HTTPFlow):
        if flow.request.pretty_host != 'apintu-prod.daikinpayu.com' or flow.request.method != 'POST' or flow.request.path.split('?')[0] != '/v2/ac/control':
            return
        try:
            response = flow.response.json()
            if flow.response.status_code != 200 or str(response.get('meta', {}).get('status', 200)) != '200' or response.get('success') is False:
                return
            fields = dict(flow.request.urlencoded_form)
            if not fields:
                fields = json.loads(flow.request.get_text())
            safe = {k: str(v) for k, v in fields.items() if k in ('power', 'flap', 'setpoint', 'fanstep', 'mode') and isinstance(v, (str, int, float)) and len(str(v)) <= 16}
            self.event('learn', fields=safe)
        except (ValueError, AttributeError):
            pass

    def tls_failed_client(self, data):
        self.event('tls_error', host=data.context.server.address[0] if data.context.server.address else '')


addons = [Capture()]
