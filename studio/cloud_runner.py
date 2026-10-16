"""Entry point for exported Linux GitHub Actions bundles."""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from .cloud_store import CloudStore, GitHubCheckpoint
from .cloud_vm import CloudVM, new_state, CheckpointFailure, ControlUncertain
from .device import Device
from .engine import Engine
from .integrations import Integrations
from .storage import StudioError


def fingerprint(program):
    return hashlib.sha256(json.dumps(program, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def redact(message):
    sensitive = [os.environ.get(key, '') for key in ('AIRCON_TOKEN', 'AIRCON_EXPECTED_ROOM', 'AIRCON_STATE_KEY', 'GITHUB_TOKEN')]
    token = os.environ.get('AIRCON_TOKEN', '').strip()
    if token.lower().startswith('bearer '): sensitive.append(token[7:].strip())
    def strings(value):
        if isinstance(value, dict):
            for item in value.values(): yield from strings(item)
        elif isinstance(value, list):
            for item in value: yield from strings(item)
        elif isinstance(value, str): yield value
    try: sensitive.extend(strings(json.loads(os.environ.get('AIRCON_CONNECTIONS_JSON') or '{}')))
    except ValueError: pass
    message = str(message)
    for value in sorted(set(sensitive), key=len, reverse=True):
        if len(value) >= 3: message = message.replace(value, '[redacted]')
    return message.replace('\r', '\\r').replace('\n', '\\n')[:2000]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--command', choices=['test', 'status', 'start', 'resume', 'retry_pending', 'pause', 'reset', 'tick'], default='test')
    args = parser.parse_args(argv)
    config = json.loads(Path(args.config).read_text(encoding='utf-8'))
    program = config['program']
    checkpoint = None
    state = new_state(fingerprint(program))
    command = args.command
    # Only trusted repository code should be deployed. No PR trigger is exported.
    def emit(event):
        if event.get('kind') in ('log', 'notify'):
            print('Script log:', redact(event.get('text', '')), flush=True)
    try:
        if command not in ('test', 'status') and config['cloud_mode'] == 'resume':
            checkpoint = GitHubCheckpoint(config['identifier'])
            saved = checkpoint.load()
            if saved is not None: state = saved
            if command == 'pause':
                state['active'] = False
                checkpoint.save(state)
                print('Cloud script paused. Device state unchanged.')
                return 0
            if command == 'reset':
                # Explicit reset discards progress but starts paused, never switches AC.
                state = new_state(fingerprint(program))
                checkpoint.save(state)
                print('Checkpoint reset and paused. Select start to begin.')
                return 0
            if state.get('fingerprint') != fingerprint(program):
                raise StudioError('脚本内容与旧进度不一致，请先核对，再手动选择 reset 和 start。')
            if command == 'tick' and not state.get('active'):
                print('Not activated or already completed; no device request sent.')
                return 0
            if command in ('start', 'resume', 'retry_pending'):
                if state.get('completed'): raise StudioError('脚本已完成，重新执行前请明确选择 reset。')
                if command == 'retry_pending' and not state.get('pending_control'):
                    raise StudioError('当前没有待确认控制，请选择 resume 正常继续。')
                state.update(active=True, error='')
        elif command not in ('test', 'status', 'start'):
            raise StudioError('单次模式仅提供 test 和 start；长期执行请选择断点模式重新导出。')
        store = CloudStore(config.get('device', {}), state)
        engine = Engine(Device(store), Integrations(store), emit)
        engine.script_id = config['identifier']
        engine.trusted_code = bool(config.get('trusted_code'))
        if command == 'test':
            errors = []
            def test_emit(event):
                if event.get('kind') == 'error': errors.append(event['text'])
            engine.emit = test_emit
            engine.run(program, True, .05)
            if errors: raise StudioError('试运行失败：' + errors[0])
            print('Dry run passed. No device or connector request was sent.')
            return 0
        if not store.token() or not store.config().get('room'):
            raise StudioError('请配置 AIRCON_TOKEN 和 AIRCON_EXPECTED_ROOM Secrets。')
        if command == 'status':
            status = engine.device.status()
            print('Identity verified; operational state:', json.dumps({key: status.get(key) for key in ('power', 'flap', 'setpoint', 'comm_stat')}, ensure_ascii=False))
            return 0
        if config['cloud_mode'] == 'resume':
            identity = hashlib.sha256(store.config()['room'].encode()).hexdigest()
            if state.get('identity_fingerprint') not in (None, identity):
                raise StudioError('目标房间与旧进度不一致，请核对后明确 reset，再启动新目标。')
            state['identity_fingerprint'] = identity
            vm = CloudVM(program, engine, state, checkpoint.save)
            # Baseline from the restored observer must be sampled AFTER restoration.
            due = state.get('not_before', 0) <= time.time()
            if not state.get('pending_control') and (due or command != 'tick'):
                engine.last_status = engine.device.status()
            if command in ('start', 'resume', 'retry_pending'): vm.flush()
            result = vm.run(retry_pending=command == 'retry_pending')
            print('Cloud script:', result)
            if state.get('error'): raise StudioError(state['error'])
            return 0
        errors = []
        engine.last_status = engine.device.status()
        engine.emit = lambda event: errors.append(event['text']) if event.get('kind') == 'error' else emit(event)
        engine.run(program, False, config.get('job_minutes', 60) / 60)
        if errors: raise StudioError(errors[0])
        print('Single execution finished.')
        return 0
    except (StudioError, CheckpointFailure, ControlUncertain) as error:
        print('Cloud script stopped:', redact(error), file=sys.stderr)
        return 1
    except Exception:
        print('Cloud runner failed; credentials and response bodies were not logged.', file=sys.stderr)
        return 1


if __name__ == '__main__': raise SystemExit(main())
