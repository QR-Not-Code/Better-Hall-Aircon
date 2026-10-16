import json
import math
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from .storage import StudioError
from .observer import Observer

BASE = 'https://apintu-prod.daikinpayu.com'
FIELDS = ('power', 'current_temperature', 'setpoint', 'flap', 'fanstep', 'mode', 'status', 'comm_stat', 'maintenance_mode', 'aircon_type')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def has_identity(value, room):
    if isinstance(value, dict):
        return any(has_identity(v, room) for v in value.values())
    if isinstance(value, list):
        return any(has_identity(v, room) for v in value)
    return isinstance(value, str) and bool(room) and value == room


class Device:
    def __init__(self, store, demo=False):
        self.store, self.demo = store, demo
        self.lock = threading.RLock()
        self.observer = Observer()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.demo_state = dict(power=1, current_temperature=25, setpoint=24, flap='N', fanstep='H', mode='C', status=True, comm_stat=1, maintenance_mode=0, aircon_type=1)

    def request(self, path, fields=None, token=None):
        token = token if token is not None else self.store.token()
        token = token.removeprefix('Bearer ').strip()
        if not token or any(c.isspace() for c in token):
            raise StudioError('还没有有效授权，请先完成连接向导。')
        headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json', 'User-Agent': 'Dart/3.0 (dart:io)'}
        body = None
        if fields is not None:
            body = urllib.parse.urlencode(fields).encode()
            headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=utf-8'
        try:
            with self.opener.open(urllib.request.Request(BASE + path, data=body, headers=headers), timeout=15) as r:
                raw = r.read(1_000_001)
            if len(raw) > 1_000_000:
                raise StudioError('设备响应过大。')
            data = json.loads(raw)
        except urllib.error.HTTPError as e:
            code = e.code
            e.close()
            if code in (401, 402, 403):
                raise StudioError(f'授权被拒绝（HTTP {code}）。请重新获取 Token，或确认账号权限。') from None
            raise StudioError(f'设备服务返回 HTTP {code}；未自动重复发送命令。') from None
        except (OSError, urllib.error.URLError):
            raise StudioError('设备请求网络失败；控制结果可能未知，请先刷新状态。') from None
        except (ValueError, UnicodeError):
            raise StudioError('设备返回了无法识别的数据。') from None
        if not isinstance(data, dict):
            raise StudioError('设备响应格式已变化。')
        meta = data.get('meta')
        if isinstance(meta, dict) and 'status' in meta and str(meta['status']) not in ('200', '201', '202', '204'):
            raise StudioError('服务器报告业务失败，请检查 App 和余额。')
        if data.get('success') is False or data.get('error'):
            raise StudioError('服务器拒绝了这次操作。')
        return data

    def status(self, token=None, room=None, payload=None):
        with self.lock:
            if self.demo:
                return self.observer.sample({**self.demo_state, 'identity_verified': True, 'updated': time.time(), 'demo': True})
            room = self.store.config().get('room', '') if room is None else room
            if not room:
                raise StudioError('请先填写或识别房间二维码。')
            response = payload if payload is not None else self.request('/me', token=token)
            data = response.get('data')
            aircon = data.get('aircon') if isinstance(data, dict) else None
            if not isinstance(aircon, dict) or not has_identity(aircon, room):
                raise StudioError('设备编号与二维码不匹配，已阻止控制。请在官方 App 确认账号绑定。')
            if type(aircon.get('power')) is bool or str(aircon.get('power')) not in ('0', '1'):
                raise StudioError('电源状态格式未知。')
            result = {k: aircon[k] for k in FIELDS if k in aircon and isinstance(aircon[k], (str, int, float, bool, type(None)))}
            if any(isinstance(v, float) and not math.isfinite(v) for v in result.values()):
                raise StudioError('设备返回了无效数值。')
            return self.observer.sample({**result, 'power': int(aircon['power']), 'identity_verified': True, 'updated': time.time(), 'demo': False})

    def capabilities(self):
        result = {'power': ['0', '1'], 'flap': ['N', 'S']}
        for key, values in self.store.config().get('learned', {}).items():
            if key in ('setpoint', 'fanstep', 'mode'):
                result[key] = sorted(set(str(v) for v in values))
        return result

    def control(self, field, value, cancel=None):
        value = str(value)
        if value not in self.capabilities().get(field, []):
            raise StudioError('该操作值尚未验证；请通过向导录制一次官方 App 操作。')
        with self.lock:
            before = self.status()
            if str(before.get(field)) == value:
                return {**before, 'result': 'already_set'}
            self.observer.expect(field, value)
            if self.demo:
                self.demo_state[field] = int(value) if field == 'power' else value
                return {**self.status(), 'result': 'demo'}
            self.request('/v2/ac/control', {field: value})
            for _ in range(6):
                if cancel:
                    if cancel.wait(3):
                        raise StudioError('命令已发送，随后取消状态确认；请刷新状态。')
                else:
                    time.sleep(3)
                state = self.status()
                if str(state.get(field)) == value:
                    return {**state, 'result': 'confirmed'}
            raise StudioError('命令已发送，但未确认目标状态。请检查官方 App 和实际设备。')
