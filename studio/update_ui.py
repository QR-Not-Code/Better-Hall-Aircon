"""Qt orchestration: background check/download, explicit consent, external swap."""
import json
import sys
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QThreadPool, QRunnable, QTimer, Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog
from .updater import Updater, UpdateCancelled
from .version import VERSION


class Task(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        self.fn()


class UpdateUI(QObject):
    result = Signal(object)
    progress = Signal(int)
    prepared = Signal(object)

    def __init__(self, window, page, bridge, resources):
        super().__init__(window)
        self.window, self.page, self.bridge = window, page, bridge
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.updater = Updater(bridge.store.root, resources, Path(sys.executable).parent if getattr(sys, 'frozen', False) else None)
        self.busy = False
        self.stopping = False
        self.dialog = None
        self.result.connect(self.checked)
        self.prepared.connect(self.ready)
        self.progress.connect(self.on_progress)

    def text(self, zh, en):
        return en if self.bridge.store.config().get('language') == 'en' else zh

    def check(self, manual=False):
        if self.busy or self.bridge.demo or self.stopping:
            return
        self.busy = True
        self.manual = manual
        def work():
            try:
                self.result.emit({'release': self.updater.check()})
            except Exception:
                self.result.emit({'error': True})
        self.pool.start(Task(work))

    def checked(self, value):
        if self.stopping: return
        self.busy = False
        if value.get('error'):
            if self.manual:
                QMessageBox.information(self.window, self.text('检查更新', 'Check for updates'), self.text('暂时无法连接 GitHub 或获取有效更新包。当前程序可继续使用，请稍后重试。', 'GitHub is unavailable or the release package is incomplete. You can keep using this version and try again later.'))
            return
        release = value.get('release')
        if not release:
            if self.manual:
                QMessageBox.information(self.window, self.text('检查更新', 'Check for updates'), self.text('当前已是最新版本：', 'You are up to date: ') + VERSION)
            return
        prompt = QMessageBox(self.window)
        prompt.setIcon(QMessageBox.Information)
        prompt.setTextFormat(Qt.PlainText)
        prompt.setWindowTitle(self.text('发现新版本', 'Update available'))
        prompt.setText(self.text('是否更新到 ', 'Update to ') + release['version'] + self.text('？', '?'))
        prompt.setInformativeText(self.text('当前版本：', 'Current version: ') + VERSION + '\n' + self.text('下载校验完成后将保存当前草稿副本、停止脚本与抓包、重启程序。空调保持最后状态，本机账号、脚本和证书保留。选择“跳过本次”后下次启动仍可检查。', 'After downloading and verifying, a copy of your draft will be saved, scripts and capture will stop, and the app will restart. The aircon stays in its last state. Your account, scripts and certificates are preserved. Skipping applies only to this check.'))
        prompt.setDetailedText(release['notes'])
        yes = prompt.addButton(self.text('更新并重启', 'Update and restart'), QMessageBox.AcceptRole)
        skip = prompt.addButton(self.text('跳过本次', 'Skip for now'), QMessageBox.RejectRole)
        prompt.setDefaultButton(skip)
        prompt.exec()
        if prompt.clickedButton() is not yes:
            return
        if not self.updater.install:
            QMessageBox.information(self.window, self.text('源码运行模式', 'Source mode'), self.text('源码运行模式请更新源码；自动替换适用于 Windows 打包版。', 'Please update the source checkout. Automatic replacement is supported in the Windows packaged app.'))
            return
        self.busy = True
        self.updater.cancel.clear()
        self.dialog = QProgressDialog(self.text('正在下载并校验更新包…', 'Downloading and verifying the update…'), self.text('取消', 'Cancel'), 0, 100, self.window)
        self.dialog.setWindowTitle(self.text('更新程序', 'Updating'))
        self.dialog.setWindowModality(Qt.WindowModal)
        self.dialog.setAutoClose(False)
        self.dialog.setAutoReset(False)
        self.dialog.canceled.connect(self.updater.cancel.set)
        self.dialog.show()
        def download():
            try:
                self.prepared.emit({'plan': self.updater.prepare(release, self.progress.emit)})
            except UpdateCancelled:
                self.prepared.emit({'cancelled': True})
            except Exception:
                self.prepared.emit({'error': True})
        self.pool.start(Task(download))

    def on_progress(self, value):
        if self.dialog:
            self.dialog.setValue(value)

    def ready(self, value):
        if self.stopping: return
        if self.dialog:
            self.dialog.canceled.disconnect(self.updater.cancel.set)
            self.dialog.close()
            self.dialog = None
        if self.updater.cancel.is_set() or value.get('cancelled'):
            self.busy = False
            return
        if value.get('error'):
            self.busy = False
            QMessageBox.warning(self.window, self.text('更新未完成', 'Update not installed'), self.text('下载、校验或准备失败。原程序未被修改。请确认程序已完整解压到独立文件夹，再检查网络、磁盘空间及安装目录写入权限。', 'Download, verification or preparation failed. Your installation is unchanged. Keep the complete app in its own folder, then check the network, free disk space and write permission.'))
            return
        self.page.runJavaScript('JSON.stringify(typeof documentData === "function" && workspace ? documentData() : null)', lambda snapshot: self.apply(value['plan'], snapshot))

    def apply(self, plan, snapshot):
        try:
            document = json.loads(snapshot or 'null')
            if not isinstance(document, dict):
                raise ValueError('Editor not ready')
            if document.get('code', '').strip() or document.get('workspace', {}).get('blocks', {}).get('blocks'):
                from datetime import datetime
                document['id'] = ''
                document['name'] = ((document.get('name') or self.text('未命名脚本', 'Untitled script'))[:60]
                                    + self.text(' · 更新前草稿 ', ' · Pre-update draft ') + datetime.now().strftime('%Y%m%d-%H%M%S'))
                self.bridge.library.save(document)
            self.updater.launch(plan)
        except Exception:
            self.busy = False
            QMessageBox.warning(self.window, self.text('更新未完成', 'Update not installed'), self.text('未能保存草稿或启动更新助手，程序保持运行。请先手动保存脚本后重试。', 'The draft could not be saved or the update helper could not start. The app remains open. Save your script and try again.'))
            return
        self.bridge.shutdown()
        QApplication.instance().quit()

    def stop(self):
        self.stopping = True
        self.updater.cancel.set()

    def previous_result(self):
        path = self.bridge.store.root / 'update-result.json'
        if not path.exists():
            return
        try:
            value = json.loads(path.read_text(encoding='utf-8-sig'))
            path.unlink()
            if value.get('status') != 'updated':
                QMessageBox.warning(self.window, self.text('上次更新未完成', 'Previous update did not complete'), self.text('更新未能完成。旧版本备份位置：\n', 'The update could not complete. Previous-version backup:\n') + str(value.get('backup', '')))
        except (OSError, ValueError):
            pass
