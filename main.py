import sys
from pathlib import Path

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))

if '--code-engine' in sys.argv:
    from studio.code_runtime import worker
    worker()
    raise SystemExit()

if '--capture-engine' in sys.argv:
    from mitmproxy.tools.main import mitmdump
    index = sys.argv.index('--capture-engine')
    mitmdump(sys.argv[index + 1:])
    raise SystemExit()

from PySide6.QtCore import QUrl, QTimer, Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineUrlRequestInterceptor
from PySide6.QtWebEngineWidgets import QWebEngineView
from studio.bridge import Bridge
from studio.storage import Store


class LocalOnly(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        if info.requestUrl().scheme() not in ('file', 'qrc', 'data', 'about', 'blob'):
            info.block(True)


class Page(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line, source):
        if '--smoke' in sys.argv:
            print(f'JS line {line}: {message}', flush=True)

    def acceptNavigationRequest(self, url, kind, main):
        return url.scheme() in ('file', 'qrc', 'data', 'about')


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Hall Aircon Studio')
    app.setOrganizationName('HallAirconStudio')
    window = QMainWindow()
    window.setWindowTitle('Hall Aircon Studio · 宿舍空调工作台')
    window.resize(1440, 940)
    window.setMinimumSize(1080, 730)
    view = QWebEngineView(window)
    page = Page(view)
    view.setPage(page)
    interceptor = LocalOnly(page)
    page.profile().setUrlRequestInterceptor(interceptor)
    demo = '--demo' in sys.argv
    store = Store(ROOT / '.demo-data' if demo else None)
    bridge = Bridge(store, ROOT, window, demo)
    from studio.update_ui import UpdateUI
    from studio.version import VERSION
    updater = UpdateUI(window, page, bridge, ROOT)
    bridge.updater = updater
    bridge.language_changed.connect(lambda language: window.setWindowTitle('Better Hall Aircon ' + VERSION + (' · Aircon workspace' if language == 'en' else ' · 宿舍空调工作台')))
    bridge.language_changed.emit(store.config().get('language', 'zh-CN'))
    channel = QWebChannel(page)
    channel.registerObject('backend', bridge)
    page.setWebChannel(channel)
    window.setCentralWidget(view)
    view.setUrl(QUrl.fromLocalFile(str(ROOT / 'ui' / 'index.html')))
    def close(event):
        running = bridge.runner and bridge.runner.is_alive()
        english = store.config().get('language') == 'en'
        if running and QMessageBox.question(window, 'Stop script and quit?' if english else '停止脚本并退出？', 'Quitting stops the script. The aircon stays in its last state.' if english else '退出会停止当前脚本。空调保持最后状态。') != QMessageBox.Yes:
            event.ignore()
            return
        updater.stop()
        bridge.shutdown()
        event.accept()
    window.closeEvent = close
    window.show()
    if not demo and '--smoke' not in sys.argv:
        QTimer.singleShot(2500, updater.previous_result)
        QTimer.singleShot(3500, updater.check)
    if '--smoke' in sys.argv:
        def smoke():
            page.runJavaScript('JSON.stringify(window.smokeTest ? window.smokeTest() : ({error:"frontend not ready"}))', lambda value: finish(value))
        def finish(value):
            import json
            output = ROOT / '.demo-data' / 'smoke.json'
            output.write_text(value if isinstance(value, str) and value else json.dumps(value, ensure_ascii=False), encoding='utf-8')
            view.grab().save(str(ROOT / '.demo-data' / 'dashboard.png'))
            page.runJavaScript("navigate('setup');setConnectRoute('capture');")
            QTimer.singleShot(1000, capture_guide)
        def capture_guide():
            view.grab().save(str(ROOT / '.demo-data' / 'setup-guide.png'))
            page.runJavaScript("setConnectRoute('direct');")
            QTimer.singleShot(700, capture_direct)
        def capture_direct():
            view.grab().save(str(ROOT / '.demo-data' / 'direct-token.png'))
            page.runJavaScript("window.smokeConnection().then(r=>window.connectionSmokeResult=r).catch(e=>window.connectionSmokeResult={error:e.message});")
            QTimer.singleShot(1800, capture_connection)
        def capture_connection():
            page.runJavaScript('JSON.stringify(window.connectionSmokeResult)', save_connection_result)
        def save_connection_result(value):
            (ROOT / '.demo-data' / 'connection-smoke.json').write_text(value or '{}', encoding='utf-8')
            view.grab().save(str(ROOT / '.demo-data' / 'token-success.png'))
            page.runJavaScript("document.getElementById('token-dialog').close();navigate('scripts');")
            QTimer.singleShot(700, capture_scripts)
        def capture_scripts():
            page.runJavaScript('JSON.stringify(window.smokeLogic())', lambda value: (ROOT / '.demo-data' / 'logic-smoke.json').write_text(value or '{}', encoding='utf-8'))
            view.grab().save(str(ROOT / '.demo-data' / 'scripts.png'))
            page.runJavaScript("window.smokeLibrary().then(r=>window.librarySmokeResult=r).catch(e=>window.librarySmokeResult={error:e.message});")
            QTimer.singleShot(6500, finish_library)
        def finish_library():
            page.runJavaScript('JSON.stringify(window.librarySmokeResult)', lambda value: (ROOT / '.demo-data' / 'library-smoke.json').write_text(value or '{}', encoding='utf-8'))
            QTimer.singleShot(300, finish_all)
        def finish_all():
            page.runJavaScript("window.smokeCloud().then(r=>window.cloudSmokeResult=r).catch(e=>window.cloudSmokeResult={error:e.message});")
            QTimer.singleShot(1500, finish_cloud)
        def finish_cloud():
            view.grab().save(str(ROOT / '.demo-data' / 'cloud-export.png'))
            page.runJavaScript('JSON.stringify(window.cloudSmokeResult)', lambda value: (ROOT / '.demo-data' / 'cloud-smoke.json').write_text(value or '{}', encoding='utf-8'))
            page.runJavaScript("document.getElementById('cloud-dialog').close();window.smokeLanguage().then(r=>window.languageSmokeResult=r).catch(e=>window.languageSmokeResult={error:e.message});")
            QTimer.singleShot(800, finish_language)
        def finish_language():
            page.runJavaScript('JSON.stringify(window.languageSmokeResult)', lambda value: (ROOT / '.demo-data' / 'language-smoke.json').write_text(value or '{}', encoding='utf-8'))
            page.runJavaScript("applyLanguage('en');navigate('dashboard');")
            QTimer.singleShot(500, capture_english)
        def capture_english():
            view.grab().save(str(ROOT / '.demo-data' / 'english-dashboard.png'))
            page.runJavaScript("navigate('setup');setConnectRoute('capture');")
            QTimer.singleShot(500, capture_english_guide)
        def capture_english_guide():
            view.grab().save(str(ROOT / '.demo-data' / 'english-guide.png'))
            page.runJavaScript("navigate('scripts');")
            QTimer.singleShot(500, capture_english_scripts)
        def capture_english_scripts():
            view.grab().save(str(ROOT / '.demo-data' / 'english-scripts.png'))
            page.runJavaScript('JSON.stringify(window.smokeTest())', lambda value: (ROOT / '.demo-data' / 'english-blocks-smoke.json').write_text(value or '{}', encoding='utf-8'))
            QTimer.singleShot(400, close_smoke)
        def close_smoke():
            bridge.shutdown()
            app.quit()
        QTimer.singleShot(8000, smoke)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
