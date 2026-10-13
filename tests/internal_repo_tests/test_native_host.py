"""
Tests for portable cMeta native messaging hosts.

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import importlib.util
import json
from pathlib import Path
import sys

import cmeta
import pytest


MODULE = Path(cmeta.__file__).parent / 'internal-repo/category/utils/api/native_host.py'
SPEC = importlib.util.spec_from_file_location('test_cmeta_native_host', MODULE)
native_host = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(native_host)
REF = '1111111111111111::2222222222222222'


class FakeCM:
    def __init__(self, artifact):
        self.artifact = artifact
        self.home_path = artifact.parent

    def access(self, params):
        assert params['category'] == '1111111111111111'
        assert params['arg1'] == '2222222222222222'
        return {'return': 0, 'artifacts': [{'path': str(self.artifact)}]}


def artifact_at(path, entry='bridge/host.py'):
    path.mkdir(parents=True)
    (path / 'bridge').mkdir()
    (path / 'bridge/host.py').write_text('def dispatch(request, cm): return request\n', encoding='utf-8')
    (path / 'native-host.json').write_text(json.dumps({
        'name': 'example_host', 'description': 'Example host', 'entry': entry,
        'allowed_extensions': ['example@example.org'],
        'checks': [{'command': 'ping'}],
    }), encoding='utf-8')
    return path


def test_resolves_same_uid_from_current_home(tmp_path):
    first = artifact_at(tmp_path / 'first' / 'plugin')
    second = artifact_at(tmp_path / 'second' / 'renamed-plugin')
    cm = FakeCM(first)
    assert native_host.resolve(cm, REF)['root'] == first
    cm.artifact = second
    cm.home_path = second.parent
    assert native_host.resolve(cm, REF)['root'] == second


def test_entry_cannot_escape_artifact(tmp_path):
    root = artifact_at(tmp_path / 'plugin', entry='../outside.py')
    (tmp_path / 'outside.py').write_text('def dispatch(request, cm): return request\n', encoding='utf-8')
    with pytest.raises(ValueError, match='inside its artifact'):
        native_host.resolve(FakeCM(root), REF)


def test_launcher_stores_only_cx_and_uid_reference(tmp_path, monkeypatch):
    root = artifact_at(tmp_path / 'home' / 'plugin')
    launcher = tmp_path / 'registration' / 'example_host.bat'
    manifest = tmp_path / 'registration' / 'example_host.json'
    monkeypatch.setattr(native_host, 'locations', lambda name: (launcher, manifest))
    monkeypatch.setattr(native_host, '_registered_manifest', lambda name: None)
    monkeypatch.setattr(native_host, '_write_registration', lambda name, path: None)
    native_host.install(FakeCM(root), REF, apply=True)
    contents = launcher.read_bytes().decode('mbcs' if sys.platform == 'win32' else 'utf-8')
    assert 'cx utils native-host-run ' + REF in contents
    assert 'cmeta utils native-host-run ' + REF in contents
    assert str(root) not in contents
    assert 'python' not in contents.lower()
    assert json.loads(manifest.read_text(encoding='utf-8'))['path'] == str(launcher)


def test_check_request_uses_selected_home(tmp_path):
    script = tmp_path / 'reply.py'
    script.write_text('''import json,os,struct,sys
raw=sys.stdin.buffer.read()
request=json.loads(raw[4:])
reply=json.dumps({'return':0,'home':os.environ['CMETA_HOME'],'request':request}).encode()
sys.stdout.buffer.write(struct.pack('=I',len(reply))+reply)
''', encoding='utf-8')
    home = tmp_path / 'selected-home'
    response = native_host._send([sys.executable, str(script)], {'command': 'ping'}, home)
    assert response['home'] == str(home)
    assert response['request'] == {'command': 'ping'}
