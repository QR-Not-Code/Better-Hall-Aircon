import json
import threading
import time
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot, QRunnable, QThreadPool
from PySide6.QtWidgets import QFileDialog
from .capture import CaptureManager
from .device import Device
from .engine import Engine
from .library import Library
from .observer import Observer
from .code_runtime import preview, validate
from .cloud_export import analyse as analyse_cloud, export_bundle
from .integrations import Integrations
from .storage import StudioError, atomic_write, room_code


class Job(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self): self.fn()


class Bridge(QObject):
    reply = Signal(str)
    event = Signal(str)

    def __init__(self, store, resources, parent=None, demo=False):
        super().__init__(parent)
        self.store, self.resources, self.demo = store, Path(resources), demo
        self.device = Device(store, demo)
        self.integrations = Integrations(store, demo)
        self.capture = CaptureManager(store, resources)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(5)
        self.engine = None
        self.runner = None
        self.script_lock = threading.Lock()
        self.poll_lock = threading.Lock()
        self.last_state = None
        self.active_verified = False
        self.capture_error = ''
        self.library = Library(store)

    def publish(self, payload):
        if payload.get('kind') == 'state': self.last_state = payload['state']
        self.event.emit(json.dumps(payload, ensure_ascii=False))

    @Slot(str, str, str)
    def request(self, request_id, method, payload):
        try:
            data = json.loads(payload or '{}')
            if method in ('copy_cloud_room', 'copy_cloud_connections', 'copy_cloud_state_key'):
                from PySide6.QtGui import QGuiApplication
                if method == 'copy_cloud_room':
                    value = self.store.config().get('room', '')
                    if not value: raise StudioError('请先连接并核对自己的房间。')
                elif method == 'copy_cloud_connections':
                    names = data.get('names', [])
                    if not isinstance(names, list) or any(not isinstance(name, str) for name in names): raise StudioError('连接名称格式无效。')
                    profiles = self.store.secrets().get('connections', {})
                    if any(name not in profiles for name in names): raise StudioError('部分连接不存在，请重新检查兼容性。')
                    value = json.dumps({name: profiles[name] for name in names}, ensure_ascii=False)
                else:
                    from cryptography.fernet import Fernet
                    value = self.store.secrets().get('cloud_state_key')
                    if not value:
                        value = Fernet.generate_key().decode('ascii')
                        self.store.secret_set('cloud_state_key', value)
                QGuiApplication.clipboard().setText(value)
                self.reply.emit(json.dumps({'id': request_id, 'ok': True, 'data': {'copied': True}}))
                return
            if method == 'open_scripts_folder':
                from PySide6.QtCore import QUrl
                from PySide6.QtGui import QDesktopServices
                folder = self.store.root.resolve()
                folder.mkdir(parents=True, exist_ok=True)
                if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
                    raise StudioError('无法打开脚本文件夹，请在资源管理器中打开 %LOCALAPPDATA%\\HallAirconStudio。')
                self.reply.emit(json.dumps({'id': request_id, 'ok': True, 'data': {'opened': True}}))
                return
            if method == 'copy_token':
                from PySide6.QtGui import QGuiApplication
                token = self.handle('show_token', {})['token']
                QGuiApplication.clipboard().setText(token)
                self.reply.emit(json.dumps({'id': request_id, 'ok': True, 'data': {'copied': True}}))
                return
            if method == 'pick_qr':
                filename, _ = QFileDialog.getOpenFileName(None, '选择房间二维码图片', '', '图片 (*.png *.jpg *.jpeg *.webp *.bmp)')
                data = {'filename': filename}
            elif method == 'import_script':
                filename, _ = QFileDialog.getOpenFileName(None, '导入脚本', '', '空调脚本 (*.aircon.json *.json)')
                data = {'filename': filename}
            elif method == 'export_script':
                filename, _ = QFileDialog.getSaveFileName(None, '导出脚本（不包含连接凭据）', '我的空调脚本.aircon.json', '空调脚本 (*.aircon.json)')
                data['filename'] = filename
            elif method == 'pick_code':
                filename, _ = QFileDialog.getOpenFileName(None, 'Open Python script', '', 'Python (*.py)')
                data = {'filename': filename}
            elif method == 'export_code':
                filename, _ = QFileDialog.getSaveFileName(None, 'Save Python script', 'script.py', 'Python (*.py)')
                data['filename'] = filename
            elif method == 'export_cloud':
                filename, _ = QFileDialog.getSaveFileName(None, '导出 GitHub Actions（不含个人凭据）', 'HallAircon-GitHub-Actions.zip', 'ZIP (*.zip)')
                data['filename'] = filename
            elif method == 'import_ics':
                filename, _ = QFileDialog.getOpenFileName(None, '选择日历文件', '', '日历 (*.ics)')
                data = {'filename': filename}
            self.pool.start(Job(lambda: self.execute(request_id, method, data)))
        except Exception as exc:
            message = str(exc) if isinstance(exc, StudioError) else '无法完成本机交互，请重试。'
            self.reply.emit(json.dumps({'id': request_id, 'ok': False, 'error': message}))

    def execute(self, request_id, method, data):
        try:
            result = self.handle(method, data)
            self.reply.emit(json.dumps({'id': request_id, 'ok': True, 'data': result}, ensure_ascii=False, allow_nan=False))
        except Exception as exc:
            message = str(exc) if isinstance(exc, StudioError) else '操作失败，请检查输入和运行环境。详细凭据未写入日志。'
            self.reply.emit(json.dumps({'id': request_id, 'ok': False, 'error': message}, ensure_ascii=False))

    def settings(self):
        cfg = self.store.config()
        return {'room': cfg.get('room', ''), 'ip': cfg.get('ip', ''), 'timezone': cfg.get('timezone', 'Asia/Singapore'),
                'has_token': bool(self.store.token()), 'expiry': self.store.expiry(), 'capabilities': self.device.capabilities(),
                'ips': self.capture.ips(), 'demo': self.demo,
                'token_preview': ((self.store.token()[:18] + '…' + self.store.token()[-8:]) if self.store.token() else ''),
                'connections': [{'name': n, 'kind': v['kind']} for n, v in self.store.secrets().get('connections', {}).items() if v.get('kind') in ('http', 'mqtt', 'calendar')]}

    def handle(self, method, data):
        if method == 'cloud_smoke_export':
            if not self.demo: raise StudioError('此接口仅供离线演示校验。')
            return export_bundle(data, self.store, self.resources, self.store.root / 'cloud-smoke-export.zip')
        if method == 'cloud_check':
            report = analyse_cloud(data, self.store)
            return {key: value for key, value in report.items() if key != 'program'}
        if method == 'export_cloud':
            if not data.get('filename'): return {'cancelled': True}
            return export_bundle(data, self.store, self.resources, data['filename'])
        if method == 'init': return self.settings()
        if method == 'save_room':
            if self.runner and self.runner.is_alive(): raise StudioError('请先停止脚本，再修改目标房间。')
            room = room_code(data['room'])
            if room != self.store.config().get('room'):
                self.capture.stop()
                self.store.update(learned={})
                self.last_state = None
                self.device.observer = Observer()
                self.active_verified = False
            self.store.update(room=room)
            return self.settings()
        if method == 'pick_qr':
            if not data['filename']: return {'cancelled': True}
            import zxingcpp
            from PIL import Image
            try:
                image = Image.open(data['filename'])
                if image.width * image.height > 40_000_000: raise StudioError('图片过大，请裁剪二维码后重试。')
                codes = zxingcpp.read_barcodes(image)
                for code in codes:
                    try: return {'room': room_code(code.text)}
                    except StudioError: pass
                raise StudioError('未识别出房间设备编号。请使用清晰图片或直接粘贴编号。')
            except OSError:
                raise StudioError('无法读取这张图片。') from None
        if method == 'manual_token':
            if self.runner and self.runner.is_alive(): raise StudioError('请先停止脚本，再更换授权。')
            token = data.get('token', '').strip()
            if token.lower().startswith('bearer '): token = token[7:].strip()
            expected = data.get('room', '').strip()
            if self.demo:
                expected = expected or 'H00-00-00-0000-00'
                state = self.device.status(token)
            else:
                response = self.device.request('/me', token=token)
                body = response.get('data')
                aircon = body.get('aircon') if isinstance(body, dict) else None
                if not isinstance(aircon, dict): raise StudioError('这个 Token 尚未绑定空调。请先在官方 App 配对房间。')
                expected = room_code(expected or str(aircon.get('aircon_code', '')))
                state = self.device.status(token, room=expected, payload=response)
            self.capture.stop()
            if expected != self.store.config().get('room'):
                self.store.update(learned={})
                self.device.observer = Observer()
                self.device.observer.sample(state)
            self.store.update(room=expected)
            self.store.secret_set('token', token)
            self.last_state, self.active_verified = state, True
            return {'status': state, 'settings': self.settings()}
        if method == 'show_token':
            token = self.store.token()
            if not token and self.demo: token = 'DEMO-TOKEN-NOT-A-REAL-CREDENTIAL'
            if not token: raise StudioError('本机还没有保存 Token，请先完成授权或直接导入。')
            return {'token': token, 'room': self.store.config().get('room', '')}
        if method == 'status':
            state = self.device.status()
            self.last_state, self.active_verified = state, True
            return state
        if method == 'control':
            if self.runner and self.runner.is_alive(): raise StudioError('脚本正在运行，请先停止脚本再手动控制。')
            result = self.device.control(data['field'], data['value'])
            self.last_state = result
            return result
        if method == 'prepare_capture':
            if self.demo: raise StudioError('演示模式不启动真实网络抓包。')
            if not self.store.config().get('room'): raise StudioError('请先保存房间编号。')
            self.capture_error = ''
            return self.capture.prepare(data['ip'])
        if method == 'firewall': return self.capture.firewall(data.get('remove', False))
        if method == 'start_capture':
            self.capture_error = ''
            return self.capture.start(data.get('mode', 'connect'))
        if method == 'stop_capture':
            result = self.capture.stop()
            return {**result, 'settings': self.settings()}
        if method == 'poll':
            if not self.poll_lock.acquire(False): return {'busy': True}
            try:
                status = self.capture.status()
                token = self.capture.candidate() if status['running'] else None
                captured = None
                if token:
                    try:
                        state = self.device.status(token)
                        self.store.secret_set('token', token)
                        self.last_state, self.active_verified = state, True
                        captured = state
                        if self.capture.mode == 'connect':
                            self.capture.stop()
                            status['running'] = False
                    except StudioError as exc:
                        self.capture_error = str(exc)
                return {'capture': status, 'captured': captured, 'capture_error': self.capture_error,
                        'script_running': bool(self.runner and self.runner.is_alive()),
                        'capabilities': self.device.capabilities(), 'state': self.last_state, 'device_events': self.device.observer.since()[-12:]}
            finally:
                self.poll_lock.release()
        if method == 'connections': return self.settings()['connections']
        if method == 'save_connection':
            name = data.get('name', '').strip()
            kind = data.get('kind')
            if not name or len(name) > 60 or kind not in ('http', 'calendar', 'mqtt'): raise StudioError('请输入连接名称和有效类型。')
            connections = self.store.secrets().get('connections', {})
            old = connections.get(name, {})
            value = {k: v for k, v in data.items() if k in ('kind', 'url', 'token', 'host', 'port', 'topic', 'tls', 'username')}
            if not value.get('token'): value['token'] = old.get('token', '')
            if kind in ('http', 'calendar'):
                from urllib.parse import urlsplit
                parsed = urlsplit(value.get('url', ''))
                if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username: raise StudioError('请输入有效的 HTTP(S) 地址。')
            if kind == 'mqtt' and (not value.get('host') or not value.get('topic')): raise StudioError('MQTT 必须填写服务器和订阅主题。')
            if kind == 'mqtt':
                try: value['port'] = int(value.get('port') or (8883 if value.get('tls') else 1883))
                except (ValueError, TypeError): raise StudioError('MQTT 端口必须是数字。') from None
                if not 1 <= value['port'] <= 65535: raise StudioError('MQTT 端口必须在 1–65535 之间。')
            connections[name] = value
            self.store.secret_set('connections', connections)
            return self.settings()['connections']
        if method == 'remove_connection':
            values = self.store.secrets().get('connections', {})
            values.pop(data['name'], None)
            self.store.secret_set('connections', values)
            return self.settings()['connections']
        if method == 'test_connection':
            name = data['name']
            profile = self.integrations.profile(name)
            kind = profile['kind']
            if kind == 'http': result = self.integrations.http(name, data.get('path', ''))
            elif kind == 'calendar': result = self.integrations.calendar(name, 24)
            elif kind == 'mqtt': result = self.integrations.mqtt(name, data.get('path', ''), threading.Event())
            else: raise StudioError('Unsupported connector type')
            return {'result': result}
        if method == 'timezone':
            from zoneinfo import ZoneInfo
            try: ZoneInfo(data['value'])
            except Exception: raise StudioError('请输入有效时区，例如 Asia/Singapore。') from None
            self.store.update(timezone=data['value'])
            return True
        if method in ('save_script', 'export_script'):
            workspace = {'format': 'HallAirconStudio', 'version': 1, 'workspace': data['workspace'], 'name': data.get('name', 'script'), 'mode': data.get('mode', 'blocks'), 'code': data.get('code', '')}
            text = json.dumps(workspace, ensure_ascii=False, indent=2)
            if len(text) > 1_000_000: raise StudioError('脚本超过 1MB 限制。')
            if method == 'export_script':
                if not data.get('filename'): return {'cancelled': True}
                for secret in (self.store.token(), self.store.config().get('room', '')):
                    if secret and secret in text: raise StudioError('脚本中包含当前凭据或设备编号，请删除后再导出。')
                path = Path(data['filename'])
            else: path = self.store.root / 'workspace.aircon.json'
            atomic_write(path, text)
            return {'saved': True}
        if method in ('load_script', 'import_script'):
            if method == 'import_script' and not data.get('filename'): return {'cancelled': True}
            path = Path(data['filename']) if method == 'import_script' else self.store.root / 'workspace.aircon.json'
            if not path.exists(): return {'empty': True}
            if path.stat().st_size > 1_000_000: raise StudioError('脚本文件超过 1MB 限制。')
            try: value = json.loads(path.read_text(encoding='utf-8'))
            except (ValueError, UnicodeError): raise StudioError('脚本文件不是有效 JSON。') from None
            if value.get('format') != 'HallAirconStudio' or value.get('version') != 1 or not isinstance(value.get('workspace'), dict): raise StudioError('脚本格式或版本不支持。')
            return value
        if method == 'scripts': return self.library.list()
        if method == 'script_get': return self.library.get(data['id'])
        if method == 'script_save': return self.library.save(data)
        if method == 'script_delete':
            self.library.delete(data['id'])
            return self.library.list()
        if method == 'code_preview': return preview(data['source'])
        if method == 'pick_code':
            if not data.get('filename'): return {'cancelled': True}
            path = Path(data['filename'])
            if path.stat().st_size > 200_000: raise StudioError('Python file exceeds 200KB')
            source = path.read_text(encoding='utf-8-sig')
            validate(source)
            return {'source': source, 'workspace': preview(source), 'name': path.stem}
        if method == 'export_code':
            if not data.get('filename'): return {'cancelled': True}
            source = data['source']
            validate(source)
            for secret in (self.store.token(), self.store.config().get('room', '')):
                if secret and secret in source: raise StudioError('Remove account credentials before export')
            atomic_write(Path(data['filename']), source)
            return {'saved': True}
        if method == 'device_events': return self.device.observer.since(data.get('cursor', 0))
        if method == 'run_script':
            with self.script_lock:
                if self.runner and self.runner.is_alive(): raise StudioError('已有脚本正在运行。')
                if not data.get('dry', True) and not self.demo and not self.active_verified: raise StudioError('请先成功刷新并核对设备身份。')
                self.engine = Engine(self.device, self.integrations, self.publish)
                self.engine.trusted_code = bool(data.get('trusted_code', False))
                self.engine.script_id = str(data.get('script_id', 'unsaved'))
                if data.get('mode') == 'code':
                    validate(data.get('code', ''))
                    data['program'] = [{'op': 'custom_code', 'source': data['code'], 'timeout': min(float(data.get('hours', 24)) * 3600, 3600)}]
                self.runner = threading.Thread(target=self.engine.run, args=(data['program'], data.get('dry', True), data.get('hours', 24)), daemon=True)
                self.runner.start()
            return {'started': True}
        if method == 'stop_script':
            if self.engine: self.engine.cancel.set()
            return {'stopping': True}
        if method == 'forget':
            if self.runner and self.runner.is_alive(): raise StudioError('请先停止脚本。')
            self.capture.stop()
            self.store.secret_set('token', '')
            self.store.update(room='')
            self.last_state, self.active_verified = None, False
            self.device.observer = Observer()
            return self.settings()
        raise StudioError('不支持的操作。')

    def shutdown(self):
        if self.engine: self.engine.cancel.set()
        self.capture.stop()
        self.pool.waitForDone(20000)
