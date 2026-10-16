"""Public GitHub release checks and verified, staged Windows updates.

No account credentials are sent. The running installation is replaced only by
the external helper after this process exits; failures retain the old folder.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from .storage import StudioError, atomic_write
from .version import VERSION, REPOSITORY

ASSET = 'HallAirconStudio-Windows.zip'
MAX_DOWNLOAD = 600 * 1024 * 1024
MAX_UNPACKED = 3 * 1024 * 1024 * 1024
INSTALL_MARKER = Path('_internal/studio/install-marker.json')
INSTALL_ENTRIES = {'hallairconstudio.exe', '_internal', 'source', 'thirdpartynotices',
                   '使用说明.md', '验证记录.md', '模块与代码指南.md', 'github云端运行指南.md'}


def dedicated_install(directory):
    directory = Path(directory)
    try:
        marker = json.loads((directory / INSTALL_MARKER).read_text(encoding='utf-8'))
        return (marker == {'application': 'Better-Hall-Aircon', 'format': 1}
                and (directory / 'HallAirconStudio.exe').is_file()
                and all(entry.name.casefold() in INSTALL_ENTRIES for entry in directory.iterdir())
                and not directory.is_symlink())
    except (OSError, ValueError):
        return False


class UpdateCancelled(Exception):
    pass


def version_tuple(value):
    match = re.fullmatch(r'v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', str(value))
    if not match:
        raise StudioError('更新版本号无效。')
    return tuple(map(int, match.groups()))


def safe_url(url):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443)
            or parsed.hostname not in {'api.github.com', 'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}):
        raise StudioError('更新下载地址不受信任。')
    return url


class GitHubRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Updater:
    def __init__(self, data_root, resources, install=None, opener=None):
        self.data_root, self.resources = Path(data_root), Path(resources)
        self.install = Path(install).resolve() if install else None
        self.opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), GitHubRedirect())
        self.cancel = threading.Event()

    def open(self, url):
        return self.opener.open(urllib.request.Request(safe_url(url), headers={
            'User-Agent': 'Better-Hall-Aircon/' + VERSION,
            'Accept': 'application/vnd.github+json' if url.startswith('https://api.github.com/') else '*/*',
        }), timeout=25)

    def check(self):
        try:
            with self.open(f'https://api.github.com/repos/{REPOSITORY}/releases/latest') as response:
                raw = response.read(1_000_001)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        if len(raw) > 1_000_000:
            raise StudioError('更新信息过大。')
        release = json.loads(raw)
        if release.get('draft') or release.get('prerelease'):
            return None
        if version_tuple(release.get('tag_name')) <= version_tuple(VERSION):
            return None
        assets = {a['name']: a for a in release.get('assets', []) if a.get('state') == 'uploaded'}
        if ASSET not in assets or ASSET.replace('.zip', '.sha256') not in assets:
            raise StudioError('新版本尚未提供完整更新包。')
        archive, checksum = assets[ASSET], assets[ASSET.replace('.zip', '.sha256')]
        if not isinstance(archive.get('size'), int) or not 0 < archive['size'] <= MAX_DOWNLOAD:
            raise StudioError('更新包大小无效。')
        if not re.fullmatch(r'sha256:[a-fA-F0-9]{64}', archive.get('digest') or ''):
            raise StudioError('更新包缺少 SHA-256 校验信息。')
        for asset in (archive, checksum):
            url = safe_url(asset['browser_download_url'])
            prefix = f'https://github.com/{REPOSITORY}/releases/download/'
            if not url.startswith(prefix) or urllib.parse.unquote(urllib.parse.urlsplit(url).path.rsplit('/', 1)[-1]) != asset['name']:
                raise StudioError('更新下载地址不受信任。')
        return {'version': release['tag_name'].lstrip('v'), 'notes': str(release.get('body') or '')[:6000],
                'archive': archive, 'checksum': checksum}

    def download(self, release, destination, progress=lambda value: None):
        checksum_asset = release['checksum']
        with self.open(checksum_asset['browser_download_url']) as response:
            checksum_raw = response.read(4097)
        if len(checksum_raw) > 4096:
            raise StudioError('校验文件无效。')
        match = re.fullmatch(rb'([a-fA-F0-9]{64})[ \t]+\*?HallAirconStudio-Windows\.zip[ \t\r\n]*', checksum_raw)
        if not match or match[1].decode().lower() != release['archive']['digest'][7:].lower():
            raise StudioError('更新包校验信息不一致。')
        if self.cancel.is_set():
            raise UpdateCancelled()
        path = Path(destination)
        received, digest = 0, hashlib.sha256()
        try:
            with self.open(release['archive']['browser_download_url']) as response, path.open('wb') as output:
                while chunk := response.read(256 * 1024):
                    if self.cancel.is_set():
                        raise UpdateCancelled()
                    received += len(chunk)
                    if received > release['archive']['size'] or received > MAX_DOWNLOAD:
                        raise StudioError('更新包大小与发布信息不一致。')
                    output.write(chunk)
                    digest.update(chunk)
                    progress(min(90, int(received / release['archive']['size'] * 90)))
            if received != release['archive']['size'] or digest.hexdigest() != match[1].decode().lower():
                raise StudioError('更新包校验失败，原程序未被修改。')
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    def unpack(self, archive, directory):
        root = Path(directory).resolve()
        root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as bundle:
            entries = bundle.infolist()
            if len(entries) > 20000 or sum(x.file_size for x in entries) > MAX_UNPACKED:
                raise StudioError('更新包解压大小超出限制。')
            seen = set()
            for entry in entries:
                path = PurePosixPath(entry.filename)
                parts = path.parts
                reserved = r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?'
                if (not parts or parts[0] != 'HallAirconStudio' or path.is_absolute()
                        or '\\' in entry.orig_filename or any(p in {'.', '..'} or ':' in p or p.endswith((' ', '.'))
                                                          or re.fullmatch(reserved, p) for p in parts)
                        or stat.S_ISLNK(entry.external_attr >> 16)):
                    raise StudioError('更新包包含不安全路径。')
                normalized = str(path).casefold()
                if normalized in seen:
                    raise StudioError('更新包包含重复路径。')
                seen.add(normalized)
                target = root.joinpath(*parts)
                if not target.resolve().is_relative_to(root):
                    raise StudioError('更新包包含不安全路径。')
                if any(p.casefold() in {'vault.bin', 'settings.json', 'scripts.json', 'phone.conf', 'wireguard.conf', '.secrets', '.demo-data', 'capture'} for p in parts):
                    raise StudioError('更新包不应包含用户数据。')
            for entry in entries:
                if self.cancel.is_set():
                    raise UpdateCancelled()
                target = root.joinpath(*PurePosixPath(entry.filename).parts)
                if entry.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.open(entry) as incoming, target.open('wb') as outgoing:
                        shutil.copyfileobj(incoming, outgoing, length=256 * 1024)
        candidate = root / 'HallAirconStudio'
        if not dedicated_install(candidate):
            raise StudioError('更新包缺少程序文件。')
        return candidate

    def prepare(self, release, progress=lambda value: None):
        if not self.install or self.install.parent == self.install or not (self.install / 'HallAirconStudio.exe').is_file():
            raise StudioError('源码运行模式无法自动替换程序，请使用打包版。')
        if not dedicated_install(self.install) or self.data_root.resolve().is_relative_to(self.install):
            raise StudioError('请把完整程序放在独立文件夹内，再执行自动更新。')
        # A sibling permits same-volume directory renames and rollback. No UAC.
        staging = self.install.parent / ('.HallAircon-update-' + uuid.uuid4().hex)
        staging.mkdir()
        archive = staging / ASSET
        self.download(release, archive, progress)
        candidate = self.unpack(archive, staging / 'payload')
        archive.unlink()
        self.data_root.mkdir(parents=True, exist_ok=True)
        helper = staging / 'apply-update.ps1'
        shutil.copy2(self.resources / 'studio' / 'update_helper.ps1', helper)
        plan = {'pid': os.getpid(), 'install': str(self.install), 'candidate': str(candidate),
                'backup': str(self.install.parent / (self.install.name + '.previous-' + uuid.uuid4().hex[:8])),
                'staging': str(staging), 'result': str(self.data_root / 'update-result.json'),
                'ready': str(staging / 'helper-ready'), 'version': release['version']}
        atomic_write(staging / 'plan.json', json.dumps(plan))
        progress(100)
        return staging / 'plan.json'

    def launch(self, plan):
        if os.name != 'nt':
            raise StudioError('自动更新仅支持 Windows。')
        plan = Path(plan).resolve()
        helper = plan.parent / 'apply-update.ps1'
        executable = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        process = subprocess.Popen([str(executable), '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden',
                                    '-ExecutionPolicy', 'Bypass', '-File', str(helper), '-PlanPath', str(plan)],
                                   cwd=plan.parent, creationflags=subprocess.CREATE_NO_WINDOW)
        # The helper captures this process before we quit, avoiding PID reuse races.
        for _ in range(100):
            if (plan.parent / 'helper-ready').exists():
                return
            if process.poll() is not None:
                break
            time.sleep(.05)
        raise StudioError('更新助手未能启动，原程序保持运行。')
