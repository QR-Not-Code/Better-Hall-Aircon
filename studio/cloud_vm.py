"""Serializable Blockly execution frames; waits release the runner instead of sleeping."""
import copy
import math
import time
from collections import deque
from .storage import StudioError


class CheckpointFailure(BaseException):
    pass


class ControlUncertain(BaseException):
    pass


def new_state(fingerprint):
    return {'version': 1, 'fingerprint': fingerprint, 'active': False, 'completed': False,
            'started': time.time(), 'frames': [{'kind': 'seq', 'path': [], 'index': 0}],
            'variables': {}, 'days': {}, 'signals': {}, 'cursors': {}, 'event_start': 0,
            'script_memory': {}, 'not_before': 0, 'pending_control': None}


class CloudVM:
    def __init__(self, program, engine, state, persist):
        def supported(value):
            if isinstance(value, dict):
                if value.get('op') in ('custom_code', 'custom_value') or (value.get('op') == 'http_request' and value.get('method') not in ('GET', 'HEAD')):
                    raise StudioError('此脚本含不能安全恢复的代码或写入接口，请用云端单次模式。')
                if value.get('op') == 'literal': return
                for item in value.values(): supported(item)
            elif isinstance(value, list):
                for item in value: supported(item)
        supported(program)
        self.program, self.engine, self.state, self.persist = program, engine, state, persist
        self.engine.dry = False
        self.engine.preflight(program)
        self.engine.variables = state.setdefault('variables', {})
        self.engine.days = state.setdefault('days', {})
        self.engine.cursors = state.setdefault('cursors', {})
        self.engine.event_start = state.get('event_start', 0)
        self.engine.started = time.monotonic() - (time.time() - state['started'])
        offset = time.monotonic() - time.time()
        self.engine.signals = {key: value + offset if type(value) is float else value for key, value in state.get('signals', {}).items()}
        self.engine.memory = self.engine.integrations.store.secrets().get('script_memory', {}).get(self.engine.script_id, {})
        observer = self.engine.device.observer
        saved = state.get('observer', {})
        observer.last = saved.get('last', {})
        observer.serial = saved.get('serial', 0)
        observer.changed_at = {key: value + offset for key, value in saved.get('changed_at', {}).items()}
        observer.pending = {key: (value[0], value[1] + offset) for key, value in saved.get('pending', {}).items()}
        observer.events = deque(saved.get('events', []), maxlen=500)
        self.controls = 0

    def resolve(self, path):
        value = self.program
        for part in path: value = value[part]
        return value

    def push(self, path):
        self.state['frames'].append({'kind': 'seq', 'path': path, 'index': 0})

    def flush(self):
        offset = time.time() - time.monotonic()
        e = self.engine
        self.state['variables'], self.state['days'], self.state['cursors'] = e.variables, e.days, e.cursors
        self.state['signals'] = {key: value + offset if type(value) is float else value for key, value in e.signals.items()}
        observer = e.device.observer
        self.state['observer'] = {'last': observer.last, 'serial': observer.serial, 'events': list(observer.events),
            'changed_at': {key: value + offset for key, value in observer.changed_at.items()},
            'pending': {key: [value[0], value[1] + offset] for key, value in observer.pending.items()}}
        try: self.persist(copy.deepcopy(self.state))
        except Exception: raise CheckpointFailure('无法持久保存进度，已停止本轮控制。') from None

    def sleep_until(self, timestamp):
        self.state['not_before'] = timestamp
        self.flush()

    def reconcile(self, retry_pending=False):
        pending = self.state.get('pending_control')
        if not pending: return
        self.engine.device.observer.expect(pending['field'], pending['value'])
        state = self.engine.device.status()
        if str(state.get(pending['field'])) != str(pending['value']):
            if retry_pending:
                self.flush()
                try: state = self.engine.device.control(pending['field'], pending['value'])
                except Exception:
                    self.state.update(active=False, error='人工确认重试后仍未确认结果，请核对设备。')
                    self.flush()
                    raise ControlUncertain(self.state['error']) from None
                self.controls += 1
            else:
                self.state.update(active=False, error=f'上一条 {pending["field"]}={pending["value"]} 结果不确定；核对后可手动选择 retry_pending 确认重试，或 reset。')
                self.flush()
                raise ControlUncertain(self.state['error'])
        self.engine.last_status = state
        self.state['pending_control'] = None
        self.flush()

    def unwind(self, kind, message=''):
        stack = self.state['frames']
        while stack:
            frame = stack[-1]
            if frame['kind'] == 'try':
                node = self.resolve(frame['path'])
                if kind == 'error' and frame['phase'] == 'body' and (node['op'] == 'try' or node.get('has_catch')):
                    frame['phase'] = 'catch'
                    self.engine.variables['last_error'] = message
                    self.push(frame['path'] + ['catch'])
                    return
                if frame['phase'] != 'finally' and node.get('finally'):
                    frame.update(phase='finally', pending={'kind': kind, 'message': message})
                    self.push(frame['path'] + ['finally'])
                    return
            if frame['kind'] == 'retry' and kind == 'error':
                node = self.resolve(frame['path'])
                if frame['attempt'] < min(max(int(node.get('attempts', 3)), 1), 10):
                    frame['attempt'] += 1
                    frame['phase'] = 'waiting'
                    self.sleep_until(time.time() + max(5, float(node.get('interval', 10))))
                    return
            if frame['kind'] == 'loop' and kind in ('break', 'continue'):
                if kind == 'break': stack.pop()
                else: frame['phase'] = 'after'
                return
            stack.pop()
        if kind == 'error':
            self.state.update(active=False, error=message)
        else:
            self.state.update(active=False, completed=True, reason=kind)

    def step(self):
        e, stack = self.engine, self.state['frames']
        frame = stack[-1]
        kind = frame['kind']
        if kind == 'seq':
            sequence = self.resolve(frame['path'])
            if frame['index'] >= len(sequence): stack.pop(); return
            path = frame['path'] + [frame['index']]
            node = self.resolve(path)
            if node['op'] == 'control' and self.controls >= 6:
                self.sleep_until(time.time() + 300)
                return
            frame['index'] += 1
            e.tick(node)
            op = node['op']
            if op == 'wait':
                seconds = float(e.expr(node['seconds']))
                if not math.isfinite(seconds) or not 0 <= seconds <= 86400: raise StudioError('停顿时间必须在 0–86400 秒。')
                if seconds: self.sleep_until(time.time() + seconds)
            elif op == 'control':
                value = str(e.expr(node['value']))
                if value not in e.device.capabilities().get(node['field'], []): raise StudioError('控制值未学习，请先在桌面录制官方操作并重新导出。')
                self.state['pending_control'] = {'field': node['field'], 'value': value}
                e.device.observer.expect(node['field'], value)
                self.flush()  # Persist intent BEFORE any device request.
                e.emit({'kind': 'log', 'text': f'计划控制 {node["field"]}={value}，进度已保存。'})
                try: e.last_status = e.device.control(node['field'], value)
                except Exception:
                    self.state.update(active=False, error='控制已进入待确认状态；核对设备后手动恢复，不自动重发。')
                    self.flush()
                    raise ControlUncertain(self.state['error']) from None
                self.controls += 1
                self.state['pending_control'] = None
                self.flush()
                e.emit({'kind': 'log', 'text': f'已确认 {node["field"]}={value}。'})
            elif op == 'if':
                for index, branch in enumerate(node['branches']):
                    if e.expr(branch['condition']): self.push(path + ['branches', index, 'body']); break
                else:
                    if node.get('else'): self.push(path + ['else'])
            elif op == 'switch':
                value = e.expr(node['value'])
                for index, case in enumerate(node.get('cases', [])):
                    if value == e.expr(case['value']): self.push(path + ['cases', index, 'body']); break
                else:
                    if node.get('default'): self.push(path + ['default'])
            elif op in ('repeat', 'while', 'forever', 'for_each', 'range_for'):
                loop = {'kind': 'loop', 'path': path, 'iteration': 0, 'phase': 'check'}
                if op == 'repeat': loop['limit'] = min(max(int(float(e.expr(node['count']))), 0), 10000)
                if op == 'for_each': loop['values'] = list(e.expr(node['value']))
                if op == 'range_for':
                    values = range(int(e.expr(node['start'])), int(e.expr(node['end'])), int(e.expr(node['step'])))
                    if len(values) > 10000: raise StudioError('范围循环不能超过 10000 项。')
                    loop['values'] = list(values)
                if len(loop.get('values', [])) > 10000: raise StudioError('遍历列表不能超过 10000 项。')
                stack.append(loop)
            elif op in ('break', 'continue', 'stop'): self.unwind(op)
            elif op in ('try', 'try_finally'):
                stack.append({'kind': 'try', 'path': path, 'phase': 'body'})
                self.push(path + ['body'])
            elif op == 'retry':
                stack.append({'kind': 'retry', 'path': path, 'phase': 'body', 'attempt': 1})
                self.push(path + ['body'])
            elif op == 'once_day':
                date = e.integrations.now().date().isoformat()
                if e.days.get(node['key']) != date:
                    stack.append({'kind': 'once_done', 'key': node['key'], 'date': date})
                    self.push(path + ['body'])
            elif op == 'cooldown':
                if time.monotonic() - e.signals.get('cooldown:' + node['key'], -float('inf')) >= float(e.expr(node['seconds'])):
                    stack.append({'kind': 'cooldown_done', 'key': node['key']})
                    self.push(path + ['body'])
            elif op == 'wait_until': stack.append({'kind': 'condition', 'path': path})
            elif op == 'wait_event':
                timeout = min(max(float(e.expr(node['timeout'])), 1), 86400)
                stack.append({'kind': 'event', 'path': path, 'expires': time.time() + timeout, 'cursor': e.device.observer.serial})
            else: e.sequence([node])
        elif kind == 'loop':
            node = self.resolve(frame['path'])
            if frame['phase'] == 'after': frame['iteration'] += 1; frame['phase'] = 'check'
            op, iteration = node['op'], frame['iteration']
            e.last_status = {}
            done = ((op == 'repeat' and iteration >= frame['limit']) or
                    (op in ('for_each', 'range_for') and iteration >= len(frame['values'])) or
                    (op == 'while' and bool(e.expr(node['condition'])) == bool(node.get('until'))))
            if done:
                stack.pop()
                if node.get('else'): self.push(frame['path'] + ['else'])
            else:
                if op in ('for_each', 'range_for'): e.variables[node['name']] = frame['values'][iteration]
                frame['phase'] = 'after'
                self.push(frame['path'] + ['body'])
        elif kind == 'try':
            node = self.resolve(frame['path'])
            if frame['phase'] != 'finally' and node.get('finally'):
                frame['phase'] = 'finally'
                self.push(frame['path'] + ['finally'])
            else:
                stack.pop()
                if frame.get('pending'): self.unwind(**frame['pending'])
        elif kind == 'retry':
            if frame['phase'] == 'waiting':
                frame['phase'] = 'body'
                self.push(frame['path'] + ['body'])
            else: stack.pop()
        elif kind == 'once_done': e.days[frame['key']] = frame['date']; stack.pop()
        elif kind == 'cooldown_done': e.signals['cooldown:' + frame['key']] = time.monotonic(); stack.pop()
        elif kind == 'condition':
            node = self.resolve(frame['path'])
            e.last_status = {}
            if e.expr(node['condition']): stack.pop()
            else: self.sleep_until(time.time() + max(5, float(node.get('interval', 30))))
        elif kind == 'event':
            node = self.resolve(frame['path'])
            if time.time() >= frame['expires']:
                stack.pop()
                if node.get('else'): self.push(frame['path'] + ['else'])
            else:
                e.last_status = e.device.status()
                events = e.device.observer.since(frame['cursor'], node.get('field', '*'), node.get('source', '*'))
                if events:
                    e.variables[node.get('name', '事件')] = events[-1]
                    stack.pop()
                    if node.get('body'): self.push(frame['path'] + ['body'])
                else: self.sleep_until(time.time() + max(5, float(node.get('interval', 10))))
        else: raise StudioError('云端进度帧无效，请检查导出版本。')

    def run(self, max_steps=100, budget=45, retry_pending=False):
        if not self.state.get('active') or self.state.get('completed'): return 'paused'
        try:
            self.reconcile(retry_pending)
            if self.state.get('not_before', 0) > time.time(): return 'waiting'
            self.state['not_before'] = 0
            deadline = time.monotonic() + budget
            for _ in range(max_steps):
                if not self.state['frames']:
                    self.state.update(active=False, completed=True)
                    break
                if time.monotonic() >= deadline: break
                try: self.step()
                except (StudioError, ValueError, TypeError, ArithmeticError) as error:
                    self.unwind('error', str(error) if isinstance(error, StudioError) else '脚本输入类型或数值无效。')
                if self.state.get('not_before', 0) > time.time() or not self.state.get('active'): break
            self.flush()
            return 'completed' if self.state.get('completed') else 'paused' if not self.state.get('active') else 'checkpointed'
        except (CheckpointFailure, ControlUncertain): raise
