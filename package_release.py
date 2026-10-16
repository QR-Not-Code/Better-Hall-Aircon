"""Create a credential-free portable archive with documentation and source."""
import importlib.metadata as metadata
import os
from pathlib import Path
import shutil
import zipfile

root = Path(__file__).resolve().parent
release = root / os.environ.get('HALLAIRCON_BUILD_DIST', 'dist') / 'HallAirconStudio'
if not (release / 'HallAirconStudio.exe').exists():
    raise SystemExit('Build the executable first.')
shutil.copy2(root / 'README.md', release / '使用说明.md')
shutil.copy2(root / 'VERIFICATION.md', release / '验证记录.md')
shutil.copy2(root / 'MODULES.md', release / '模块与代码指南.md')
shutil.copy2(root / 'CLOUD.md', release / 'GitHub云端运行指南.md')
licenses = release / 'ThirdPartyNotices'
licenses.mkdir(exist_ok=True)
if (root / 'licenses').exists():
    for license_file in (root / 'licenses').iterdir():
        if license_file.is_file(): shutil.copy2(license_file, licenses / license_file.name)
names = ['PySide6', 'mitmproxy', 'mitmproxy-rs', 'mitmproxy-windows', 'qrcode', 'Pillow', 'zxing-cpp', 'icalendar', 'recurring-ical-events', 'paho-mqtt', 'cryptography', 'aioquic', 'pyOpenSSL', 'argon2-cffi', 'tzdata', 'tornado', 'Brotli', 'h2', 'hpack', 'hyperframe', 'wsproto', 'h11', 'msgpack', 'sortedcontainers', 'publicsuffix2', 'ruamel.yaml', 'pyparsing', 'pyperclip', 'urwid', 'zstandard', 'ldap3', 'pydivert', 'pylsqpack', 'service-identity', 'asgiref']
index = ['Third-party software bundled with Hall Aircon Studio.\n', 'Blockly 13.4.0: Apache-2.0. See _internal/ui/vendor/LICENSE.\n', 'Qt / PySide6: LGPLv3 / GPLv3 / commercial options. This distribution uses the open-source dynamic libraries.\n', 'Qt sources and licensing: https://code.qt.io/ and https://doc.qt.io/qt-6/licensing.html\n', 'Dynamic Qt libraries can be replaced under _internal/PySide6. No application code prevents replacement.\n', 'Chromium and Qt WebEngine third-party credits: https://doc.qt.io/qt-6/qtwebengine-licensing.html\n']
for name in names:
    try: dist = metadata.distribution(name)
    except metadata.PackageNotFoundError: continue
    index.append(f'\n{name} {dist.version}\n')
    for item in dist.files or []:
        item_path = Path(str(item))
        if item_path.is_absolute() or '..' in item_path.parts: continue
        if not any(part.lower().startswith(('license', 'copying', 'notice')) for part in item_path.parts): continue
        source = dist.locate_file(item)
        if source.is_file():
            target = licenses / name / item_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
index.append('\nOriginal application source is included in Source/.\n')
(licenses / 'INDEX.txt').write_text(''.join(index), encoding='utf-8')
source_root = release / 'Source'
for directory in ['studio', 'ui', 'tests']:
    for source in (root / directory).rglob('*'):
        if not source.is_file() or '__pycache__' in source.parts: continue
        target = source_root / source.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
for name in ['main.py', 'requirements.txt', 'build.py', 'README.md', 'VERIFICATION.md', 'MODULES.md', 'CLOUD.md']:
    shutil.copy2(root / name, source_root / name)
archive = root / os.environ.get('HALLAIRCON_RELEASE_ARCHIVE', 'HallAirconStudio-Windows.zip')
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for path in sorted(release.rglob('*')):
        if not path.is_file(): continue
        if any(part in {'.demo-data', '__pycache__', '.pytest_cache'} for part in path.relative_to(release).parts): continue
        if path.name in {'vault.bin', 'token.txt', 'room.txt', 'wireguard.conf', 'phone.conf'}:
            raise SystemExit('Refusing to package a private data file.')
        z.write(path, Path('HallAirconStudio') / path.relative_to(release))
print('Portable archive:', archive.name, 'MB:', round(archive.stat().st_size / 1_000_000, 1))
import hashlib
checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
archive.with_suffix('.sha256').write_text(checksum + '  ' + archive.name + '\n', encoding='utf-8')
