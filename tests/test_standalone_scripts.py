from pathlib import Path
import subprocess
import sys
import threading
import time
from unittest.mock import Mock, patch

import pytest

from scripts import main as launcher
from studio.device import Device
from studio.storage import Store, StudioError


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def context(tmp_path):
    store = Store(tmp_path)
    store.update(learned={'setpoint': ['22', '24'], 'fanstep': ['A', 'L', 'H']})
    ctx = launcher.Context(store)
    ctx.device = Device(store, demo=True)
    return ctx


def test_context_uses_verified_device_controls_and_observes_changes(context):
    assert context.refresh()['identity_verified']
    assert context.control('setpoint', '22')['setpoint'] == '22'
    assert context.control('fanstep', 'L')['fanstep'] == 'L'
    events = context.events(0, 'fanstep', 'local_correlated')
    assert len(events) == 1
    assert events[0]['before'] == 'H' and events[0]['after'] == 'L'
    assert context.events(events[0]['seq'], 'fanstep') == []
    with pytest.raises(StudioError, match='尚未验证'):
        context.control('fanstep', 'UNKNOWN')


@pytest.mark.parametrize('seconds', [-1, 86401, float('nan'), float('inf')])
def test_context_rejects_invalid_waits(context, seconds):
    with pytest.raises(StudioError, match='Wait duration'):
        context.wait(seconds)


def test_context_wait_and_later_commands_stop_when_cancelled(context):
    context.device.control = Mock()
    timer = threading.Timer(.05, context.cancel.set)
    timer.start()
    started = time.monotonic()
    try:
        with pytest.raises(KeyboardInterrupt):
            context.wait(1500)
        assert time.monotonic() - started < 2
        with pytest.raises(KeyboardInterrupt):
            context.control('power', '1')
        context.device.control.assert_not_called()
    finally:
        timer.join()


def test_context_http_json_path_and_post_body(context):
    context.store.secrets = Mock(return_value={
        'connections': {'sensor': {'kind': 'http', 'url': 'https://example.test', 'token': 'sample'}}
    })
    with patch('studio.integrations.fetch', return_value=(b'{"sensor":{"temperature":25.5}}', None)) as fetch:
        assert context.http('sensor', 'sensor.temperature') == 25.5
        assert context.request('sensor', 'POST', {'enabled': True}, 'sensor.temperature') == 25.5
        assert fetch.call_args.args == ('https://example.test', 'sample', {'enabled': True}, 'POST')


def test_launcher_does_not_run_cycle_when_room_verification_fails(capsys):
    ctx = Mock()
    ctx.refresh.side_effect = StudioError('Room verification failed')
    with patch.object(launcher, 'Context', return_value=ctx), patch.object(launcher.runpy, 'run_path') as run:
        assert launcher.main() == 1
    run.assert_not_called()
    ctx.cancel.set.assert_called_once()
    assert 'Room verification failed' in capsys.readouterr().err


def test_standalone_entrypoint_runs_cycle_without_gui_from_another_directory(tmp_path):
    # Exercise the actual entrypoint and cycle with an isolated demo device.
    # Accelerate only waits, so no account files or real network are accessed.
    program = f'''
from pathlib import Path
import runpy
import sys
from unittest.mock import patch

sys.path.insert(0, {str(ROOT)!r})
from studio.device import Device
from studio.storage import Store

store = Store(Path.cwd() / 'isolated-settings')
store.update(learned={{'setpoint': ['26', '22', '24'], 'fanstep': ['A', 'H', 'L', 'LM', 'M', 'MH']}})
devices = []
waits = []

def device_factory(store):
    device = Device(store, demo=True)
    devices.append(device)
    return device

def fast_wait(event, seconds=None):
    waits.append(seconds)
    assert devices[0].demo_state['setpoint'] == '22'
    assert devices[0].demo_state['fanstep'] == 'H'
    assert devices[0].demo_state['power'] == (1 if seconds == 300 else 0)
    if len(waits) == 6:
        raise KeyboardInterrupt
    return False

with patch('studio.storage.Store', return_value=store), patch('studio.device.Device', side_effect=device_factory), patch('threading.Event.wait', fast_wait):
    try:
        runpy.run_path({str(ROOT / 'scripts' / 'main.py')!r}, run_name='__main__')
    except SystemExit as stopped:
        assert stopped.code == 130, stopped.code
    else:
        raise AssertionError('Expected the launcher to exit after Ctrl+C')

assert waits == [300, 1500] * 3
assert not any(name.startswith('PySide6') for name in sys.modules)
print('HEADLESS-CYCLE-OK')
'''
    result = subprocess.run([sys.executable, '-c', program], cwd=tmp_path,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'HEADLESS-CYCLE-OK' in result.stdout
    assert 'Cycling at 22 C, fan H' in result.stdout
    assert 'The aircon remains in its last state.' in result.stdout
