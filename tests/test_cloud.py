import copy
import json
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch
import pytest
import yaml
from cryptography.fernet import Fernet
from studio.cloud_store import CloudStore, GitHubCheckpoint
from studio.cloud_vm import CloudVM, new_state, CheckpointFailure, ControlUncertain
from studio.cloud_runner import fingerprint
from studio.cloud_export import analyse, export_bundle, workflow
from studio.device import Device
from studio.engine import Engine
from studio.integrations import Integrations
from studio.storage import Store, StudioError


ROOT = Path(__file__).resolve().parents[1]
def lit(value): return {'op': 'literal', 'value': value}
def var(name): return {'op': 'var', 'name': name}
def control(field, value): return {'op': 'control', 'field': field, 'value': lit(value)}
def compare(name, value): return {'op': 'compare', 'operator': 'EQ', 'a': var(name), 'b': lit(value)}
def branch(condition, body): return {'op': 'if', 'branches': [{'condition': condition, 'body': body}], 'else': []}


class Clock:
    now = 1_800_000_000.0
    def advance(self, seconds): self.now += seconds


@pytest.fixture
def cloud():
    clock = Clock()
    with patch('time.time', side_effect=lambda: clock.now), patch('time.monotonic', side_effect=lambda: clock.now - 1_700_000_000):
        state = new_state('test')
        env = {'AIRCON_TOKEN': 'dummy-cloud-credential', 'AIRCON_EXPECTED_ROOM': 'H00-00-00-0000-00'}
        device = Device(CloudStore({}, state, env), True)
        device.demo_state['power'] = 0
        device.control = Mock(wraps=device.control)
        snapshots = []
        def resume(program, saved=None, persist=None):
            current = copy.deepcopy(saved if saved is not None else state)
            current['fingerprint'] = fingerprint(program)
            current['active'] = True
            store = CloudStore({}, current, env)
            engine = Engine(device, Integrations(store, True))
            engine.script_id = 'script'
            vm = CloudVM(program, engine, current, persist or snapshots.append)
            return vm
        yield clock, device, snapshots, resume


def test_wait_two_hours_resumes_after_wait_without_repeating_power_on(cloud):
    clock, device, snapshots, resume = cloud
    program = [control('power', '1'), {'op': 'wait', 'seconds': lit(7200)}, control('power', '0')]
    first = resume(program)
    assert first.run() == 'checkpointed'
    assert device.demo_state['power'] == 1 and device.control.call_count == 1
    clock.advance(3600)
    assert resume(program, snapshots[-1]).run() == 'waiting'
    assert device.control.call_count == 1
    clock.advance(3601)
    final = resume(program, snapshots[-1])
    assert final.run() == 'completed'
    assert device.demo_state['power'] == 0 and device.control.call_count == 2


def test_nested_loops_continue_break_and_else_across_runner_restarts(cloud):
    clock, device, snapshots, resume = cloud
    program = [{'op': 'set', 'name': 'total', 'value': lit(0)},
        {'op': 'repeat', 'count': lit(2), 'body': [
            {'op': 'range_for', 'name': 'n', 'start': lit(0), 'end': lit(5), 'step': lit(1), 'body': [
                branch(compare('n', 1), [{'op': 'continue'}]),
                branch(compare('n', 3), [{'op': 'break'}]),
                {'op': 'change_var', 'name': 'total', 'value': lit(1)},
                {'op': 'wait', 'seconds': lit(1)}], 'else': [{'op': 'set', 'name': 'wrong', 'value': lit(True)}]}],
         'else': [{'op': 'set', 'name': 'complete', 'value': lit(True)}]}]
    vm = resume(program)
    for _ in range(20):
        result = vm.run(max_steps=12)
        if result == 'completed': break
        clock.advance(300)
        vm = resume(program, snapshots[-1])
    assert vm.state['completed']
    assert vm.engine.variables['total'] == 4
    assert vm.engine.variables['complete'] is True and 'wrong' not in vm.engine.variables


def test_try_catch_finally_and_retry_survive_checkpoints(cloud):
    clock, device, snapshots, resume = cloud
    program = [{'op': 'set', 'name': 'attempt', 'value': lit(0)},
        {'op': 'retry', 'attempts': 2, 'interval': 5, 'body': [
            {'op': 'change_var', 'name': 'attempt', 'value': lit(1)},
            branch(compare('attempt', 1), [{'op': 'raise', 'value': lit('retry me')}])]},
        {'op': 'try_finally', 'has_catch': True, 'body': [{'op': 'raise', 'value': lit('expected')}],
         'catch': [{'op': 'wait', 'seconds': lit(2)}, {'op': 'set', 'name': 'caught', 'value': lit(True)}],
         'finally': [{'op': 'set', 'name': 'cleaned', 'value': lit(True)}]}]
    vm = resume(program)
    for _ in range(10):
        if vm.run() == 'completed': break
        clock.advance(300)
        vm = resume(program, snapshots[-1])
    assert vm.engine.variables['attempt'] == 2
    assert vm.engine.variables['caught'] and vm.engine.variables['cleaned']


def test_finally_executes_on_continue_and_break_in_vm(cloud):
    _, _, _, resume = cloud
    program = [{'op': 'set', 'name': 'n', 'value': lit(0)},
        {'op': 'repeat', 'count': lit(2), 'body': [{'op': 'try_finally', 'body': [{'op': 'continue'}],
         'finally': [{'op': 'change_var', 'name': 'n', 'value': lit(1)}]}], 'else': []},
        {'op': 'forever', 'body': [{'op': 'try_finally', 'body': [{'op': 'break'}],
         'finally': [{'op': 'change_var', 'name': 'n', 'value': lit(1)}]}]}]
    vm = resume(program)
    assert vm.run() == 'completed' and vm.engine.variables['n'] == 3


def test_forever_bounded_batch_preserves_position_and_days_memory(cloud):
    clock, _, snapshots, resume = cloud
    program = [{'op': 'forever', 'body': [
        {'op': 'once_day', 'key': 'daily', 'body': [{'op': 'change_var', 'name': 'n', 'value': lit(1)}]},
        {'op': 'memory_set', 'name': 'key', 'value': lit(7)}, {'op': 'wait', 'seconds': lit(60)}]}]
    vm = resume(program)
    assert vm.run(max_steps=100) == 'checkpointed'
    clock.advance(300)
    vm = resume(program, snapshots[-1]); vm.run()
    assert vm.engine.variables['n'] == 1
    assert vm.engine.memory['key'] == 7
    assert vm.state['active'] is True


def test_observer_swing_baseline_and_stable_time_survive_restarts(cloud):
    clock, device, snapshots, resume = cloud
    program = [{'op': 'refresh'}, {'op': 'wait', 'seconds': lit(1)},
               {'op': 'set', 'name': 'changed', 'value': {'op': 'changed', 'id': 'watch', 'field': 'flap', 'target': 'S', 'source': 'suspected_external'}},
               {'op': 'set', 'name': 'stable', 'value': {'op': 'stable', 'field': 'power', 'seconds': lit(100)}}]
    vm = resume(program); vm.run()
    clock.advance(300); device.demo_state['flap'] = 'S'
    vm = resume(program, snapshots[-1]); vm.run()
    assert vm.engine.variables['changed'] is True and vm.engine.variables['stable'] is True


def test_wait_event_and_condition_resume_and_timeout(cloud):
    clock, device, snapshots, resume = cloud
    program = [{'op': 'refresh'}, {'op': 'wait_event', 'field': 'flap', 'source': 'suspected_external', 'timeout': lit(600),
        'name': 'event', 'body': [{'op': 'set', 'name': 'hit', 'value': lit(True)}], 'else': []},
        {'op': 'wait_until', 'condition': {'op': 'state_flag', 'field': 'power', 'target': '1'}, 'interval': 30}]
    vm = resume(program); vm.run()
    clock.advance(300); device.demo_state.update(flap='S', power=1)
    vm = resume(program, snapshots[-1]); assert vm.run() == 'completed'
    assert vm.engine.variables['event']['after'] == 'S' and vm.engine.variables['hit']


def test_checkpoint_failure_before_control_sends_no_command(cloud):
    _, device, _, resume = cloud
    def fail(state): raise OSError('disk or GitHub unavailable')
    vm = resume([control('power', '1')], persist=fail)
    with pytest.raises(CheckpointFailure): vm.run()
    device.control.assert_not_called()


def test_crash_after_command_reconciles_without_reposting(cloud):
    _, device, snapshots, resume = cloud
    class Crash(BaseException): pass
    def persist(state):
        if not state.get('pending_control') and device.control.call_count: raise Crash()
        snapshots.append(copy.deepcopy(state))
    program = [control('power', '1'), {'op': 'set', 'name': 'after', 'value': lit(True)}]
    with pytest.raises(Crash): resume(program, persist=persist).run()
    assert snapshots[-1]['pending_control'] and device.control.call_count == 1
    vm = resume(program, snapshots[-1]); vm.run()
    assert device.control.call_count == 1 and vm.engine.variables['after']


def test_unconfirmed_pending_control_pauses_without_auto_retry(cloud):
    _, device, _, resume = cloud
    program = [control('power', '1')]
    vm = resume(program)
    vm.state['pending_control'] = {'field': 'power', 'value': '1'}
    with pytest.raises(ControlUncertain): vm.run()
    assert vm.state['active'] is False
    device.control.assert_not_called()


def test_encrypted_github_checkpoint_roundtrip_and_conflict():
    key = Fernet.generate_key().decode()
    cp = GitHubCheckpoint('0123456789abcdef', {'GITHUB_TOKEN': 'dummy', 'GITHUB_REPOSITORY': 'test/repo', 'AIRCON_STATE_KEY': key})
    cp.branch_ready = True
    saved = {}
    def request(endpoint, method='GET', data=None, missing=False):
        if method == 'PUT': saved.update(data); return {'content': {'sha': 'new-sha'}}
        return {'sha': 'new-sha', 'content': saved['content']}
    cp.request = Mock(side_effect=request)
    cp.save({'active': True, 'variables': {'secret': 'private-value'}})
    assert 'private-value' not in saved['content']
    assert cp.load()['variables']['secret'] == 'private-value'
    cp.save({'active': False})
    assert saved['sha'] == 'new-sha'
    cp.request = Mock(side_effect=StudioError('conflict'))
    with pytest.raises(StudioError): cp.save({'active': False})


def test_cloud_store_never_uses_dpapi_or_persists_credentials():
    state = {}
    store = CloudStore({}, state, {'AIRCON_TOKEN': 'dummy', 'AIRCON_EXPECTED_ROOM': 'test-room', 'AIRCON_CONNECTIONS_JSON': '{}'})
    with patch('studio.storage.protect', side_effect=AssertionError('No DPAPI on cloud')):
        assert store.token() == 'dummy'
        store.secret_set('script_memory', {'x': {'n': 1}})
    assert 'dummy' not in json.dumps(state)
    with pytest.raises(StudioError): store.secret_set('token', 'other')


def test_export_compatibility_private_network_and_arbitrary_code(tmp_path):
    store = Store(tmp_path)
    store.secret_set('connections', {'sensor': {'kind': 'http', 'url': 'http://192.168.1.2/api'}})
    report = analyse({'program': [{'op': 'log', 'value': {'op': 'http', 'connection': 'sensor', 'path': ''}}]}, store)
    assert any('局域网' in error for error in report['errors'])
    report = analyse({'mode': 'code', 'code': 'result = 1', 'trusted_code': True, 'cloud_mode': 'resume'}, store)
    assert report['errors']
    assert not analyse({'mode': 'code', 'code': 'result = 1', 'trusted_code': True, 'cloud_mode': 'once'}, store)['errors']


def test_export_bundle_contains_workflow_and_runs_headless_dry(tmp_path):
    store = Store(tmp_path/'store')
    store.secret_set('token', 'private-token-never-export')
    store.update(room='H99-private-room-00')
    output = tmp_path/'actions.zip'
    data = {'id': 'script-test', 'name': 'Cloud test', 'program': [control('power', '1'), {'op': 'wait', 'seconds': lit(7200)}, control('power', '0')], 'cloud_mode': 'resume'}
    result = export_bundle(data, store, ROOT, output)
    target = tmp_path/'repo'
    with zipfile.ZipFile(output) as archive:
        for item in archive.infolist():
            content = archive.read(item)
            assert b'private-token-never-export' not in content and b'H99-private-room-00' not in content
            assert b'PySide6' not in content if item.filename.endswith('.py') else True
        yaml_text = archive.read('.github/workflows/aircon-'+result['identifier']+'.yml').decode()
        parsed = yaml.load(yaml_text, Loader=yaml.BaseLoader)
        assert parsed['on']['workflow_dispatch']['inputs']['command']['default'] == 'test'
        assert parsed['permissions']['contents'] == 'write'
        assert parsed['concurrency']['cancel-in-progress'] == 'false'
        archive.extractall(target)
    bundle = target/'aircon'/result['identifier']
    run = subprocess.run([sys.executable, str(bundle/'cloud_runner.py'), '--config', str(bundle/'script.json'), '--command', 'test'], capture_output=True, text=True, timeout=20)
    assert run.returncode == 0, run.stderr
    assert 'No device or connector request' in run.stdout
    assert not (bundle/'studio'/'bridge.py').exists()


def test_single_mode_has_no_schedule_and_export_blocks_hardcoded_secret(tmp_path):
    store = Store(tmp_path)
    store.secret_set('token', 'never-export-this-token')
    with pytest.raises(StudioError):
        export_bundle({'program': [{'op': 'log', 'value': lit('never-export-this-token')}], 'cloud_mode': 'once'}, store, ROOT, tmp_path/'bad.zip')
    parsed = yaml.load(workflow('0123456789abcdef', 'once', 5, 60), Loader=yaml.BaseLoader)
    assert 'schedule' not in parsed['on'] and parsed['permissions']['contents'] == 'read'
    assert parsed['jobs']['run']['timeout-minutes'] == '65'


def test_runner_activation_pause_reset_and_changed_program(tmp_path, monkeypatch):
    from studio.cloud_runner import main
    path = tmp_path/'script.json'
    config = {'identifier': '0123456789abcdef', 'cloud_mode': 'resume', 'device': {},
              'program': [{'op': 'wait', 'seconds': lit(3600)}, {'op': 'set', 'name': 'end', 'value': lit(True)}]}
    path.write_text(json.dumps(config), encoding='utf-8')
    saved = {}
    cp = Mock()
    cp.load.side_effect = lambda: copy.deepcopy(saved.get('state'))
    cp.save.side_effect = lambda state: saved.update(state=copy.deepcopy(state))
    created = []
    def device(store):
        value = Device(store, True)
        value.control = Mock(wraps=value.control)
        created.append(value)
        return value
    monkeypatch.setenv('AIRCON_TOKEN', 'dummy-account-token')
    monkeypatch.setenv('AIRCON_EXPECTED_ROOM', 'H00-00-00-0000-00')
    monkeypatch.setenv('AIRCON_CONNECTIONS_JSON', '{}')
    with patch('studio.cloud_runner.GitHubCheckpoint', return_value=cp), patch('studio.cloud_runner.Device', side_effect=device):
        assert main(['--config', str(path), '--command', 'tick']) == 0
        assert not created and not saved
        assert main(['--config', str(path), '--command', 'start']) == 0
        assert saved['state']['active'] and saved['state']['not_before'] > time.time()
        assert main(['--config', str(path), '--command', 'pause']) == 0
        assert not saved['state']['active']
        count = len(created)
        assert main(['--config', str(path), '--command', 'tick']) == 0 and len(created) == count
        config['program'] = [{'op': 'pass'}]
        path.write_text(json.dumps(config), encoding='utf-8')
        assert main(['--config', str(path), '--command', 'start']) == 1
        assert main(['--config', str(path), '--command', 'reset']) == 0
        assert not saved['state']['active'] and saved['state']['fingerprint'] == fingerprint(config['program'])
    assert all(not value.control.called for value in created)


def test_status_is_read_only_and_logs_only_operational_fields(tmp_path, monkeypatch, capsys):
    from studio.cloud_runner import main
    path = tmp_path/'script.json'
    path.write_text(json.dumps({'identifier': '0123456789abcdef', 'cloud_mode': 'resume', 'device': {}, 'program': [control('power', '0')]}))
    monkeypatch.setenv('AIRCON_TOKEN', 'dummy-account-token')
    monkeypatch.setenv('AIRCON_EXPECTED_ROOM', 'H00-00-00-0000-00')
    monkeypatch.setenv('AIRCON_CONNECTIONS_JSON', '{}')
    device = Mock()
    device.status.return_value = {'power': 1, 'flap': 'S', 'account': 'private-account', 'room': 'private-room'}
    with patch('studio.cloud_runner.Device', return_value=device), patch('studio.cloud_runner.GitHubCheckpoint') as checkpoint:
        assert main(['--config', str(path), '--command', 'status']) == 0
        checkpoint.assert_not_called()
    device.control.assert_not_called()
    assert 'private-account' not in capsys.readouterr().out


def test_cloud_logs_redact_known_secrets_and_escape_workflow_commands(monkeypatch):
    from studio.cloud_runner import redact
    monkeypatch.setenv('AIRCON_TOKEN', 'Bearer private-account-token')
    monkeypatch.setenv('AIRCON_EXPECTED_ROOM', 'private-room-code')
    monkeypatch.setenv('AIRCON_CONNECTIONS_JSON', json.dumps({'sensor': {'kind': 'http', 'token': 'private-sensor-token'}}))
    text = redact('private-account-token private-room-code private-sensor-token\n::warning::test')
    assert 'private-account-token' not in text and 'private-room-code' not in text and 'private-sensor-token' not in text
    assert '\n' not in text


def test_secret_copy_uses_clipboard_without_echo_and_reuses_key(tmp_path):
    from studio.bridge import Bridge
    store = Store(tmp_path)
    store.update(room='H00-test-room-00')
    store.secret_set('connections', {'sensor': {'kind': 'http', 'url': 'https://example.test', 'token': 'private-connector-token'}})
    bridge = Bridge(store, ROOT, demo=True)
    replies = []
    bridge.reply.connect(replies.append)
    clipboard = Mock()
    with patch('PySide6.QtGui.QGuiApplication.clipboard', return_value=clipboard):
        bridge.request('room', 'copy_cloud_room', '{}')
        assert clipboard.setText.call_args.args[0] == 'H00-test-room-00'
        bridge.request('connections', 'copy_cloud_connections', json.dumps({'names': ['sensor']}))
        assert json.loads(clipboard.setText.call_args.args[0])['sensor']['token'] == 'private-connector-token'
        bridge.request('key1', 'copy_cloud_state_key', '{}')
        key = clipboard.setText.call_args.args[0]
        Fernet(key)
        bridge.request('key2', 'copy_cloud_state_key', '{}')
        assert clipboard.setText.call_args.args[0] == key
    assert all(json.loads(reply)['ok'] for reply in replies)
    assert 'private-connector-token' not in ''.join(replies) and key not in ''.join(replies)


def test_cloud_gui_smoke_if_available():
    path = ROOT/'.demo-data'/'cloud-smoke.json'
    if not path.exists(): pytest.skip('Run GUI smoke first')
    result = json.loads(path.read_text(encoding='utf-8'))
    assert all(result.values())


def test_debounce_and_cooldown_wall_time_survive_new_process(cloud):
    clock, _, snapshots, resume = cloud
    program = [{'op': 'forever', 'body': [
        {'op': 'set', 'name': 'ready', 'value': {'op': 'debounce', 'id': 'gate', 'value': lit(True), 'seconds': lit(100)}},
        {'op': 'cooldown', 'key': 'gate', 'seconds': lit(600), 'body': [{'op': 'change_var', 'name': 'count', 'value': lit(1)}]},
        {'op': 'wait', 'seconds': lit(60)}]}]
    vm = resume(program); vm.run()
    assert vm.engine.variables['ready'] is False and vm.engine.variables['count'] == 1
    clock.advance(300)
    vm = resume(program, snapshots[-1]); vm.run()
    assert vm.engine.variables['ready'] is True and vm.engine.variables['count'] == 1
    clock.advance(301)
    vm = resume(program, snapshots[-1]); vm.run()
    assert vm.engine.variables['count'] == 2


def test_selected_if_branch_is_not_re_evaluated_after_wait(cloud):
    clock, device, snapshots, resume = cloud
    program = [{'op': 'if', 'branches': [{'condition': {'op': 'state_flag', 'field': 'power', 'target': '0'},
                 'body': [{'op': 'wait', 'seconds': lit(1)}, {'op': 'set', 'name': 'branch', 'value': lit('original')}]}],
                'else': [{'op': 'set', 'name': 'branch', 'value': lit('wrong')}]}]
    vm = resume(program); vm.run()
    device.demo_state['power'] = 1; clock.advance(300)
    vm = resume(program, snapshots[-1]); vm.run()
    assert vm.engine.variables['branch'] == 'original'


def test_event_timeout_runs_else_and_no_phantom_event(cloud):
    clock, _, snapshots, resume = cloud
    program = [{'op': 'wait_event', 'field': 'flap', 'source': '*', 'timeout': lit(5), 'name': 'event',
        'body': [{'op': 'set', 'name': 'wrong', 'value': lit(True)}],
        'else': [{'op': 'set', 'name': 'timeout', 'value': lit(True)}]}]
    vm = resume(program); vm.run()
    clock.advance(300)
    vm = resume(program, snapshots[-1]); vm.run()
    assert vm.engine.variables['timeout'] and 'wrong' not in vm.engine.variables


def test_resume_vm_rejects_non_resumable_side_effects_before_control(cloud):
    _, device, _, resume = cloud
    for node in ({'op': 'custom_code', 'source': 'result = 1'},
                 {'op': 'log', 'value': {'op': 'http_request', 'method': 'POST', 'connection': 'api', 'body': lit({}), 'path': ''}}):
        with pytest.raises(StudioError): resume([control('power', '1'), node])
    device.control.assert_not_called()


def test_explicit_retry_pending_sends_target_once_then_continues(cloud):
    _, device, _, resume = cloud
    program = [control('power', '1'), {'op': 'set', 'name': 'done', 'value': lit(True)}]
    vm = resume(program)
    vm.state['frames'][0]['index'] = 1
    vm.state['pending_control'] = {'field': 'power', 'value': '1'}
    assert vm.run(retry_pending=True) == 'completed'
    assert device.control.call_count == 1 and vm.engine.variables['done']


def test_malformed_statement_is_rejected_before_any_device_command(tmp_path):
    engine = Engine(Mock(), Integrations(CloudStore({}, {}), True))
    with pytest.raises(StudioError): engine.preflight([control('power', '1'), {'invalid': True}])


def test_literal_python_connector_names_are_included_in_secret_export(tmp_path):
    store = Store(tmp_path)
    store.secret_set('connections', {'sensor': {'kind': 'http', 'url': 'https://example.test/api', 'token': 'private-sensor'}})
    report = analyse({'mode': 'code', 'cloud_mode': 'once', 'code': 'result = ctx.http("sensor", "value")', 'trusted_code': True}, store)
    assert report['connections'] == ['sensor'] and not report['errors']
