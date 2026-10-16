"""Control-flow and predicates used by the visual logic catalogue."""
import math
from .storage import StudioError

EXPRESSIONS = {'xor', 'nand', 'nor', 'xnor', 'all', 'any', 'select', 'membership', 'is_null', 'type_is',
               'truthy', 'is_finite', 'var_defined'}
STATEMENTS = {'switch', 'pass', 'raise', 'try_finally'}


def expression(e, node):
    op = node['op']
    get = lambda key: e.expr(node[key])
    if op == 'select': return get('yes') if get('condition') else get('no')
    if op == 'nand': return not (get('a') and get('b'))
    if op == 'nor': return not (get('a') or get('b'))
    if op in ('xor', 'xnor'):
        result = bool(get('a')) != bool(get('b'))
        return result if op == 'xor' else not result
    if op == 'all': return all(get('value'))
    if op == 'any': return any(get('value'))
    if op == 'membership':
        result = get('item') in get('value')
        return not result if node.get('negate') else result
    if op == 'is_null': return get('value') is None
    if op == 'type_is':
        value = get('value')
        types = {'number': (int, float), 'text': (str,), 'boolean': (bool,), 'list': (list,), 'object': (dict,), 'null': (type(None),)}
        return type(value) in types[node['type']]
    if op == 'truthy': return bool(get('value'))
    if op == 'is_finite':
        value = get('value')
        return type(value) in (int, float) and math.isfinite(value)
    if op == 'var_defined': return node['name'] in e.variables
    raise StudioError('未知逻辑表达式。')


def statement(e, node, depth):
    op = node['op']
    if op == 'pass': return
    if op == 'raise': raise StudioError(str(e.expr(node['value']))[:500])
    if op == 'switch':
        value = e.expr(node['value'])
        for case in node.get('cases', []):
            if value == e.expr(case['value']):
                e.sequence(case['body'], depth + 1)
                return
        e.sequence(node.get('default', []), depth + 1)
    elif op == 'try_finally':
        try:
            try:
                e.sequence(node['body'], depth + 1)
            except (StudioError, ValueError, TypeError, ArithmeticError) as error:
                if not node.get('has_catch'): raise
                e.variables['last_error'] = str(error)
                e.sequence(node.get('catch', []), depth + 1)
        finally:
            # A user Stop must never cause new actuator commands from cleanup.
            if not e.cancel.is_set(): e.sequence(node.get('finally', []), depth + 1)
