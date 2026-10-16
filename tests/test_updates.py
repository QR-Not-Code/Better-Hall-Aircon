import hashlib
import io
import json
from pathlib import Path
import stat
from unittest.mock import Mock
import zipfile
import pytest
from studio.storage import StudioError
from studio.updater import Updater, UpdateCancelled, version_tuple, safe_url, GitHubRedirect, ASSET, dedicated_install, INSTALL_MARKER
from studio.version import VERSION, REPOSITORY


def payload(version='99.0.0', data=b'archive'):
    base = f'https://github.com/{REPOSITORY}/releases/download/v{version}/'
    return {'tag_name':'v'+version, 'body':'Release notes', 'assets':[
        {'name':ASSET,'state':'uploaded','browser_download_url':base+ASSET,'size':len(data),'digest':'sha256:'+hashlib.sha256(data).hexdigest()},
        {'name':ASSET.replace('.zip','.sha256'),'state':'uploaded','browser_download_url':base+ASSET.replace('.zip','.sha256')}]}


def checker(tmp_path, release):
    updater = Updater(tmp_path, tmp_path)
    updater.open = Mock(return_value=io.BytesIO(json.dumps(release).encode()))
    return updater


def test_versions_compare_numerically_and_skip_current_older_preview(tmp_path):
    assert version_tuple('v1.10.0') > version_tuple('1.9.9')
    for version in ('0.1.0',VERSION):
        assert checker(tmp_path,payload(version)).check() is None
    for flag in ('draft','prerelease'):
        release=payload(); release[flag]=True
        assert checker(tmp_path,release).check() is None
    for value in ('1.2','v1.2.3-beta','v01.2.3','malicious'):
        with pytest.raises(StudioError): version_tuple(value)


def test_only_fixed_repo_release_assets_with_hash_are_offered(tmp_path):
    assert checker(tmp_path,payload()).check()['version']=='99.0.0'
    for mutation in ('url','digest','size','missing'):
        release=payload()
        if mutation=='url':release['assets'][0]['browser_download_url']='https://github.com/attacker/repo/releases/download/v99.0.0/'+ASSET
        if mutation=='digest':release['assets'][0]['digest']=None
        if mutation=='size':release['assets'][0]['size']=999999999999
        if mutation=='missing':release['assets'].pop()
        with pytest.raises(StudioError):checker(tmp_path,release).check()


@pytest.mark.parametrize('url',['http://github.com/a','https://evil.example/a','https://github.com@evil.example/a','https://github.com:444/a','file:///C:/test'])
def test_redirects_cannot_escape_github_https(url):
    with pytest.raises(StudioError):safe_url(url)
    with pytest.raises(StudioError):GitHubRedirect().redirect_request(None,None,302,'',{},url)


def test_download_stream_hash_size_checksum_and_cancel(tmp_path):
    content=b'valid archive bytes'; release=payload(data=content)
    updater=checker(tmp_path,release); offered=updater.check()
    checksum=(hashlib.sha256(content).hexdigest()+'  '+ASSET+'\n').encode()
    output=tmp_path/'download.zip'; progress=[]
    updater.open=Mock(side_effect=[io.BytesIO(checksum),io.BytesIO(content)])
    updater.download(offered,output,progress.append)
    assert output.read_bytes()==content and progress[-1]==90
    for corrupt in (b'bad',content+b'extra'):
        updater.open=Mock(side_effect=[io.BytesIO(checksum),io.BytesIO(corrupt)])
        with pytest.raises(StudioError):updater.download(offered,output)
        assert not output.exists()
    updater.open=Mock(return_value=io.BytesIO(b'0'*64+b'  '+ASSET.encode()))
    with pytest.raises(StudioError):updater.download(offered,output)
    updater.cancel.set(); updater.open=Mock(return_value=io.BytesIO(checksum))
    with pytest.raises(UpdateCancelled):updater.download(offered,output)


def make_zip(tmp_path, additional=None):
    archive=tmp_path/'update.zip'
    with zipfile.ZipFile(archive,'w') as bundle:
        bundle.writestr('HallAirconStudio/HallAirconStudio.exe',b'MZ-demo')
        bundle.writestr('HallAirconStudio/_internal/data.dat',b'demo')
        bundle.writestr('HallAirconStudio/'+INSTALL_MARKER.as_posix(),json.dumps({'application':'Better-Hall-Aircon','format':1}))
        if additional:
            entry, data = additional
            if isinstance(entry, str) and '\\' in entry:
                raw = zipfile.ZipInfo('placeholder')
                raw.filename = entry  # Preserve a malicious raw ZIP path on Windows.
                entry = raw
            bundle.writestr(entry, data)
    return archive


@pytest.mark.parametrize('path',['../escape','HallAirconStudio/../../escape','C:/escape','HallAirconStudio/_internal/evil:stream','HallAirconStudio/CON.txt','HallAirconStudio/evil.','HallAirconStudio\\escape','HallAirconStudio/vault.bin','HallAirconStudio/capture/private.key'])
def test_unsafe_archives_never_escape_staging(tmp_path,path):
    archive=make_zip(tmp_path,(path,b'private'))
    updater=Updater(tmp_path,tmp_path)
    with pytest.raises(StudioError):updater.unpack(archive,tmp_path/'payload')
    assert not (tmp_path/'payload/HallAirconStudio/HallAirconStudio.exe').exists()


def test_symlinks_and_case_insensitive_duplicate_are_rejected(tmp_path):
    entry=zipfile.ZipInfo('HallAirconStudio/link');entry.external_attr=(stat.S_IFLNK|0o777)<<16
    updater=Updater(tmp_path,tmp_path)
    for additional in ((entry,b'../../outside'),('HallAirconStudio/hallairconstudio.EXE',b'duplicate')):
        with pytest.raises(StudioError):updater.unpack(make_zip(tmp_path,additional),tmp_path/'payload')


def test_verified_payload_is_staged_beside_install_without_modifying_it(tmp_path):
    install=tmp_path/'Installed app'; install.mkdir(); (install/'HallAirconStudio.exe').write_bytes(b'original')
    marker=install/INSTALL_MARKER;marker.parent.mkdir(parents=True);marker.write_text(json.dumps({'application':'Better-Hall-Aircon','format':1}))
    user=tmp_path/'user';user.mkdir();(user/'vault.bin').write_bytes(b'keep private data')
    resources=Path(__file__).resolve().parents[1]
    updater=Updater(user,resources,install)
    archive=make_zip(tmp_path)
    def download(release,path,progress):path.write_bytes(archive.read_bytes())
    updater.download=download
    plan=updater.prepare({'version':'99.0.0'})
    data=json.loads(plan.read_text())
    assert Path(data['staging']).parent==install.parent
    assert Path(data['candidate']).joinpath('HallAirconStudio.exe').read_bytes()==b'MZ-demo'
    assert (install/'HallAirconStudio.exe').read_bytes()==b'original'
    assert (user/'vault.bin').read_bytes()==b'keep private data'
    assert not Path(data['backup']).exists()
    assert (plan.parent/'apply-update.ps1').exists()


def test_loose_desktop_files_cannot_be_replaced_as_an_install(tmp_path):
    install=tmp_path/'Desktop';install.mkdir();(install/'HallAirconStudio.exe').write_bytes(b'original')
    marker=install/INSTALL_MARKER;marker.parent.mkdir(parents=True);marker.write_text(json.dumps({'application':'Better-Hall-Aircon','format':1}))
    assert dedicated_install(install)
    (install/'personal-notes.txt').write_text('keep me')
    assert not dedicated_install(install)
    updater=Updater(tmp_path/'user',tmp_path,install);updater.download=Mock()
    with pytest.raises(StudioError):updater.prepare({'version':'99.0.0'})
    updater.download.assert_not_called()
    assert (install/'personal-notes.txt').read_text()=='keep me'


def test_locale_catalogue_and_generated_js_match():
    ui=Path(__file__).resolve().parents[1]/'ui'
    catalogue=json.loads((ui/'locale-en.json').read_text(encoding='utf-8'))
    javascript=(ui/'locale-en.js').read_text(encoding='utf-8')
    generated=json.loads(javascript.split('window.EN=',1)[1].rsplit(';',1)[0])
    assert generated==catalogue
    assert catalogue['空调控制']=='Aircon control'
    # Blockly arguments must survive every translated block message.
    import re
    for original,translated in catalogue.items():
        assert sorted(re.findall(r'%\d+',original))==sorted(re.findall(r'%\d+',translated))


@pytest.mark.parametrize('fail_first_launch',[False,True])
def test_windows_helper_swaps_after_exit_and_rolls_back_on_launch_error(tmp_path,fail_first_launch):
    import os
    import subprocess
    import sys
    import time
    if os.name!='nt':pytest.skip('Windows helper integration')
    install=tmp_path/'Current app'; install.mkdir();(install/'HallAirconStudio.exe').write_text('old')
    stage=tmp_path/'.HallAircon-update-integration';stage.mkdir()
    candidate=stage/'payload/HallAirconStudio';candidate.mkdir(parents=True);(candidate/'HallAirconStudio.exe').write_text('new')
    backup=tmp_path/'Current app.previous-integration'
    result=tmp_path/'result.json';ready=stage/'helper-ready';launches=tmp_path/'launches.txt'
    parent=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],creationflags=subprocess.CREATE_NO_WINDOW)
    data={'pid':parent.pid,'install':str(install),'staging':str(stage),'candidate':str(candidate),'backup':str(backup),
          'result':str(result),'ready':str(ready),'version':'99.0.0'}
    plan=stage/'plan.json';plan.write_text(json.dumps(data),encoding='utf-8')
    helper=Path(__file__).resolve().parents[1]/'studio/update_helper.ps1'
    # Exercise the actual swap/rollback script, replacing only process launch.
    # No dummy or real application binary is executed.
    wrapper=stage/'test-helper.ps1'
    quote=lambda path:"'"+str(path).replace("'","''")+"'"
    wrapper.write_text("$script:launchCount=0\nfunction global:Start-Process { param($FilePath,$WorkingDirectory)\n"
                       "$script:launchCount++\n"+
                       ("if ($script:launchCount -eq 1) { throw 'Simulated launch failure' }\n" if fail_first_launch else '')+
                       "Set-Content -LiteralPath "+quote(launches)+" -Value $FilePath\n}\n& "+quote(helper)+" -PlanPath "+quote(plan),encoding='utf-8-sig')
    process=subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(wrapper)],
                             stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        deadline=time.monotonic()+12
        while not ready.exists() and process.poll() is None and time.monotonic()<deadline:time.sleep(.05)
        assert ready.exists()
        assert (install/'HallAirconStudio.exe').read_text()=='old'
        parent.terminate();parent.wait(timeout=5)
        stdout,stderr=process.communicate(timeout=30)
        assert process.returncode==0,stderr.decode(errors='replace')
        outcome=json.loads(result.read_text(encoding='utf-8-sig'))
        assert outcome['status']==('rolled_back' if fail_first_launch else 'updated')
        assert (install/'HallAirconStudio.exe').read_text()==('old' if fail_first_launch else 'new')
        assert launches.exists()
        if fail_first_launch:assert (stage/'failed-install/HallAirconStudio.exe').read_text()=='new'
        else:assert (backup/'HallAirconStudio.exe').read_text()=='old'
    finally:
        if parent.poll() is None:parent.terminate();parent.wait(timeout=5)
        if process.poll() is None:process.terminate();process.communicate(timeout=5)


def test_update_ui_stays_silent_without_new_release_and_skip_never_downloads(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QApplication,QMainWindow
    from studio.storage import Store
    import studio.update_ui as ui
    app=QApplication.instance() or QApplication([])
    window=QMainWindow()
    bridge=SimpleNamespace(store=Store(tmp_path),demo=False)
    controller=ui.UpdateUI(window,None,bridge,Path(__file__).resolve().parents[1])
    controller.manual=False
    messages=[]
    class Message:
        Information=1;AcceptRole=1;RejectRole=2
        information=Mock();warning=Mock()
        def __init__(self,*args):messages.append(self);self.choice=None
        def setIcon(self,*args):pass
        def setTextFormat(self,*args):pass
        def setWindowTitle(self,*args):pass
        def setText(self,*args):pass
        def setInformativeText(self,*args):pass
        def setDetailedText(self,*args):pass
        def addButton(self,text,role):return role
        def setDefaultButton(self,button):self.choice=button
        def exec(self):pass
        def clickedButton(self):return self.choice
    monkeypatch.setattr(ui,'QMessageBox',Message)
    controller.updater.prepare=Mock(side_effect=AssertionError('Skip must not prepare an update'))
    try:
        controller.checked({'release':None});controller.checked({'error':True})
        assert not messages and not Message.information.called and not Message.warning.called
        controller.checked({'release':{'version':'99.0.0','notes':'sample'}})
        assert len(messages)==1 and not controller.busy
        controller.updater.prepare.assert_not_called()
        controller.manual=True;controller.checked({'release':None})
        Message.information.assert_called_once()
        controller.stop();controller.checked({'release':{'version':'99.0.1','notes':'ignored after closing'}})
        assert len(messages)==1
    finally:
        controller.stop();window.close()


def test_language_is_persisted_and_does_not_change_room_or_scripts(tmp_path):
    from PySide6.QtWidgets import QApplication
    from studio.bridge import Bridge
    from studio.storage import Store
    app=QApplication.instance() or QApplication([])
    store=Store(tmp_path);store.update(room='H00-00-00-0000-00')
    bridge=Bridge(store,Path(__file__).resolve().parents[1],demo=True)
    replies=[];languages=[]
    bridge.reply.connect(lambda raw:replies.append(json.loads(raw)))
    bridge.language_changed.connect(languages.append)
    bridge.request('en','language',json.dumps({'value':'en'}))
    assert replies[-1]['ok'] and languages==['en']
    assert store.config()['language']=='en'
    assert store.config()['room']=='H00-00-00-0000-00'
    assert bridge.settings()['language']=='en'
    assert bridge.translate('空调控制')=='Aircon control'
    bridge.request('invalid','language',json.dumps({'value':'xx'}))
    assert not replies[-1]['ok'] and store.config()['language']=='en'
    assert not (tmp_path/'scripts.json').exists()
