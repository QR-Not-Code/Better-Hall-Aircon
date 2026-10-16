"""Compile reviewed scripts into a credential-free, portable Actions repository ZIP."""
import hashlib
import ast
import ipaddress
import json
import re
import zipfile
from pathlib import Path
from .engine import Engine
from .device import Device
from .integrations import Integrations
from .storage import StudioError

RUNTIME = ['storage.py', 'device.py', 'observer.py', 'engine.py', 'integrations.py', 'operations.py', 'logic.py',
           'code_runtime.py', 'cloud_store.py', 'cloud_vm.py', 'cloud_runner.py']
SCHEDULES = {5: '3-58/5 * * * *', 10: '3-53/10 * * * *', 15: '3-48/15 * * * *', 30: '3,33 * * * *', 60: '3 * * * *'}


def walk(value):
    if isinstance(value, dict):
        if 'op' in value:
            yield value
            if value['op'] == 'literal': return
        for item in value.values(): yield from walk(item)
    elif isinstance(value, list):
        for item in value: yield from walk(item)


def private_host(host):
    host = (host or '').lower().strip('[]')
    if host in ('localhost', '0.0.0.0') or host.endswith(('.local', '.localhost')): return True
    try: return not ipaddress.ip_address(host).is_global
    except ValueError: return '.' not in host


def analyse(data, store):
    mode = data.get('cloud_mode', 'resume')
    if mode not in ('resume', 'once'): raise StudioError('云端模式无效。')
    program = data.get('program', [])
    if data.get('mode') == 'code': program = [{'op': 'custom_code', 'source': data.get('code', ''), 'timeout': 3600}]
    engine = Engine(Device(store, True), Integrations(store, True))
    engine.preflight(program)
    if not program: raise StudioError('请先添加脚本。')
    errors, warnings, connections = [], [], set()
    from urllib.parse import urlsplit
    profiles = store.secrets().get('connections', {})
    def inspect_connection(name):
        connections.add(name)
        profile = profiles.get(name)
        if profile is None: errors.append(f'连接「{name}」尚未配置。')
        elif profile.get('kind') not in ('http', 'calendar', 'mqtt'): errors.append(f'连接「{name}」的类型不支持云端。')
        elif private_host(profile.get('host') if profile.get('kind') == 'mqtt' else urlsplit(profile.get('url', '')).hostname):
            errors.append(f'连接「{name}」使用本机或局域网地址，GitHub 托管 runner 无法直接访问。')
    for node in walk(program):
        op = node['op']
        if op in ('custom_code', 'custom_value'):
            if mode == 'resume': errors.append('任意 Python 无法自动恢复执行栈，请改用单次模式，或改写为积木。')
            else: warnings.append('Python 在 Linux 云端执行，单个 Python 进程最长 1 小时；本机文件、Windows API、额外 pip 包需自行适配。')
            if not data.get('trusted_code'): errors.append('代码模块需先勾选信任本脚本的 Python 代码。')
            for call in ast.walk(ast.parse(node.get('source', ''))):
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name) and call.func.value.id == 'ctx' and call.func.attr in ('http', 'request', 'calendar', 'mqtt'):
                    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str): inspect_connection(call.args[0].value)
                    else: warnings.append('Python 使用动态连接名，需自行补充 AIRCON_CONNECTIONS_JSON；静态检查无法列出全部引用。')
        if mode == 'resume' and op == 'http_request' and node.get('method') not in ('GET', 'HEAD'):
            errors.append('带写入副作用的自定义 HTTP 请求请使用单次模式；断点模式不自动重放此类请求。')
        if op in ('http', 'http_request', 'mqtt', 'calendar', 'network', 'net_time'):
            name = node.get('connection', '')
            inspect_connection(name)
        if mode == 'once' and op in ('forever', 'while', 'wait_until', 'wait_event'):
            warnings.append('单次作业有时限，不能永久常驻；长期积木流程推荐断点模式。')
        if op == 'notify': warnings.append('云端提示记入执行结果，不会弹出已关闭电脑的界面。')
    if mode == 'resume':
        warnings.extend(['定时最短 5 分钟且可能延迟；短等待、时间条件和事件监测精度受触发间隔影响，精确时刻等号可能错过，建议使用时段加当天一次。',
                         '变量、循环位置与观察基线会加密保存到 aircon-state 分支，需要 contents: write 和 AIRCON_STATE_KEY。'])
    else: warnings.append('单次模式不会跨作业恢复变量、等待或循环进度；退出作业后进程停止。')
    warnings.append('Token 到期需更新 GitHub Secret；本工具没有已验证的自动刷新接口。')
    return {'program': program, 'errors': list(dict.fromkeys(errors)), 'warnings': list(dict.fromkeys(warnings)),
            'connections': sorted(connections), 'mode': mode}


def workflow(identifier, mode, interval, minutes):
    schedule = f"  schedule:\n    - cron: '{SCHEDULES[interval]}'\n" if mode == 'resume' else ''
    permissions = 'write' if mode == 'resume' else 'read'
    options = '[test, status, start, resume, pause, reset, retry_pending]' if mode == 'resume' else '[test, status, start]'
    return f'''name: Hall Aircon Cloud {identifier}
on:
  workflow_dispatch:
    inputs:
      command:
        description: "test 模拟 / status 只读验证 / start 启动 / resume 继续 / pause 暂停 / reset 重置并暂停"
        type: choice
        default: test
        options: {options}
{schedule}permissions:
  contents: {permissions}
concurrency:
  group: hall-aircon-cloud-${{{{ github.repository }}}}
  cancel-in-progress: false
jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: {5 if mode == 'resume' else minutes + 5}
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - uses: actions/setup-python@v7
        with:
          python-version: '3.12'
      - name: Install headless runtime
        run: python -m pip install -r aircon/{identifier}/requirements.txt
      - name: Run exported script
        env:
          AIRCON_TOKEN: ${{{{ secrets.AIRCON_TOKEN }}}}
          AIRCON_EXPECTED_ROOM: ${{{{ secrets.AIRCON_EXPECTED_ROOM }}}}
          AIRCON_CONNECTIONS_JSON: ${{{{ secrets.AIRCON_CONNECTIONS_JSON }}}}
          AIRCON_STATE_KEY: ${{{{ secrets.AIRCON_STATE_KEY }}}}
          GITHUB_TOKEN: ${{{{ github.token }}}}
          CLOUD_COMMAND: ${{{{ github.event_name == 'schedule' && 'tick' || inputs.command }}}}
        run: python aircon/{identifier}/cloud_runner.py --config aircon/{identifier}/script.json --command "$CLOUD_COMMAND"
'''


def export_bundle(data, store, resources, filename):
    report = analyse(data, store)
    if report['errors']: raise StudioError('无法导出：' + '；'.join(report['errors']))
    try: interval, minutes = int(data.get('interval', 5)), int(data.get('job_minutes', 60))
    except (TypeError, ValueError): raise StudioError('云端运行参数无效。') from None
    if interval not in SCHEDULES or not 5 <= minutes <= 330: raise StudioError('触发间隔或作业时限无效。')
    seed = str(data.get('id') or data.get('name', 'script'))
    identifier = hashlib.sha256(seed.encode()).hexdigest()[:16]
    config = {'format': 'HallAirconCloud', 'version': 1, 'identifier': identifier, 'name': str(data.get('name', 'script'))[:100],
              'cloud_mode': report['mode'], 'job_minutes': minutes, 'trusted_code': bool(data.get('trusted_code')),
              'program': report['program'], 'device': {key: store.config().get(key, default) for key, default in (('timezone', 'Asia/Singapore'), ('learned', {}))}}
    text = json.dumps(config, ensure_ascii=False, indent=2, allow_nan=False)
    sensitive = [store.token(), store.config().get('room', '')]
    for profile in store.secrets().get('connections', {}).values():
        sensitive.extend(str(profile.get(key) or '') for key in ('token', 'url', 'host', 'ws') if len(str(profile.get(key) or '')) >= 6)
    if any(value and value in text for value in sensitive):
        raise StudioError('脚本源码中含当前凭据、设备编号或连接地址，请改为命名连接并通过 GitHub Secrets 配置。')
    prefix = f'aircon/{identifier}/'
    root = Path(resources)
    guide = (root / 'CLOUD.md').read_text(encoding='utf-8')
    requirements = 'cryptography==48.0.1\nicalendar==7.3.0\nrecurring-ical-events==3.8.2\npaho-mqtt==2.1.0\ntzdata>=2026.1\n'
    with zipfile.ZipFile(filename, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('.github/workflows/aircon-' + identifier + '.yml', workflow(identifier, report['mode'], interval, minutes))
        archive.writestr(prefix + 'script.json', text)
        archive.writestr(prefix + 'requirements.txt', requirements)
        archive.writestr(prefix + 'studio/__init__.py', '')
        for name in RUNTIME: archive.write(root / 'studio' / name, prefix + 'studio/' + name)
        archive.writestr(prefix + 'main.py', 'from studio.code_runtime import worker\nworker()\n')
        archive.writestr(prefix + 'cloud_runner.py', 'from studio.cloud_runner import main\nraise SystemExit(main())\n')
        archive.writestr('CLOUD-README.md', guide + '\n\n本次连接名称：' + ', '.join(report['connections']) + '\n模式：' + report['mode'] + '\n')
        examples = {}
        for name in report['connections']:
            kind = store.secrets()['connections'][name]['kind']
            examples[name] = ({'kind': 'mqtt', 'host': 'your-broker.example', 'port': 8883, 'topic': 'your-topic', 'tls': True, 'username': '', 'token': ''} if kind == 'mqtt' else
                              {'kind': kind, 'url': 'https://your-own-service.example/' + ('calendar.ics' if kind == 'calendar' else 'api'), 'token': ''})
        archive.writestr('connections.example.json', json.dumps(examples, ensure_ascii=False, indent=2))
    return {'saved': True, 'identifier': identifier, 'warnings': report['warnings']}
