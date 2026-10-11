import subprocess
from types import SimpleNamespace
from crawl.updates import update_available


def test_update_check_detects_newer_commits_without_pulling(tmp_path, monkeypatch):
    (tmp_path / '.git').mkdir()
    calls=[]
    outputs=iter(['origin/main','main','origin','','2'])
    def run(args, **kwargs):
        calls.append(args)
        assert kwargs['env']['GIT_TERMINAL_PROMPT']=='0'
        return SimpleNamespace(stdout=next(outputs),check_returncode=lambda: None)
    monkeypatch.setattr(subprocess,'run',run)
    assert update_available(tmp_path)
    assert not any('pull' in args for args in calls)


def test_update_check_is_quiet_when_offline(tmp_path,monkeypatch):
    (tmp_path / '.git').mkdir()
    def run(*args,**kwargs):
        raise subprocess.TimeoutExpired('git',12)
    monkeypatch.setattr(subprocess,'run',run)
    assert not update_available(tmp_path)


def test_update_check_is_quiet_when_current(tmp_path,monkeypatch):
    (tmp_path / '.git').mkdir()
    outputs=iter(['origin/main','main','origin','','0'])
    monkeypatch.setattr(subprocess,'run',lambda *args,**kwargs: SimpleNamespace(stdout=next(outputs),check_returncode=lambda: None))
    assert not update_available(tmp_path)


def test_packaged_updates_choose_the_matching_platform(monkeypatch):
    import io, json, urllib.request
    from crawl.updates import latest_release
    def response(*args, **kwargs):
        return io.BytesIO(json.dumps({'tag_name':'v0.3.4','assets':[
            {'name':'EasyCrawl-Setup-0.3.4-windows.exe','browser_download_url':'https://github.com/RJ2320/easycrawl/releases/download/v0.3.4/setup.exe'},
            {'name':'EasyCrawl-0.3.4-mac.dmg','browser_download_url':'https://github.com/RJ2320/easycrawl/releases/download/v0.3.4/mac.dmg'}]}).encode())
    monkeypatch.setattr(urllib.request,'urlopen',response)
    assert latest_release('0.3.3','win32')[1].endswith('setup.exe')
    assert latest_release('0.3.3','darwin')[1].endswith('mac.dmg')
    assert latest_release('0.3.4','win32') is None
    assert latest_release('0.3.3','linux') is None


def test_packaged_update_ignores_untrusted_download(monkeypatch):
    import io, json, urllib.request
    from crawl.updates import latest_release
    monkeypatch.setattr(urllib.request,'urlopen',lambda *a,**k: io.BytesIO(json.dumps(
        {'tag_name':'v0.3.4','assets':[{'name':'EasyCrawl-Setup-0.3.4-windows.exe','browser_download_url':'https://example.com/setup.exe'}]}).encode()))
    assert latest_release('0.3.3','win32') is None
