import datetime as dt
import io
import json
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch
import pytest
from studio.storage import Store, StudioError, protect, room_code
from studio.device import Device, has_identity
from studio.engine import Engine
from studio.integrations import Integrations, json_path


def literal(value): return {'op': 'literal', 'value': value}


@pytest.fixture
def store(tmp_path): return Store(tmp_path)


def test_dpapi_roundtrip_and_no_plaintext(store):
    store.secret_set('token', 'example-secret-never-a-real-account')
    assert store.token() == 'example-secret-never-a-real-account'
    assert b'example-secret' not in (store.root / 'vault.bin').read_bytes()


def test_store_preserves_other_secret_keys(store):
    store.secret_set('token', 'sample')
    store.secret_set('connections', {'sensor': {'kind': 'http'}})
    assert store.token() == 'sample'


def test_room_validation():
    assert room_code(' H00-00-00-0000-00 ') == 'H00-00-00-0000-00'
    with pytest.raises(StudioError): room_code('https://example.test')


def test_identity_exact_only():
    assert has_identity({'nested': {'code': 'my-room'}}, 'my-room')
    assert not has_identity({'code': 'my-room-extra'}, 'my-room')
    assert not has_identity({'code': ''}, '')


def test_device_filters_private_fields(store):
    store.update(room='test-room')
    device = Device(store)
    device.request = Mock(return_value={'data': {'aircon': {'code': 'test-room', 'power': 1, 'flap': 'N', 'wallet': {'balance': 5}, 'account': 'private', 'room': 'private'}}})
    result = device.status()
    assert result['identity_verified']
    assert 'wallet' not in result and 'room' not in result and 'account' not in result


def test_mismatched_room_blocks_control(store):
    store.update(room='test-room')
    device = Device(store)
    device.request = Mock(return_value={'data': {'aircon': {'code': 'other-room', 'power': 0}}})
    with pytest.raises(StudioError): device.control('power', '1')
    device.request.assert_called_once_with('/me', token=None)


def test_unlearned_values_blocked(store):
    device = Device(store)
    device.request = Mock()
    with pytest.raises(StudioError): device.control('mode', 'GUESS')
    device.request.assert_not_called()


def test_demo_does_not_read_credentials_or_network(store):
    device = Device(store, True)
    store.token = Mock(side_effect=AssertionError('No credentials in demo'))
    assert device.control('flap', 'S')['flap'] == 'S'


def test_form_encoding_and_business_error(store):
    device = Device(store)
    device.opener = Mock()
    device.opener.open.return_value = io.BytesIO(b'{"meta":{"status":200}}')
    device.request('/v2/ac/control', {'flap': 'S'}, token='example-token')
    request = device.opener.open.call_args.args[0]
    assert request.data == b'flap=S'
    device.opener.open.return_value = io.BytesIO(b'{"meta":{"status":402}}')
    with pytest.raises(StudioError): device.request('/me', token='example-token')


def test_json_path():
    assert json_path({'items': [{'temperature': 26.5}]}, 'items.0.temperature') == 26.5
    with pytest.raises(StudioError): json_path({}, 'missing.path')


def engine(store):
    device = Mock()
    device.status.return_value = {'power': 1, 'flap': 'N'}
    integrations = Integrations(store, True)
    events = []
    return Engine(device, integrations, events.append), device, events


def test_dry_run_never_controls_or_calls_external(store):
    runner, device, events = engine(store)
    runner.integrations.http = Mock(side_effect=AssertionError('No HTTP in dry run'))
    runner.run([{'op': 'control', 'field': 'power', 'value': literal('0')}, {'op': 'set', 'name': 'sensor', 'value': {'op': 'http', 'connection': 'x', 'path': 'temperature'}}], True)
    device.control.assert_not_called()
    assert runner.variables['sensor'] == 26.5
    assert not any(e['kind'] == 'error' for e in events)


def test_cancellation_interrupts_long_wait(store):
    runner, device, events = engine(store)
    thread = threading.Thread(target=runner.run, args=([{'op': 'wait', 'seconds': literal(7200)}, {'op': 'control', 'field': 'power', 'value': literal('0')}], False))
    thread.start()
    time.sleep(.05)
    runner.cancel.set()
    thread.join(1)
    assert not thread.is_alive()
    device.control.assert_not_called()


def test_preflight_catches_unknown_later_block_before_actuation(store):
    runner, device, events = engine(store)
    runner.run([{'op': 'control', 'field': 'power', 'value': literal('0')}, {'op': 'shell'}], False)
    device.control.assert_not_called()
    assert any(e['kind'] == 'error' for e in events)


def test_if_variables_and_loops(store):
    runner, device, events = engine(store)
    runner.run([{'op': 'set', 'name': 'n', 'value': literal(26)}, {'op': 'if', 'branches': [{'condition': {'op': 'compare', 'operator': 'GT', 'a': {'op': 'var', 'name': 'n'}, 'b': literal(25)}, 'body': [{'op': 'repeat', 'count': literal(2), 'body': [{'op': 'control', 'field': 'flap', 'value': literal('S')}]}]}]}], False)
    assert device.control.call_count == 2


def test_try_catch_and_once_day(store):
    runner, device, events = engine(store)
    device.status.side_effect = StudioError('offline')
    body = [{'op': 'once_day', 'key': 'job', 'body': [{'op': 'log', 'value': literal('once')}]}]
    runner.run([{'op': 'try', 'body': [{'op': 'refresh'}], 'catch': [{'op': 'log', 'value': literal('caught')}]}, *body, *body], False)
    assert sum(e.get('text') == 'once' for e in events) == 1
    assert any(e.get('text') == 'caught' for e in events)


def test_local_http_json_and_network(store):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b'{"temperature":26.5}')
        def do_HEAD(self): self.send_response(200); self.end_headers()
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    store.secret_set('connections', {'sensor': {'kind': 'http', 'url': f'http://127.0.0.1:{server.server_port}'}})
    try:
        connectors = Integrations(store)
        assert connectors.http('sensor', 'temperature') == 26.5
        assert connectors.network('sensor') is True
        assert connectors.net_time('sensor') > 0
    finally:
        server.shutdown(); server.server_close()


def test_ics_recurrence_expansion(store):
    now = dt.datetime.now(dt.timezone.utc)
    start = now + dt.timedelta(minutes=5)
    data = ('BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:test\r\nDTSTART:'+start.strftime('%Y%m%dT%H%M%SZ')+'\r\nDTEND:'+(start+dt.timedelta(minutes=50)).strftime('%Y%m%dT%H%M%SZ')+'\r\nRRULE:FREQ=DAILY;COUNT=3\r\nSUMMARY:Class\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n').encode()
    store.secret_set('connections', {'calendar': {'kind': 'calendar', 'url': 'https://example.test/calendar.ics'}})
    with patch('studio.integrations.fetch', return_value=(data, None)):
        result = Integrations(store).calendar('calendar', 72, 'Class')
    assert len(result) == 3




def test_frontend_catalogue_compiles(store):
    path = Path(__file__).resolve().parents[1] / '.demo-data' / 'smoke.json'
    if not path.exists(): pytest.skip('Run GUI smoke first')
    results = json.loads(path.read_text(encoding='utf-8'))
    assert results['ready'] and results['blockly']
    assert results['templates'] == {}
    assert results['blocks'] >= 90
    assert all(item['ok'] for item in results['catalogue'])
    assert all(item.get('compiled', False) for item in results['catalogue'])
    for item in results['catalogue']:
        runner, _, _ = engine(store)
        runner.preflight(item['program'])


def test_mqtt_reader_subscribes_and_returns_json(store):
    store.secret_set('connections', {'sensor': {'kind': 'mqtt', 'host': 'localhost', 'port': 1883, 'topic': 'test/temperature'}})
    client = Mock()
    def start():
        client.on_connect(client, None, None, 0, None)
        client.on_message(client, None, type('Message', (), {'payload': b'{"temperature":25.5}'})())
    client.loop_start.side_effect = start
    with patch('paho.mqtt.client.Client', return_value=client):
        assert Integrations(store).mqtt('sensor', 'temperature', threading.Event()) == 25.5
    client.subscribe.assert_called_once_with('test/temperature')
    client.disconnect.assert_called_once()



def test_bridge_mqtt_defaults_and_script_export_privacy(store, tmp_path):
    from studio.bridge import Bridge
    bridge = Bridge(store, Path(__file__).resolve().parents[1], demo=True)
    bridge.handle('save_connection', {'name': 'sensor', 'kind': 'mqtt', 'host': 'localhost', 'topic': 'test', 'port': '', 'token': 'sample-password'})
    assert store.secrets()['connections']['sensor']['port'] == 1883
    store.secret_set('token', 'sample-private-token')
    output = tmp_path / 'export.aircon.json'
    with pytest.raises(StudioError): bridge.handle('export_script', {'filename': str(output), 'workspace': {'text': 'sample-private-token'}})
    bridge.handle('export_script', {'filename': str(output), 'workspace': {'blocks': {}}})
    assert 'sample-password' not in output.read_text()
    assert 'connections' not in output.read_text()


def test_invalid_duration_finishes_without_actuation(store):
    runner, device, events = engine(store)
    runner.run([{'op': 'control', 'field': 'power', 'value': literal('0')}], False, float('nan'))
    device.control.assert_not_called()
    assert events[-1]['kind'] == 'finished'
    assert any(e['kind'] == 'error' for e in events)


def test_direct_token_connects_without_room_or_capture(store):
    from studio.bridge import Bridge
    bridge = Bridge(store, Path(__file__).resolve().parents[1])
    bridge.device.request = Mock(return_value={'data': {'aircon': {'aircon_code': 'H00-00-00-0000-00', 'power': 1, 'flap': 'N'}}})
    bridge.capture.prepare = Mock(side_effect=AssertionError('No capture needed'))
    bridge.capture.start = Mock(side_effect=AssertionError('No capture needed'))
    result = bridge.handle('manual_token', {'token': 'bearer sample-token'})
    assert store.token() == 'sample-token'
    assert store.config()['room'] == 'H00-00-00-0000-00'
    assert result['status']['identity_verified']
    assert 'token' not in result and 'token' not in result['settings']
    assert bridge.handle('show_token', {}) == {'token': 'sample-token', 'room': 'H00-00-00-0000-00'}


def test_failed_direct_token_preserves_previous_account(store):
    from studio.bridge import Bridge
    store.update(room='H00-00-00-0000-00')
    store.secret_set('token', 'previous-sample')
    bridge = Bridge(store, Path(__file__).resolve().parents[1])
    bridge.device.request = Mock(side_effect=StudioError('授权失败'))
    with pytest.raises(StudioError): bridge.handle('manual_token', {'token': 'invalid-sample'})
    assert store.token() == 'previous-sample'
    assert store.config()['room'] == 'H00-00-00-0000-00'


def test_direct_token_rejects_unbound_or_mismatched_room(store):
    from studio.bridge import Bridge
    bridge = Bridge(store, Path(__file__).resolve().parents[1])
    bridge.device.request = Mock(return_value={'data': {'aircon': None}})
    with pytest.raises(StudioError): bridge.handle('manual_token', {'token': 'sample'})
    bridge.device.request.return_value = {'data': {'aircon': {'aircon_code': 'H00-00-00-0000-00', 'power': 1}}}
    with pytest.raises(StudioError): bridge.handle('manual_token', {'token': 'sample', 'room': 'H99-00-00-0000-00'})
    assert not store.token()


def test_copy_token_uses_native_clipboard_without_echoing_reply(store):
    from studio.bridge import Bridge
    bridge = Bridge(store, Path(__file__).resolve().parents[1])
    store.secret_set('token', 'sample-private-token')
    clipboard = Mock()
    replies = []
    bridge.reply.connect(replies.append)
    with patch('PySide6.QtGui.QGuiApplication.clipboard', return_value=clipboard):
        bridge.request('copy-test', 'copy_token', '{}')
    clipboard.setText.assert_called_once_with('sample-private-token')
    assert json.loads(replies[-1])['data'] == {'copied': True}
    assert 'sample-private-token' not in replies[-1]


def test_captured_token_is_only_revealed_by_explicit_endpoint(store):
    from studio.bridge import Bridge
    bridge = Bridge(store, Path(__file__).resolve().parents[1])
    bridge.capture.status = Mock(return_value={'running': True, 'ready': True})
    bridge.capture.candidate = Mock(return_value='captured-sample')
    bridge.capture.stop = Mock()
    bridge.device.status = Mock(return_value={'power': 1, 'identity_verified': True})
    result = bridge.handle('poll', {})
    assert result['captured']['identity_verified']
    assert 'captured-sample' not in json.dumps(result)
    bridge.capture.stop.assert_called_once()
    assert bridge.handle('show_token', {})['token'] == 'captured-sample'
