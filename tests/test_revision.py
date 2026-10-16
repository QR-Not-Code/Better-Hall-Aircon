import json
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch
import pytest
from studio.storage import Store, StudioError
from studio.library import Library
from studio.observer import Observer
from studio.device import Device
from studio.integrations import Integrations
from studio.engine import Engine
from studio.code_runtime import execute, preview


def lit(value): return {'op': 'literal', 'value': value}


@pytest.fixture
def setup(tmp_path):
    store = Store(tmp_path)
    events = []
    engine = Engine(Device(store, True), Integrations(store, True), events.append)
    return store, engine, events


def test_named_library_rename_clone_delete_and_reload(setup):
    store, _, _ = setup
    library = Library(store)
    first = library.save({'name': 'A', 'workspace': {'blocks': {}}, 'mode': 'blocks'})
    renamed = library.save({**first, 'name': 'B'})
    assert renamed['id'] == first['id'] and len(library.list()) == 1
    clone = library.save({**renamed, 'id': '', 'name': 'C'})
    assert clone['id'] != first['id']
    assert Library(store).get(clone['id'])['name'] == 'C'
    library.delete(first['id'])
    assert len(library.list()) == 1


def test_legacy_import_keeps_original_and_new_install_is_empty(setup):
    store, _, _ = setup
    library = Library(store)
    assert library.list() == []
    legacy = store.root / 'workspace.aircon.json'
    legacy.write_text(json.dumps({'format': 'HallAirconStudio', 'version': 1, 'workspace': {'text': 'keep'}}))
    assert library.get(library.list()[0]['id'])['workspace']['text'] == 'keep'
    assert legacy.exists() and len(library.list()) == 1


def test_swing_power_external_events_and_self_correlation():
    observer = Observer()
    observer.sample({'power': 0, 'flap': 'N'})
    assert observer.since() == []
    observer.expect('power', 1)
    observer.sample({'power': 1, 'flap': 'S'})
    assert observer.since(field='power')[0]['source'] == 'local_correlated'
    assert observer.since(field='flap')[0]['source'] == 'suspected_external'
    observer.sample({'power': 1, 'flap': 'N'})
    assert [e['after'] for e in observer.since(field='flap')] == ['S', 'N']
    observer.sample({'power': 1, 'flap': 'N'})
    assert len(observer.since()) == 3


def test_telemetry_not_classified_as_manual_action():
    observer = Observer()
    observer.sample({'current_temperature': 25})
    observer.sample({'current_temperature': 24})
    assert observer.since()[0]['source'] == 'telemetry'


def test_demo_controls_publish_local_swing_events(setup):
    _, engine, _ = setup
    engine.device.status()
    engine.device.control('flap', 'S')
    assert engine.device.observer.since(field='flap')[0]['source'] == 'local_correlated'


def test_changed_consumes_each_event_once_per_block(setup):
    _, engine, _ = setup
    engine.dry = False
    engine.device.status()
    engine.device.demo_state['flap'] = 'S'
    node = {'op': 'changed', 'id': 'watch', 'field': 'flap', 'target': 'S', 'source': 'suspected_external'}
    assert engine.expr(node) is True
    assert engine.expr(node) is False


def test_debounce_edge_hysteresis_and_smoothing(setup):
    _, engine, _ = setup
    debounce = {'op': 'debounce', 'id': 'd', 'value': lit(True), 'seconds': lit(3)}
    with patch('studio.operations.time.monotonic', return_value=10): assert engine.expr(debounce) is False
    with patch('studio.operations.time.monotonic', return_value=14): assert engine.expr(debounce) is True
    edge = {'op': 'edge', 'id': 'edge', 'direction': 'RISE', 'value': lit(False)}
    assert engine.expr(edge) is False
    edge['value'] = lit(True)
    assert engine.expr(edge) is True and engine.expr(edge) is False
    hysteresis = {'op': 'hysteresis', 'id': 'h', 'value': lit(28), 'low': lit(24), 'high': lit(27)}
    assert engine.expr(hysteresis) is True
    hysteresis['value'] = lit(25)
    assert engine.expr(hysteresis) is True
    hysteresis['value'] = lit(23)
    assert engine.expr(hysteresis) is False
    node = {'op': 'smooth', 'id': 's', 'value': lit(10), 'size': lit(2)}
    assert engine.expr(node) == 10
    node['value'] = lit(20)
    assert engine.expr(node) == 15


def test_cooldown_prevents_repeated_actions(setup):
    _, engine, events = setup
    node = {'op': 'cooldown', 'key': 'key', 'seconds': lit(60), 'body': [{'op': 'log', 'value': lit('once')}]}
    engine.sequence([node, node])
    assert sum(e.get('text') == 'once' for e in events) == 1


def test_json_lists_random_and_short_circuit(setup):
    _, engine, _ = setup
    assert engine.expr({'op': 'boolean', 'operator': 'AND', 'a': lit(False), 'b': {'op': 'var', 'name': 'missing'}}) is False
    assert engine.expr({'op': 'random_int', 'a': lit(2), 'b': lit(2)}) == 2
    assert engine.expr({'op': 'aggregate', 'operator': 'MEAN', 'value': lit([1, 3, 8])}) == 4
    assert engine.expr({'op': 'list_range', 'start': lit(0), 'end': lit(5), 'step': lit(2)}) == [0, 2, 4]
    assert engine.expr({'op': 'object_get', 'value': lit({}), 'key_value': lit('x'), 'fallback': lit(5)}) == 5


def test_script_memory_survives_restart_and_is_namespaced(setup):
    store, engine, _ = setup
    engine.script_id = 'one'
    engine.run([{'op': 'memory_set', 'name': 'key', 'value': lit(17)}], False)
    new = Engine(Device(store, True), Integrations(store, True))
    new.script_id = 'one'
    new.run([{'op': 'set', 'name': 'read', 'value': {'op': 'memory', 'name': 'key', 'fallback': lit(0)}}], False)
    assert new.variables['read'] == 17
    assert 'two' not in store.secrets()['script_memory']


def test_python_preview_maps_known_calls_and_preserves_complex_source():
    result = preview('ctx.control("flap", "S")\nctx.wait(2)')
    first = result['blocks']['blocks'][0]
    assert first['type'] == 'ac_swing' and first['next']['block']['type'] == 'wait_seconds'
    source = 'import math\nfor n in range(3):\n    ctx.log(math.sqrt(n))'
    custom = preview(source)['blocks']['blocks'][0]
    assert custom['type'] == 'custom_code' and custom['extraState']['source'] == source


def test_custom_code_dry_run_does_not_execute(setup):
    _, engine, _ = setup
    assert execute('raise RuntimeError()', 123, engine) == 123


def test_untrusted_code_preflight_blocks_prior_controls(setup):
    _, engine, events = setup
    engine.device.control = Mock()
    engine.run([{'op': 'control', 'field': 'power', 'value': lit('0')}, {'op': 'custom_code', 'source': 'result = 1'}], False)
    engine.device.control.assert_not_called()
    assert any(e['kind'] == 'error' for e in events)


def test_trusted_python_real_subprocess_sdk_and_return(setup):
    _, engine, events = setup
    engine.dry = False
    engine.trusted_code = True
    result = execute('import math\nctx.log("sdk smoke")\nvariables["x"] = 6\nresult = math.sqrt(16) + ctx.refresh()["power"]', None, engine)
    assert result == 5 and engine.variables['x'] == 6
    assert any(e.get('text') == 'sdk smoke' for e in events)


def test_python_timeout_and_cancellation(setup):
    _, engine, events = setup
    engine.dry = False
    engine.trusted_code = True
    with pytest.raises(StudioError, match='超时'): execute('while True: pass', None, engine, timeout=1)
    def stop():
        time.sleep(.3)
        engine.cancel.set()
    thread = threading.Thread(target=stop)
    thread.start()
    from studio.engine import Halt
    with pytest.raises(Halt): execute('while True: pass', None, engine, timeout=10)
    thread.join()


def test_custom_http_methods_and_body_are_forwarded(setup):
    store, _, _ = setup
    store.secret_set('connections', {'api': {'kind': 'http', 'url': 'https://example.test/api', 'token': 'dummy'}})
    with patch('studio.integrations.fetch', return_value=(b'{"ok":true}', None)) as fetch:
        assert Integrations(store).request('api', 'POST', {'x': 1}, 'ok') is True
        assert fetch.call_args.args == ('https://example.test/api', 'dummy', {'x': 1}, 'POST')


def test_code_sdk_wait_respects_code_timeout_and_restores_script_deadline(setup):
    _, engine, _ = setup
    engine.dry = False
    engine.trusted_code = True
    engine.deadline = time.monotonic() + 600
    previous = engine.deadline
    started = time.monotonic()
    with pytest.raises(StudioError): execute('ctx.wait(100)', None, engine, timeout=1)
    assert time.monotonic() - started < 3
    assert engine.deadline == previous


def test_gui_revision_smoke_results():
    path = Path(__file__).resolve().parents[1] / '.demo-data' / 'library-smoke.json'
    if not path.exists(): pytest.skip('Run GUI smoke first')
    assert all(json.loads(path.read_text(encoding='utf-8')).values())
