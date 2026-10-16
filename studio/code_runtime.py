"""Trusted Python code in a cancellable child process. This is NOT a sandbox."""
import ast
import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from .storage import StudioError


def validate(source):
    if not isinstance(source, str) or len(source) > 200_000:
        raise StudioError('代码超过 200KB。')
    try:
        ast.parse(source)
    except SyntaxError as error:
        raise StudioError(f'Python 第 {error.lineno} 行语法错误：{error.msg}') from None


def preview(source):
    validate(source)
    blocks = []
    for node in ast.parse(source).body:
        try:
            call = node.value
            if not isinstance(node, ast.Expr) or not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute) or not isinstance(call.func.value, ast.Name) or call.func.value.id != 'ctx' or call.keywords:
                raise ValueError()
            args = [ast.literal_eval(a) for a in call.args]
            def literal(value):
                return {'block': {'type': 'math_number', 'fields': {'NUM': value}}} if type(value) in (int, float) else {'block': {'type': 'text', 'fields': {'TEXT': str(value)}}}
            name = call.func.attr
            arities = {'control': 2, 'wait': 1, 'log': 1, 'refresh': 0}
            if len(args) != arities.get(name, -1): raise ValueError()
            if name == 'control' and args[0] in ('power', 'flap'):
                if str(args[1]) not in ({'0', '1'} if args[0] == 'power' else {'N', 'S'}): raise ValueError()
                block = {'type': 'ac_power' if args[0] == 'power' else 'ac_swing', 'fields': {'VALUE': str(args[1])}}
            elif name == 'wait': block = {'type': 'wait_seconds', 'inputs': {'SECONDS': literal(args[0])}}
            elif name == 'log': block = {'type': 'log_value', 'inputs': {'VALUE': literal(args[0])}}
            elif name == 'refresh' and not args: block = {'type': 'ac_refresh'}
            else: raise ValueError()
            blocks.append(block)
        except (ValueError, TypeError, AttributeError, IndexError):
            # Preserve arbitrary control flow, scopes and imports as one opaque module.
            return {'blocks': {'languageVersion': 0, 'blocks': [{'type': 'custom_code', 'fields': {'NAME': '用户代码'}, 'extraState': {'source': source}}]}}
    for a, b in zip(blocks, blocks[1:]): a['next'] = {'block': b}
    return {'blocks': {'languageVersion': 0, 'blocks': blocks[:1]}}


def execute(source, inputs, engine, timeout=60):
    validate(source)
    if engine.dry:
        engine.emit({'kind': 'log', 'text': '试运行：自定义 Python 仅检查语法，未执行；返回输入数据。'})
        return inputs
    if not engine.trusted_code:
        raise StudioError('代码模式和自定义模块需要勾选“信任本脚本的本机 Python 代码”。')
    command = [sys.executable, '--code-engine'] if getattr(sys, 'frozen', False) else [sys.executable, str(Path(__file__).resolve().parents[1] / 'main.py'), '--code-engine']
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               text=True, encoding='utf-8', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    messages = queue.Queue()
    def read():
        try:
            for line in process.stdout:
                if len(line) > 1_000_000: break
                messages.put(json.loads(line))
        except (OSError, ValueError): pass
        finally: messages.put({'kind': 'closed'})
    threading.Thread(target=read, daemon=True).start()
    def send(data):
        process.stdin.write(json.dumps(data, ensure_ascii=False, allow_nan=False) + '\n')
        process.stdin.flush()
    previous_deadline = engine.deadline
    try:
        send({'source': source, 'inputs': inputs, 'variables': engine.variables})
        deadline = time.monotonic() + min(max(float(timeout), 1), 3600)
        engine.deadline = min(previous_deadline, deadline) if previous_deadline is not None else deadline
        class CodeCancel:
            def wait(self, seconds):
                remaining = max(0, deadline - time.monotonic())
                return engine.cancel.wait(min(seconds, remaining)) or time.monotonic() >= deadline
        while time.monotonic() < deadline:
            engine.tick()
            try: message = messages.get(timeout=.1)
            except queue.Empty: continue
            kind = message.get('kind')
            if kind == 'result':
                variables = message.get('variables', {})
                if isinstance(variables, dict): engine.variables.update(variables)
                return message.get('result')
            if kind == 'error': raise StudioError(f'自定义代码第 {message.get("line", "?")} 行发生 {message.get("error_type", "Error")}；请检查输入类型与接口名称。')
            if kind == 'closed': raise StudioError('自定义代码进程已退出，未返回结果。')
            if kind == 'rpc':
                try:
                    args = message.get('args', [])
                    name = message['method']
                    if name == 'control':
                        value = engine.device.control(*args, cancel=CodeCancel())
                        engine.last_status = value
                        engine.emit({'kind': 'state', 'state': value})
                    elif name == 'refresh':
                        value = engine.device.status()
                        engine.last_status = value
                        engine.emit({'kind': 'state', 'state': value})
                    elif name == 'wait': engine.wait(*args); value = None
                    elif name == 'log': engine.emit({'kind': 'log', 'text': str(args[0])[:2000]}); value = None
                    elif name == 'http': value = engine.integrations.http(*args)
                    elif name == 'request': value = engine.integrations.request(*args)
                    elif name == 'calendar': value = engine.integrations.calendar(*args)
                    elif name == 'mqtt': value = engine.integrations.mqtt(*args, cancel=engine.cancel)
                    elif name == 'now': value = engine.integrations.now().isoformat()
                    elif name == 'events': value = engine.device.observer.since(*args)
                    else: raise StudioError('未知代码 SDK 方法。')
                    send({'ok': True, 'value': value})
                except StudioError as error: send({'ok': False, 'error': str(error)})
        raise StudioError('自定义代码达到执行超时。')
    finally:
        engine.deadline = previous_deadline
        if process.poll() is None: process.kill()
        process.wait(timeout=5)
        process.stdin.close()
        process.stdout.close()


def worker():
    # PyInstaller --windowed clears Python streams even when Popen supplied pipes.
    if sys.stdin is None or sys.stdout is None:
        import ctypes
        import io
        import msvcrt
        import os
        get_handle = ctypes.windll.kernel32.GetStdHandle
        get_handle.restype = ctypes.c_void_p
        if sys.stdin is None:
            descriptor = msvcrt.open_osfhandle(get_handle(-10), os.O_RDONLY)
            sys.stdin = io.TextIOWrapper(io.FileIO(descriptor, 'r'), encoding='utf-8')
        if sys.stdout is None:
            descriptor = msvcrt.open_osfhandle(get_handle(-11), os.O_WRONLY)
            sys.stdout = io.TextIOWrapper(io.FileIO(descriptor, 'w'), encoding='utf-8', write_through=True)
    protocol_in, protocol_out = sys.stdin, sys.stdout
    def write(data):
        protocol_out.write(json.dumps(data, ensure_ascii=False, allow_nan=False) + '\n')
        protocol_out.flush()
    class Context:
        def __getattr__(self, name):
            def call(*args):
                write({'kind': 'rpc', 'method': name, 'args': args})
                response = json.loads(protocol_in.readline())
                if not response['ok']: raise RuntimeError(response['error'])
                return response.get('value')
            return call
    try:
        data = json.loads(protocol_in.readline())
        ctx = Context()
        class Console:
            def write(self, text):
                if text.strip(): ctx.log(text)
                return len(text)
            def flush(self): pass
        sys.stdout = Console()
        scope = {'ctx': ctx, 'inputs': data.get('inputs'), 'variables': data.get('variables', {}), 'result': None, '__name__': '__user_script__'}
        exec(compile(data['source'], '<user-script>', 'exec'), scope, scope)
        write({'kind': 'result', 'result': scope.get('result'), 'variables': scope.get('variables', {})})
    except BaseException as error:
        import traceback
        frames = traceback.extract_tb(error.__traceback__)
        lines = [frame.lineno for frame in frames if frame.filename == '<user-script>']
        write({'kind': 'error', 'error_type': type(error).__name__, 'line': lines[-1] if lines else 0})
