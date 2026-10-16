"""Build a portable Windows directory. Never includes user settings or capture data."""
from pathlib import Path
import os
import PyInstaller.__main__
from studio.cloud_export import RUNTIME

root = Path(__file__).resolve().parent
PyInstaller.__main__.run([
    str(root / 'main.py'), '--name', 'HallAirconStudio', '--onedir', '--windowed', '--noconfirm', '--clean',
    '--distpath', str(root / os.environ.get('HALLAIRCON_BUILD_DIST', 'dist')), '--workpath', str(root / 'build'), '--specpath', str(root / 'build'),
    '--add-data', str(root / 'ui') + ';ui',
    '--add-data', str(root / 'studio' / 'capture_addon.py') + ';studio',
    '--add-data', str(root / 'studio' / 'update_helper.ps1') + ';studio',
    '--add-data', str(root / 'studio' / 'install-marker.json') + ';studio',
    '--add-data', str(root / 'CLOUD.md') + ';.',
    *[argument for name in RUNTIME for argument in ('--add-data', str(root / 'studio' / name) + ';studio')],
    '--collect-all', 'mitmproxy', '--collect-all', 'mitmproxy_rs', '--collect-all', 'mitmproxy_windows',
    '--collect-data', 'tzdata', '--collect-data', 'icalendar',
    '--hidden-import', 'paho.mqtt.client', '--hidden-import', 'zxingcpp', '--hidden-import', 'qrcode',
    '--hidden-import', 'PIL.Image', '--hidden-import', 'recurring_ical_events',
    '--exclude-module', 'PyQt6', '--exclude-module', 'PyQt5', '--exclude-module', 'PySide2',
    '--exclude-module', 'tkinter', '--exclude-module', 'matplotlib', '--exclude-module', 'pandas',
    '--exclude-module', 'scipy', '--exclude-module', 'IPython', '--exclude-module', 'pytest',
    '--exclude-module', 'numpy', '--exclude-module', 'numba', '--exclude-module', 'torch',
])
