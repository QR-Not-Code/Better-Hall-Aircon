import base64
import ctypes
import json
import os
import re
import threading
from pathlib import Path


class StudioError(Exception):
    pass


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_bytes(content if isinstance(content, bytes) else content.encode('utf-8'))
    temporary.replace(path)


def protect(data, decrypt=False):
    if os.name != 'nt':
        raise StudioError('凭据加密需要 Windows。')
    class Blob(ctypes.Structure):
        _fields_ = [('size', ctypes.c_ulong), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    if decrypt:
        ok = ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    else:
        ok = ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source), 'HallAirconStudio', None, None, None, 1, ctypes.byref(target))
    if not ok:
        raise StudioError('Windows 凭据加密失败，或该凭据不属于当前 Windows 用户。')
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree(target.data)


class Store:
    def __init__(self, root=None):
        self.root = Path(root or Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'HallAirconStudio')
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def config(self):
        p = self.root / 'settings.json'
        return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {'room': '', 'ip': '', 'timezone': 'Asia/Singapore', 'learned': {}}

    def update(self, **values):
        with self.lock:
            current = self.config()
            current.update(values)
            atomic_write(self.root / 'settings.json', json.dumps(current, ensure_ascii=False, indent=2))
            return current

    def secrets(self):
        p = self.root / 'vault.bin'
        return json.loads(protect(p.read_bytes(), True)) if p.exists() else {}

    def secret_set(self, key, value):
        with self.lock:
            values = self.secrets()
            values[key] = value
            atomic_write(self.root / 'vault.bin', protect(json.dumps(values).encode()))

    def token(self):
        return self.secrets().get('token', '')

    def expiry(self):
        token = self.token()
        try:
            payload = token.split('.')[1]
            claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
            return {'expires': claims.get('exp'), 'issued': claims.get('iat'), 'verified': False}
        except (IndexError, ValueError, TypeError):
            return {'expires': None, 'issued': None, 'verified': False}


def room_code(value):
    value = value.strip()
    if not re.fullmatch(r'[A-Za-z0-9]+(?:-[A-Za-z0-9]+){2,8}', value):
        raise StudioError('请输入二维码中的完整设备编号，例如 H00-00-00-0000-00；不要输入网页地址。')
    return value
