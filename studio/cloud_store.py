"""Headless secrets and encrypted GitHub-backed checkpoints. No desktop imports."""
import base64
import copy
import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from .storage import StudioError


class CloudStore:
    def __init__(self, config, state=None, environment=None):
        self.environment = os.environ if environment is None else environment
        self.state = state if state is not None else {}
        self.lock = threading.RLock()
        self._config = copy.deepcopy(config)
        self._config['room'] = self.environment.get('AIRCON_EXPECTED_ROOM', '').strip()
        try:
            connections = json.loads(self.environment.get('AIRCON_CONNECTIONS_JSON') or '{}')
            if not isinstance(connections, dict): raise ValueError()
            for profile in connections.values():
                if not isinstance(profile, dict) or profile.get('kind') not in ('http', 'mqtt', 'calendar'): raise ValueError()
        except (ValueError, TypeError):
            raise StudioError('AIRCON_CONNECTIONS_JSON 格式无效。') from None
        self.connections = connections

    def config(self): return copy.deepcopy(self._config)
    def token(self):
        value = self.environment.get('AIRCON_TOKEN', '').strip()
        return value[7:].strip() if value.lower().startswith('bearer ') else value
    def secrets(self):
        return {'token': self.token(), 'connections': copy.deepcopy(self.connections),
                'script_memory': copy.deepcopy(self.state.get('script_memory', {}))}

    def secret_set(self, key, value):
        if key != 'script_memory': raise StudioError('云端不允许修改账号凭据。')
        self.state[key] = copy.deepcopy(value)


class GitHubCheckpoint:
    branch = 'aircon-state'

    def __init__(self, identifier, environment=None):
        env = os.environ if environment is None else environment
        self.repository = env.get('GITHUB_REPOSITORY', '')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', self.repository):
            raise StudioError('缺少有效的 GITHUB_REPOSITORY。')
        if not re.fullmatch(r'[a-f0-9]{16}', identifier): raise StudioError('云端脚本标识无效。')
        self.path = f'.aircon-state/{identifier}.bin'
        self.token = env.get('GITHUB_TOKEN', '')
        self.key = env.get('AIRCON_STATE_KEY', '')
        if not self.token: raise StudioError('缺少 GITHUB_TOKEN。')
        from cryptography.fernet import Fernet
        try: self.cipher = Fernet(self.key.encode('ascii'))
        except (ValueError, UnicodeError): raise StudioError('请将有效 Fernet 密钥配置为 AIRCON_STATE_KEY。') from None
        self.sha = None
        self.branch_ready = False

    def request(self, endpoint, method='GET', data=None, missing=False):
        from .device import NoRedirect
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        request = urllib.request.Request('https://api.github.com/repos/' + self.repository + endpoint,
            data=None if data is None else json.dumps(data).encode(), method=method,
            headers={'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'HallAirconStudio', 'Content-Type': 'application/json'})
        try:
            with opener.open(request, timeout=20) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000: raise StudioError('GitHub 状态响应过大。')
            return json.loads(raw)
        except urllib.error.HTTPError as error:
            code = error.code
            error.close()
            if missing and code == 404: return None
            raise StudioError(f'GitHub 状态读写失败（HTTP {code}）；检查仓库写权限、分支保护和额度。') from None
        except (OSError, ValueError, urllib.error.URLError):
            raise StudioError('无法读写 GitHub 进度，已阻止继续控制设备。') from None

    def load(self):
        result = self.request('/contents/' + self.path + '?ref=' + self.branch, missing=True)
        if result is None: return None
        self.sha = result['sha']
        self.branch_ready = True
        from cryptography.fernet import InvalidToken
        try:
            encrypted = base64.b64decode(result['content'])
            state = json.loads(self.cipher.decrypt(encrypted))
            if not isinstance(state, dict): raise ValueError()
            return state
        except (InvalidToken, ValueError, KeyError):
            raise StudioError('云端进度无法解密。请恢复原 AIRCON_STATE_KEY，勿直接覆盖已有进度。') from None

    def ensure_branch(self):
        if self.branch_ready: return
        existing = self.request('/git/ref/heads/' + self.branch, missing=True)
        if existing is None:
            repo = self.request('')
            branch = urllib.parse.quote(repo['default_branch'], safe='')
            reference = self.request('/git/ref/heads/' + branch)
            self.request('/git/refs', 'POST', {'ref': 'refs/heads/' + self.branch, 'sha': reference['object']['sha']})
        self.branch_ready = True

    def save(self, state):
        self.ensure_branch()
        raw = json.dumps(state, ensure_ascii=False, allow_nan=False).encode()
        if len(raw) > 500_000: raise StudioError('云端进度超过 500KB，请减少变量或事件数据。')
        payload = {'message': 'Update encrypted aircon checkpoint', 'branch': self.branch,
                   'content': base64.b64encode(self.cipher.encrypt(raw)).decode('ascii')}
        if self.sha: payload['sha'] = self.sha
        result = self.request('/contents/' + self.path, 'PUT', payload)
        self.sha = result['content']['sha']
