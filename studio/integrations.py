import datetime as dt
import json
import queue
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo
from .storage import StudioError


def json_path(data, path):
    if not path or path == '$':
        return data
    for part in path.removeprefix('$.').split('.'):
        try:
            data = data[int(part)] if isinstance(data, list) else data[part]
        except (KeyError, IndexError, TypeError, ValueError):
            raise StudioError('JSON 路径不存在，请核对传感器返回值。') from None
    return data


def fetch(url, token='', body=None, method='GET', limit=2_000_000):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise StudioError('连接地址必须是 HTTP(S)，且不能在 URL 中包含账号密码。')
    headers = {'Accept': 'application/json, text/calendar, */*', 'User-Agent': 'HallAirconStudio/1.0'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if body is not None:
        headers['Content-Type'] = 'application/json'
    try:
        # Never forward Authorization through redirects to another host.
        from .device import NoRedirect
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), headers=headers, method=method), timeout=10) as response:
            data = response.read(limit + 1)
            date = response.headers.get('Date')
        if len(data) > limit:
            raise StudioError('外部接口响应超过大小限制。')
        return data, date
    except (urllib.error.URLError, OSError):
        raise StudioError('外部接口连接失败。请检查地址、网络和凭据；没有记录完整 URL 或凭据。') from None


class Integrations:
    def __init__(self, store, demo=False):
        self.store, self.demo = store, demo

    def profile(self, name, kind=None):
        p = self.store.secrets().get('connections', {}).get(name)
        if not p or (kind and p.get('kind') != kind):
            raise StudioError(f'请先在连接器页面配置「{name}」。')
        return p

    def now(self):
        try:
            return dt.datetime.now(ZoneInfo(self.store.config().get('timezone', 'Asia/Singapore')))
        except Exception:
            raise StudioError('时区名称无效，例如 Asia/Singapore 或 Asia/Shanghai。') from None

    def http(self, name, path=''):
        if self.demo:
            return json_path({'temperature': 26.5, 'humidity': 65, 'online': True}, path)
        p = self.profile(name, 'http')
        raw, _ = fetch(p['url'], p.get('token', ''))
        try:
            return json_path(json.loads(raw), path)
        except ValueError:
            raise StudioError('外部接口没有返回 JSON。') from None

    def network(self, name):
        if self.demo:
            return True
        p = self.profile(name)
        try:
            fetch(p['url'], p.get('token', ''), method='HEAD')
            return True
        except StudioError:
            return False

    def net_time(self, name):
        if self.demo:
            return self.now().timestamp()
        from email.utils import parsedate_to_datetime
        p = self.profile(name, 'http')
        _, date = fetch(p['url'], p.get('token', ''), method='HEAD')
        if not date:
            raise StudioError('该接口没有返回 HTTP Date 时间头。')
        try:
            return parsedate_to_datetime(date).timestamp()
        except (ValueError, TypeError):
            raise StudioError('HTTP Date 格式无法识别。') from None

    def calendar(self, name, hours=24, keyword=''):
        if self.demo:
            return [{'title': '示例课程', 'start': self.now().isoformat()}]
        import icalendar
        import recurring_ical_events
        p = self.profile(name, 'calendar')
        raw, _ = fetch(p['url'], p.get('token', ''))
        now = self.now()
        try:
            cal = icalendar.Calendar.from_ical(raw)
            events = recurring_ical_events.of(cal).between(now, now + dt.timedelta(hours=min(max(float(hours), 1), 720)))
            result = []
            for event in events[:1000]:
                title = str(event.get('SUMMARY', ''))
                if keyword.casefold() in title.casefold():
                    result.append({'title': title, 'start': event.decoded('DTSTART').isoformat()})
            return result
        except Exception:
            raise StudioError('日历解析失败，请检查 ICS 地址、时区和事件格式。') from None

    def mqtt(self, name, path, cancel):
        if self.demo:
            return json_path({'temperature': 26.5}, path)
        import paho.mqtt.client as mqtt
        p = self.profile(name, 'mqtt')
        messages = queue.Queue(maxsize=1)
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if p.get('username'):
            client.username_pw_set(p['username'], p.get('token', ''))
        if p.get('tls'):
            client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
        client.on_connect = lambda c, u, flags, rc, props: c.subscribe(p['topic']) if rc == 0 else None
        def receive(c, u, message):
            if len(message.payload) <= 100000 and messages.empty():
                messages.put_nowait(message.payload)
        client.on_message = receive
        try:
            client.connect_async(p['host'], int(p.get('port', 8883 if p.get('tls') else 1883)), 30)
            client.loop_start()
            deadline = time.monotonic() + 20
            while not cancel.is_set() and time.monotonic() < deadline:
                try:
                    raw = messages.get(timeout=.3)
                    return json_path(json.loads(raw), path)
                except queue.Empty:
                    pass
            raise StudioError('等待 MQTT 消息超时或已停止。请检查主题和 retained 消息。')
        except (OSError, ValueError):
            raise StudioError('MQTT 连接或 JSON 消息解析失败。') from None
        finally:
            client.disconnect()
            client.loop_stop()

    def request(self, name, method='GET', body=None, path=''):
        if method not in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD'):
            raise StudioError('HTTP 方法无效。')
        if self.demo: return {'demo': True, 'method': method, 'data': body}
        if method in ('GET', 'HEAD'): body = None
        profile = self.profile(name, 'http')
        raw, _ = fetch(profile['url'], profile.get('token', ''), body, method)
        if not raw: return None
        try: return json_path(json.loads(raw), path)
        except ValueError: raise StudioError('接口返回的内容不是 JSON。') from None
