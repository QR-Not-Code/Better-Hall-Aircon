import base64
import ctypes
import io
import ipaddress
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from .storage import StudioError, atomic_write, protect


class CaptureManager:
    def __init__(self, store, resources):
        self.store, self.resources = store, Path(resources)
        self.process = None
        self.directory = store.root / 'capture'
        self.directory.mkdir(exist_ok=True)
        self.last_candidate = None
        self.mode = 'connect'
        self.last_error = ''
        self.ip = ''
        self.offset = 0
        self.learned = {}

    @staticmethod
    def ips():
        found = {x[4][0] for x in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
        return sorted((x for x in found if not x.startswith(('127.', '169.254.'))), key=lambda x: (x != '192.168.137.1', x))

    def prepare(self, ip, port=51820):
        if self.process and self.process.poll() is None:
            raise StudioError('请先停止现有抓包，再重新准备连接。')
        import mitmproxy_rs.wireguard as wg
        from mitmproxy import certs
        import qrcode
        try:
            address = ipaddress.ip_address(ip)
            if address.version != 4 or not address.is_private or address.is_loopback or address.is_unspecified:
                raise ValueError()
        except ValueError:
            raise StudioError('请选择电脑的局域网 IPv4 地址。') from None
        if ip not in self.ips():
            raise StudioError('这个地址不属于当前电脑，请刷新地址列表。')
        self.ip = ip
        self.port = int(port)
        certs.CertStore.from_store(self.directory, 'mitmproxy', 2048)
        keyfile = self.directory / 'wireguard.conf'
        if not keyfile.exists():
            atomic_write(keyfile, json.dumps({'server_key': wg.genkey(), 'client_key': wg.genkey()}))
        keys = json.loads(keyfile.read_text())
        profile = ('[Interface]\nPrivateKey = ' + keys['client_key'] + '\nAddress = 10.0.0.1/32\nDNS = 10.0.0.53\n\n[Peer]\nPublicKey = ' + wg.pubkey(keys['server_key']) + f'\nAllowedIPs = 0.0.0.0/0\nEndpoint = {ip}:{self.port}\nPersistentKeepalive = 25\n')
        atomic_write(self.directory / 'phone.conf', profile)
        buffer = io.BytesIO()
        qrcode.make(profile).save(buffer, format='PNG')
        self.qr = 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()
        self.store.update(ip=ip)
        return {'ip': ip, 'port': self.port, 'qr': self.qr}

    def firewall(self, remove=False):
        if os.name != 'nt': raise StudioError('自动防火墙配置仅支持 Windows。')
        if not self.ip:
            self.ip = self.store.config().get('ip', '')
        if not self.ip: raise StudioError('请先选择热点地址并准备连接。')
        subnet = str(ipaddress.ip_network(self.ip + '/24', strict=False))
        script = "$ErrorActionPreference='Stop'; "
        if remove:
            script += "Get-NetFirewallRule -Name 'HallAirconStudio-Capture' -ErrorAction SilentlyContinue | Remove-NetFirewallRule; "
        else:
            script += "Get-NetFirewallRule -Name 'HallAirconStudio-Capture' -ErrorAction SilentlyContinue | Remove-NetFirewallRule; "
            script += f"New-NetFirewallRule -Name 'HallAirconStudio-Capture' -DisplayName 'Hall Aircon Studio phone capture' -Direction Inbound -Action Allow -Protocol UDP -LocalPort {int(getattr(self, 'port', 51820))} -LocalAddress {self.ip} -RemoteAddress {subnet} -Profile Any | Out-Null; "
        flag = self.directory / 'firewall-result.txt'
        flag.unlink(missing_ok=True)
        script = 'try { ' + script + f"Set-Content -LiteralPath '{str(flag).replace(chr(39), chr(39)*2)}' -Value OK }} catch {{ Set-Content -LiteralPath '{str(flag).replace(chr(39), chr(39)*2)}' -Value ERROR }}"
        encoded = base64.b64encode(script.encode('utf-16-le')).decode()
        result = ctypes.windll.shell32.ShellExecuteW(None, 'runas', 'powershell.exe', '-NoProfile -WindowStyle Hidden -EncodedCommand ' + encoded, None, 0)
        if result <= 32: raise StudioError('未获得管理员权限。可稍后重试防火墙配置。')
        return {'requested': True}

    def start(self, mode='connect'):
        if self.process and self.process.poll() is None:
            self.mode = mode
            return {'running': True}
        if not self.ip: raise StudioError('请先准备连接。')
        self.mode, self.last_candidate, self.last_error = mode, None, ''
        for name in ('ready', 'phone-seen', 'candidate.bin', 'events.jsonl'):
            (self.directory / name).unlink(missing_ok=True)
        self.offset = 0
        self.learned = {}
        arguments = ['--mode', 'wireguard', '--listen-host', self.ip, '--listen-port', str(self.port), '--set', 'confdir=' + str(self.directory), '--set', 'flow_detail=0', '--set', 'termlog_verbosity=error', '--allow-hosts', r'^(apintu-prod\.daikinpayu\.com|mitm\.it)(:[0-9]+)?$', '-s', str(self.resources / 'studio' / 'capture_addon.py')]
        executable = [sys.executable, '--capture-engine'] if getattr(sys, 'frozen', False) else [sys.executable, str(self.resources / 'main.py'), '--capture-engine']
        self.log_handle = (self.directory / 'engine.log').open('w', encoding='utf-8')
        self.process = subprocess.Popen(executable + arguments, cwd=self.resources, stdout=self.log_handle, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return {'running': True}

    def status(self):
        running = bool(self.process and self.process.poll() is None)
        events = []
        path = self.directory / 'events.jsonl'
        if path.exists():
            lines = path.read_text(encoding='utf-8').splitlines()
            if len(lines) < self.offset: self.offset = 0
            for line in lines[self.offset:]:
                try: events.append(json.loads(line))
                except ValueError: continue
            self.offset = len(lines)
        for event in events:
            if event.get('kind') == 'learn':
                for key, value in event['fields'].items():
                    self.learned.setdefault(key, set()).add(value)
        phone = self.directory / 'phone-seen'
        last = float(phone.read_text()) if phone.exists() else 0
        flag = self.directory / 'firewall-result.txt'
        return {'running': running, 'ready': running and (self.directory / 'ready').exists(), 'phone_recent': time.time() - last < 60, 'last_phone': last,
                'firewall': flag.read_text(encoding='utf-8-sig').strip() if flag.exists() else 'pending', 'events': events,
                'error': '抓包引擎已退出，请检查端口占用或运行环境。' if self.process and not running else ''}

    def candidate(self):
        file = self.directory / 'candidate.bin'
        if not file.exists(): return None
        raw = file.read_bytes()
        if raw == self.last_candidate: return None
        self.last_candidate = raw
        return protect(raw, True).decode()

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try: self.process.wait(timeout=5)
            except subprocess.TimeoutExpired: self.process.kill()
        if hasattr(self, 'log_handle'): self.log_handle.close()
        learned = self.store.config().get('learned', {})
        for key, values in self.learned.items():
            learned[key] = sorted(set(learned.get(key, [])) | values)
        self.store.update(learned=learned)
        (self.directory / 'candidate.bin').unlink(missing_ok=True)
        return {'stopped': True, 'learned': learned}
