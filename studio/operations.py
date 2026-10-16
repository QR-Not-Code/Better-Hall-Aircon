"""Standard data, event and signal-processing operations."""
import json
import math
import random
import statistics
import time
from .storage import StudioError
from .code_runtime import execute
from . import logic

EXPRESSIONS = {'random_int', 'random_float', 'clamp', 'unary', 'aggregate', 'list', 'list_get', 'list_contains',
               'split', 'replace', 'text_case', 'json_parse', 'json_stringify', 'coalesce', 'is_empty', 'object',
               'stable', 'changed', 'events', 'debounce', 'edge', 'hysteresis', 'smooth', 'elapsed', 'memory',
               'custom_value', 'http_request', 'between_time', 'random_choice', 'in_range', 'text_slice', 'keys',
               'object_get', 'list_range', 'timestamp_format', 'state_flag'}
STATEMENTS = {'custom_code', 'change_var', 'list_append', 'memory_set', 'cooldown', 'assert', 'wait_event', 'reset_signal',
              'object_set', 'var_delete', 'memory_delete', 'for_each', 'range_for'}
EXPRESSIONS |= logic.EXPRESSIONS
STATEMENTS |= logic.STATEMENTS


def expression(e, n):
    op = n['op']
    if op in logic.EXPRESSIONS: return logic.expression(e, n)
    get = lambda key: e.expr(n[key])
    key = n.get('key', n.get('id', 'signal'))
    now = time.monotonic()
    if op == 'random_choice': return random.choice(get('value'))
    if op == 'in_range': return float(get('low')) <= float(get('value')) <= float(get('high'))
    if op == 'text_slice': return str(get('value'))[int(get('start')):int(get('end'))]
    if op == 'keys': return list(get('value').keys())
    if op == 'object_get':
        obj, field = get('value'), str(get('key_value'))
        return obj[field] if field in obj else get('fallback')
    if op == 'list_range':
        values = range(int(get('start')), int(get('end')), int(get('step')))
        if len(values) > 10000: raise StudioError('范围列表不能超过 10000 项。')
        return list(values)
    if op == 'timestamp_format':
        import datetime
        return datetime.datetime.fromtimestamp(float(get('value')), e.integrations.now().tzinfo).strftime(n['format'])
    if op == 'state_flag':
        state = {'power': 1, 'flap': 'N'} if e.dry else e.device.status()
        e.last_status = state
        return str(state.get(n['field'])) == n['target']
    if op == 'random_int': return random.randint(int(get('a')), int(get('b')))
    if op == 'random_float': return random.random()
    if op == 'clamp': return min(max(float(get('value')), float(get('min'))), float(get('max')))
    if op == 'unary':
        value = float(get('value'))
        return {'ABS': abs, 'ROUND': round, 'FLOOR': math.floor, 'CEIL': math.ceil, 'SQRT': math.sqrt}[n['operator']](value)
    if op == 'aggregate':
        values = [float(v) for v in get('value')]
        if not values: raise StudioError('统计列表不能为空。')
        return {'SUM': sum, 'MIN': min, 'MAX': max, 'MEAN': statistics.mean, 'MEDIAN': statistics.median}[n['operator']](values)
    if op == 'list': return [e.expr(v) for v in n['items']]
    if op == 'object': return {str(get('key_value')): get('value')}
    if op == 'list_get': return get('value')[int(get('index'))]
    if op == 'list_contains': return get('item') in get('value')
    if op == 'split': return str(get('value')).split(str(get('separator')))
    if op == 'replace': return str(get('value')).replace(str(get('old')), str(get('new')))
    if op == 'text_case': return {'UPPER': str.upper, 'LOWER': str.lower, 'TRIM': str.strip}[n['operator']](str(get('value')))
    if op == 'json_parse': return json.loads(str(get('value')))
    if op == 'json_stringify': return json.dumps(get('value'), ensure_ascii=False, allow_nan=False)
    if op == 'coalesce':
        value = get('value')
        return get('fallback') if value is None else value
    if op == 'is_empty': return get('value') in (None, '', [], {})
    if op == 'memory': return e.memory[n['name']] if n['name'] in e.memory else get('fallback')
    if op == 'between_time':
        current = e.integrations.now().strftime('%H:%M')
        start, end = n['start'], n['end']
        return start <= current <= end if start <= end else current >= start or current <= end
    if op == 'elapsed': return now - e.started
    if op == 'http_request':
        if e.dry: return {'demo': True}
        return e.integrations.request(n['connection'], n['method'], get('body'), n.get('path', ''))
    if op == 'custom_value': return execute(n['source'], get('value'), e, n.get('timeout', 60))
    if op in ('changed', 'events'):
        if e.dry: return False if op == 'changed' else []
        e.last_status = e.device.status()
        events = e.device.observer.since(e.cursors.get(key, e.event_start), n.get('field', '*'), n.get('source', '*'))
        if op == 'events': return events
        e.cursors[key] = e.device.observer.serial
        target = n.get('target', '*')
        return any(target == '*' or str(event['after']) == target for event in events)
    if op == 'stable':
        if e.dry: return True
        e.last_status = e.device.status()
        return e.device.observer.stable(n['field']) >= float(get('seconds'))
    if op == 'debounce':
        value = bool(get('value'))
        if not value: e.signals.pop(key, None); return False
        started = e.signals.setdefault(key, now)
        return now - started >= max(0, float(get('seconds')))
    if op == 'edge':
        value = bool(get('value'))
        previous = e.signals.get(key, value)
        e.signals[key] = value
        return value != previous and (n['direction'] == 'ANY' or value == (n['direction'] == 'RISE'))
    if op == 'hysteresis':
        value, low, high = float(get('value')), float(get('low')), float(get('high'))
        if low >= high: raise StudioError('回差下界必须小于上界。')
        previous = e.signals.get(key, False)
        result = True if value >= high else False if value <= low else previous
        e.signals[key] = result
        return result
    if op == 'smooth':
        size = min(max(int(get('size')), 1), 1000)
        values = e.signals.setdefault(key, [])
        values.append(float(get('value')))
        del values[:-size]
        return statistics.mean(values)
    raise StudioError('未知数据操作。')


def statement(e, n, depth):
    op = n['op']
    get = lambda key: e.expr(n[key])
    if op in logic.STATEMENTS: return logic.statement(e, n, depth)
    if op in ('for_each', 'range_for'):
        from .engine import BreakLoop, ContinueLoop
        values = list(get('value')) if op == 'for_each' else range(int(get('start')), int(get('end')), int(get('step')))
        if len(values) > 10000: raise StudioError('列表循环不能超过 10000 项。')
        completed = not (e.dry and len(values) > 3)
        for item in values[:3] if e.dry else values:
            e.tick()
            e.variables[n['name']] = item
            try: e.sequence(n['body'], depth + 1)
            except BreakLoop:
                completed = False
                break
            except ContinueLoop: pass
        if completed: e.sequence(n.get('else', []), depth + 1)
    elif op == 'object_set':
        obj = e.variables.setdefault(n['name'], {})
        if not isinstance(obj, dict) or len(obj) >= 10000: raise StudioError('变量必须是少于 10000 项的对象。')
        obj[str(get('key_value'))] = get('value')
    elif op == 'var_delete': e.variables.pop(n['name'], None)
    elif op == 'memory_delete':
        e.memory.pop(n['name'], None)
        if not e.dry:
            memories = e.integrations.store.secrets().get('script_memory', {})
            memories[e.script_id] = e.memory
            e.integrations.store.secret_set('script_memory', memories)
    elif op == 'custom_code': execute(n['source'], e.variables, e, n.get('timeout', 60))
    elif op == 'change_var': e.variables[n['name']] = float(e.variables.get(n['name'], 0)) + float(get('value'))
    elif op == 'list_append':
        values = e.variables.setdefault(n['name'], [])
        if not isinstance(values, list) or len(values) >= 10000: raise StudioError('变量必须是少于 10000 项的列表。')
        values.append(get('value'))
    elif op == 'memory_set':
        e.memory[n['name']] = get('value')
        if not e.dry:
            all_memory = e.integrations.store.secrets().get('script_memory', {})
            all_memory[e.script_id] = e.memory
            e.integrations.store.secret_set('script_memory', all_memory)
    elif op == 'cooldown':
        key = n['key']
        now = time.monotonic()
        if now - e.signals.get('cooldown:' + key, -float('inf')) >= float(get('seconds')):
            e.sequence(n['body'], depth + 1)
            e.signals['cooldown:' + key] = time.monotonic()
    elif op == 'assert':
        if not get('condition'): raise StudioError('断言未通过：' + n.get('message', '条件不成立'))
    elif op == 'reset_signal': e.signals.pop(n['key'], None)
    elif op == 'wait_event':
        cursor = e.device.observer.serial
        until = time.monotonic() + min(max(float(get('timeout')), 1), 86400)
        if e.dry: return
        while time.monotonic() < until:
            e.tick()
            e.last_status = e.device.status()
            events = e.device.observer.since(cursor, n.get('field', '*'), n.get('source', '*'))
            if events:
                e.variables[n.get('name', '事件')] = events[-1]
                e.sequence(n.get('body', []), depth + 1)
                return
            e.wait(max(5, n.get('interval', 10)))
        e.sequence(n.get('else', []), depth + 1)
