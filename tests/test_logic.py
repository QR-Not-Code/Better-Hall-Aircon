import json
from pathlib import Path
from unittest.mock import Mock
import pytest
from studio.device import Device
from studio.engine import Engine
from studio.integrations import Integrations
from studio.storage import Store


def lit(value): return {'op': 'literal', 'value': value}
def var(name): return {'op': 'var', 'name': name}
def log(value): return {'op': 'log', 'value': lit(value)}
def compare(a, operator, b): return {'op': 'compare', 'a': a, 'operator': operator, 'b': b}
def branch(condition, body): return {'op': 'if', 'branches': [{'condition': condition, 'body': body}], 'else': []}


@pytest.fixture
def runner(tmp_path):
    store = Store(tmp_path)
    events = []
    engine = Engine(Device(store, True), Integrations(store, True), events.append)
    return engine, events


def texts(events): return [event['text'] for event in events if event.get('kind') == 'log']
def check_success(events): assert not [event for event in events if event['kind'] == 'error']


def test_continue_repeat_counts_iterations_and_skips_remaining_body(runner):
    engine, events = runner
    engine.run([{'op': 'set', 'name': 'n', 'value': lit(0)}, {'op': 'repeat', 'count': lit(4), 'body': [
        {'op': 'change_var', 'name': 'n', 'value': lit(1)},
        branch(compare(var('n'), 'EQ', lit(2)), [{'op': 'continue'}]),
        {'op': 'log', 'value': var('n')}
    ], 'else': [log('complete')]}], False)
    assert [text for text in texts(events) if text in ('1.0', '2.0', '3.0', '4.0')] == ['1.0', '3.0', '4.0']
    assert 'complete' in texts(events)
    check_success(events)


@pytest.mark.parametrize('kind', ['while', 'forever'])
def test_continue_and_break_in_conditional_and_infinite_loops(runner, kind):
    engine, events = runner
    node = {'op': kind, 'condition': lit(True), 'body': [
        {'op': 'change_var', 'name': 'n', 'value': lit(1)},
        branch(compare(var('n'), 'LT', lit(3)), [{'op': 'continue'}]),
        {'op': 'break'}, log('unreachable')], 'else': [log('wrong-else')]}
    engine.run([{'op': 'set', 'name': 'n', 'value': lit(0)}, node, log('after')], False)
    assert engine.variables['n'] == 3
    assert 'after' in texts(events) and 'unreachable' not in texts(events) and 'wrong-else' not in texts(events)
    check_success(events)


@pytest.mark.parametrize('loop', [
    {'op': 'for_each', 'name': 'n', 'value': lit([0, 1, 2, 3])},
    {'op': 'range_for', 'name': 'n', 'start': lit(0), 'end': lit(4), 'step': lit(1)}
])
def test_continue_foreach_and_range_else(runner, loop):
    engine, events = runner
    loop = {**loop, 'body': [branch(compare(var('n'), 'EQ', lit(1)), [{'op': 'continue'}]), {'op': 'log', 'value': var('n')}], 'else': [log('exhausted')]}
    engine.run([loop], False)
    assert [v for v in texts(events) if v in ('0', '1', '2', '3')] == ['0', '2', '3']
    assert 'exhausted' in texts(events)
    check_success(events)


def test_nested_break_and_continue_only_affect_nearest_loop(runner):
    engine, events = runner
    inner = {'op': 'for_each', 'name': 'inner', 'value': lit([0, 1, 2]), 'body': [
        branch(compare(var('inner'), 'EQ', lit(0)), [{'op': 'continue'}]),
        {'op': 'break'}, log('wrong')], 'else': [log('inner-else')]}
    outer = {'op': 'repeat', 'count': lit(2), 'body': [inner, log('outer-step')], 'else': [log('outer-else')]}
    engine.run([outer], False)
    assert texts(events).count('outer-step') == 2 and 'outer-else' in texts(events)
    assert 'inner-else' not in texts(events)
    check_success(events)


@pytest.mark.parametrize('op', ['break', 'continue'])
def test_invalid_loop_control_rejected_before_any_device_command(runner, op):
    engine, events = runner
    engine.device.control = Mock()
    engine.run([{'op': 'control', 'field': 'power', 'value': lit('0')}, {'op': op}], False)
    engine.device.control.assert_not_called()
    assert any(event.get('kind') == 'error' and op in event['text'] for event in events)


def test_elif_checks_in_order_and_else_only_when_none_match(runner):
    engine, events = runner
    node = {'op': 'if', 'branches': [
        {'condition': lit(False), 'body': [log('if')]},
        {'condition': lit(True), 'body': [log('elif')]},
        {'condition': {'op': 'var', 'name': 'must-not-evaluate'}, 'body': [log('wrong')]}],
        'else': [log('else')]}
    engine.run([node, {'op': 'if', 'branches': [{'condition': lit(False), 'body': []}], 'else': [log('fallback')]}], False)
    assert 'elif' in texts(events) and 'fallback' in texts(events) and 'else' not in texts(events)
    check_success(events)


def test_switch_evaluates_value_once_and_runs_first_match_only(runner):
    engine, events = runner
    selector = {'op': 'random_int', 'a': lit(7), 'b': lit(7)}
    node = {'op': 'switch', 'value': selector, 'cases': [
        {'value': lit(1), 'body': [log('wrong')]},
        {'value': lit(7), 'body': [log('matched')]},
        {'value': var('unread'), 'body': [log('wrong')]}], 'default': [log('default')]}
    engine.run([node], False)
    assert 'matched' in texts(events) and 'default' not in texts(events)
    check_success(events)


@pytest.mark.parametrize('op,a,b,result', [
    ('xor', True, True, False), ('xor', True, False, True),
    ('xnor', False, False, True), ('nand', True, True, False),
    ('nor', False, False, True)
])
def test_boolean_combinations(runner, op, a, b, result):
    engine, _ = runner
    assert engine.expr({'op': op, 'a': lit(a), 'b': lit(b)}) is result


def test_lazy_ternary_nand_nor_and_default_semantics(runner):
    engine, _ = runner
    missing = var('missing')
    assert engine.expr({'op': 'select', 'condition': lit(True), 'yes': lit(9), 'no': missing}) == 9
    assert engine.expr({'op': 'nand', 'a': lit(False), 'b': missing}) is True
    assert engine.expr({'op': 'nor', 'a': lit(True), 'b': missing}) is False
    assert engine.expr({'op': 'all', 'value': lit([])}) is True
    assert engine.expr({'op': 'any', 'value': lit([])}) is False
    assert engine.expr({'op': 'is_null', 'value': lit('')}) is False
    assert engine.expr({'op': 'type_is', 'value': lit(True), 'type': 'number'}) is False
    assert engine.expr({'op': 'var_defined', 'name': 'missing'}) is False


def test_try_finally_runs_on_continue_break_and_error(runner):
    engine, events = runner
    engine.run([{'op': 'repeat', 'count': lit(2), 'body': [{'op': 'try_finally', 'body': [{'op': 'continue'}], 'finally': [log('continue-cleanup')]}]},
                {'op': 'repeat', 'count': lit(2), 'body': [{'op': 'try_finally', 'body': [{'op': 'break'}], 'finally': [log('break-cleanup')]}]},
                {'op': 'try_finally', 'has_catch': True, 'body': [{'op': 'raise', 'value': lit('expected')}], 'catch': [log('caught')], 'finally': [log('error-cleanup')]}], False)
    assert texts(events).count('continue-cleanup') == 2
    assert texts(events).count('break-cleanup') == 1
    assert 'caught' in texts(events) and 'error-cleanup' in texts(events)
    check_success(events)


def test_loop_else_zero_iterations_and_break_from_else_targets_outer(runner):
    engine, events = runner
    engine.run([{'op': 'repeat', 'count': lit(3), 'body': [
        {'op': 'for_each', 'name': 'x', 'value': lit([]), 'body': [], 'else': [log('empty'), {'op': 'break'}]}, log('wrong')], 'else': [log('outer-else')]}], False)
    assert texts(events).count('empty') == 1
    assert 'wrong' not in texts(events) and 'outer-else' not in texts(events)
    check_success(events)


def test_gui_branch_composition_smoke():
    path = Path(__file__).resolve().parents[1] / '.demo-data' / 'logic-smoke.json'
    if not path.exists(): pytest.skip('Run GUI smoke first')
    result = json.loads(path.read_text(encoding='utf-8'))
    assert result['compoundElse'] and result['compoundElif'] and result['orphanRejected']
    assert result['lateElifRejected'] and result['lateCaseRejected']
    assert result['branchChain']['op'] == 'if' and len(result['branchChain']['branches']) == 2
    assert result['switch']['op'] == 'switch' and len(result['switch']['cases']) == 1
