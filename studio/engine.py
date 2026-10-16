"""Bounded, cancellable interpreter for Blockly's explicit JSON tree. No eval."""
import json
import math
import operator
import threading
import time
from .storage import StudioError
from .integrations import json_path
from . import operations


class Halt(Exception):
    pass


class BreakLoop(Exception):
    pass


class ContinueLoop(Exception):
    pass


class Engine:
    def __init__(self, device, integrations, emit=lambda event: None):
        self.device, self.integrations, self.emit = device, integrations, emit
        self.cancel = threading.Event()
        self.variables = {}
        self.count = 0
        self.dry = True
        self.last_status = {}
        self.deadline = None
        self.days = {}
        self.signals, self.cursors, self.memory = {}, {}, {}
        self.started = time.monotonic()
        self.event_start = 0
        self.trusted_code = False
        self.script_id = "unsaved"

    def tick(self, node=None):
        if self.cancel.is_set():
            raise Halt()
        if self.deadline is not None and time.monotonic() > self.deadline:
            raise StudioError('脚本达到本次运行时长上限。')
        self.count += 1
        if self.count > 100000:
            raise StudioError('脚本达到 100000 步上限，请增加停顿或减少循环。')
        if node and node.get('id'):
            self.emit({'kind': 'block', 'id': node['id']})

    def preflight(self, program):
        statements = {'wait', 'set', 'log', 'refresh', 'control', 'if', 'repeat', 'while', 'forever', 'break', 'continue', 'stop', 'try', 'wait_until', 'once_day', 'retry', 'notify'}
        expressions = {'literal', 'var', 'compare', 'boolean', 'not', 'math', 'join', 'length', 'contains', 'path', 'number', 'state', 'time', 'http', 'network', 'net_time', 'calendar', 'mqtt'}
        statements |= operations.STATEMENTS
        expressions |= operations.EXPRESSIONS
        total = 0
        def walk(value, depth=0):
            nonlocal total
            if depth > 64: raise StudioError('积木嵌套过深。')
            total += 1
            if total > 10000: raise StudioError('脚本过大。')
            if isinstance(value, list):
                for item in value: walk(item, depth + 1)
            elif isinstance(value, dict):
                op = value.get('op')
                if op is not None:
                    if op not in statements | expressions: raise StudioError('脚本含有未知积木。')
                    if op == 'control' and value.get('field') not in ('power', 'flap', 'setpoint', 'fanstep', 'mode'): raise StudioError('不允许控制这个设备字段。')
                    if not self.dry and op in ('http', 'network', 'net_time', 'calendar', 'mqtt', 'http_request'):
                        self.integrations.profile(value.get('connection', ''))
                if op in ('custom_code', 'custom_value'):
                    from .code_runtime import validate
                    validate(value.get('source', ''))
                    if not self.dry and not self.trusted_code: raise StudioError('请勾选信任本脚本的本机 Python 代码。')
                for key, item in value.items():
                    if key != 'value' or op != 'literal': walk(item, depth + 1)
        walk(program)
        def flow(nodes, loops=0):
            if not isinstance(nodes, list): raise StudioError('动作流程必须是列表。')
            for node in nodes:
                if not isinstance(node, dict) or node.get('op') not in statements:
                    raise StudioError('动作流程中存在无效或缺少操作类型的积木。')
                op = node.get('op')
                if op in ('break', 'continue') and not loops:
                    raise StudioError(f'{op} 只能放在循环内部；已在运行前阻止执行。')
                if op in ('repeat', 'while', 'forever', 'for_each', 'range_for'):
                    flow(node.get('body', []), loops + 1)
                    flow(node.get('else', []), loops)
                else:
                    for key in ('body', 'else', 'catch', 'finally'):
                        flow(node.get(key, []), loops)
                for branch in node.get('branches', []): flow(branch.get('body', []), loops)
                for case in node.get('cases', []): flow(case.get('body', []), loops)
                flow(node.get('default', []), loops)
        flow(program)

    def wait(self, seconds):
        seconds = float(seconds)
        if not math.isfinite(seconds) or seconds < 0 or seconds > 86400:
            raise StudioError('停顿时间必须在 0 到 86400 秒之间。')
        self.emit({'kind': 'log', 'text': f'{"试运行：" if self.dry else ""}等待 {seconds:g} 秒'})
        duration = min(seconds, .05) if self.dry else seconds
        if self.deadline is not None:
            duration = min(duration, max(0, self.deadline - time.monotonic()))
        if self.cancel.wait(duration):
            raise Halt()
        self.tick()

    def expr(self, node):
        self.tick()
        if not isinstance(node, dict):
            raise StudioError('存在未连接的数值积木。')
        op = node.get('op')
        if op in operations.EXPRESSIONS: return operations.expression(self, node)
        if op == 'literal':
            return node.get('value')
        if op == 'var':
            if node['name'] not in self.variables:
                raise StudioError('变量尚未赋值：' + node['name'])
            return self.variables[node['name']]
        if op == 'compare':
            a, b = self.expr(node['a']), self.expr(node['b'])
            comparisons = {'EQ': operator.eq, 'NEQ': operator.ne, 'LT': operator.lt, 'LTE': operator.le, 'GT': operator.gt, 'GTE': operator.ge}
            return comparisons[node['operator']](a, b)
        if op == 'boolean':
            a = bool(self.expr(node['a']))
            return (a and bool(self.expr(node['b']))) if node['operator'] == 'AND' else (a or bool(self.expr(node['b'])))
        if op == 'not':
            return not self.expr(node['value'])
        if op == 'math':
            a, b = float(self.expr(node['a'])), float(self.expr(node['b']))
            if node['operator'] == 'POWER' and (abs(b) > 100 or abs(a) > 1e6):
                raise StudioError('乘方输入过大。')
            functions = {'ADD': operator.add, 'MINUS': operator.sub, 'MULTIPLY': operator.mul, 'DIVIDE': operator.truediv, 'POWER': operator.pow, 'MODULO': operator.mod}
            result = functions[node['operator']](a, b)
            if not isinstance(result, (int, float)) or not math.isfinite(result):
                raise StudioError('运算产生无效数值。')
            return result
        if op == 'join':
            return ''.join(str(self.expr(n)) for n in node['items'])[:10000]
        if op == 'length':
            return len(self.expr(node['value']))
        if op == 'contains':
            return str(self.expr(node['part'])) in str(self.expr(node['text']))
        if op == 'path':
            return json_path(self.expr(node['value']), node['path'])
        if op == 'number':
            return float(self.expr(node['value']))
        if op == 'state':
            if not self.last_status:
                self.last_status = {'power': 1, 'flap': 'N', 'current_temperature': 25, 'setpoint': 24} if self.dry else self.device.status()
            return self.last_status.get(node['field'])
        if op == 'time':
            now = self.integrations.now()
            return {'hour': now.hour, 'minute': now.minute, 'weekday': now.isoweekday(), 'timestamp': now.timestamp(), 'date': now.date().isoformat(), 'hhmm': now.strftime('%H:%M')}[node['field']]
        if op in ('http', 'network', 'net_time', 'calendar', 'mqtt'):
            if self.dry:
                return {'http': 26.5, 'network': True, 'net_time': self.integrations.now().timestamp(), 'calendar': [{'title': 'demo'}], 'mqtt': 26.5}[op]
            if op == 'http': return self.integrations.http(node['connection'], node['path'])
            if op == 'network': return self.integrations.network(node['connection'])
            if op == 'net_time': return self.integrations.net_time(node['connection'])
            if op == 'calendar': return self.integrations.calendar(node['connection'], node['hours'], node.get('keyword', ''))
            if op == 'mqtt': return self.integrations.mqtt(node['connection'], node['path'], self.cancel)
        raise StudioError('不支持的表达式：' + str(op))

    def sequence(self, nodes, depth=0):
        if depth > 32:
            raise StudioError('积木嵌套超过 32 层。')
        for node in nodes:
            self.tick(node)
            op = node['op']
            if op == 'wait': self.wait(self.expr(node['seconds']))
            elif op == 'set': self.variables[node['name']] = self.expr(node['value'])
            elif op == 'log':
                # User messages may contain personal sensor/calendar data. Kept in memory only.
                self.emit({'kind': 'log', 'text': str(self.expr(node['value']))[:2000]})
            elif op == 'notify':
                self.emit({'kind': 'notify', 'text': str(self.expr(node['value']))[:500]})
            elif op == 'refresh':
                self.last_status = {'power': 1, 'flap': 'N', 'current_temperature': 25, 'setpoint': 24} if self.dry else self.device.status()
                if not self.dry: self.emit({'kind': 'state', 'state': self.last_status})
                self.emit({'kind': 'log', 'text': '已刷新设备状态' if not self.dry else '试运行：使用示例设备状态'})
            elif op == 'control':
                value = self.expr(node['value'])
                self.emit({'kind': 'log', 'text': f'{"试运行：" if self.dry else ""}设置 {node["field"]} = {value}'})
                if not self.dry:
                    self.last_status = self.device.control(node['field'], value, self.cancel)
                    self.emit({'kind': 'state', 'state': self.last_status})
                else:
                    self.last_status[node['field']] = value
            elif op == 'if':
                for branch in node['branches']:
                    if self.expr(branch['condition']):
                        self.sequence(branch['body'], depth + 1)
                        break
                else:
                    self.sequence(node.get('else', []), depth + 1)
            elif op in ('repeat', 'while', 'forever'):
                count = 0
                completed = True
                limit = min(max(int(float(self.expr(node['count']))), 0), 10000) if op == 'repeat' else 10000
                while count < limit:
                    self.tick()
                    if op == 'while' and bool(self.expr(node['condition'])) == bool(node.get('until')):
                        break
                    if self.dry and count >= 3:
                        self.emit({'kind': 'log', 'text': '试运行：循环最多演示 3 次'})
                        completed = False
                        break
                    try:
                        self.sequence(node['body'], depth + 1)
                    except BreakLoop:
                        completed = False
                        break
                    except ContinueLoop:
                        pass
                    count += 1
                    if self.cancel.wait(.01): raise Halt()
                else:
                    if op != 'repeat': raise StudioError('循环达到上限。')
                if completed: self.sequence(node.get('else', []), depth + 1)
            elif op == 'break': raise BreakLoop()
            elif op == 'continue': raise ContinueLoop()
            elif op == 'stop': raise Halt()
            elif op == 'once_day':
                date = self.integrations.now().date().isoformat()
                if self.days.get(node['key']) != date:
                    self.sequence(node['body'], depth + 1)
                    self.days[node['key']] = date
            elif op == 'try':
                try:
                    self.sequence(node['body'], depth + 1)
                except (StudioError, ValueError, TypeError, ArithmeticError) as e:
                    self.emit({'kind': 'log', 'text': '执行失败，进入错误处理分支'})
                    self.variables['last_error'] = str(e)
                    self.sequence(node.get('catch', []), depth + 1)
            elif op == 'retry':
                attempts = min(max(int(node.get('attempts', 3)), 1), 10)
                for attempt in range(attempts):
                    try:
                        self.sequence(node['body'], depth + 1)
                        break
                    except StudioError:
                        if attempt == attempts - 1: raise
                        self.emit({'kind': 'log', 'text': '分支失败，等待后重试；请仅用于可重复的操作'})
                        self.wait(max(5, float(node.get('interval', 10))))
            elif op == 'wait_until':
                iterations = 0
                while not self.expr(node['condition']):
                    self.tick()
                    if self.dry:
                        self.emit({'kind': 'log', 'text': '试运行：跳过条件等待'})
                        break
                    self.wait(max(5, float(node.get('interval', 30))))
                    iterations += 1
                    self.last_status = {}
            elif op in operations.STATEMENTS: operations.statement(self, node, depth)
            else: raise StudioError('不支持的动作：' + str(op))

    def run(self, program, dry=True, max_hours=24):
        self.dry = bool(dry)
        try:
            hours = float(max_hours)
            if not math.isfinite(hours) or not .01 <= hours <= 168:
                raise StudioError('运行时长应在 0.01 到 168 小时之间。')
            self.deadline = time.monotonic() + hours * 3600
            if not isinstance(program, list) or len(json.dumps(program)) > 500000:
                raise StudioError('脚本为空或超过大小限制。')
            self.event_start = getattr(self.device.observer, "serial", 0) if hasattr(self.device, "observer") else 0
            if not self.dry:
                self.memory = self.integrations.store.secrets().get("script_memory", {}).get(self.script_id, {})
            self.preflight(program)
            self.emit({'kind': 'log', 'text': '开始试运行（不控制设备、不访问外部连接器）' if self.dry else '开始正式运行；请保持程序和电脑运行'})
            self.sequence(program)
            self.emit({'kind': 'log', 'text': '脚本执行完成'})
        except Halt:
            self.emit({'kind': 'log', 'text': '脚本已停止；不会自动改变当前空调状态'})
        except Exception as e:
            message = str(e) if isinstance(e, StudioError) else '脚本输入类型或结构错误，请检查高亮积木。'
            self.emit({'kind': 'error', 'text': message})
        finally:
            self.emit({'kind': 'finished'})
