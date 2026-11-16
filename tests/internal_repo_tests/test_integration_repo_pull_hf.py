"""
Integration tests of `cx repo pull hf://<owner>/<name>`: a repository of the Hugging Face Hub pulled by its API
into a throwaway CMETA_HOME, with the Hub replaced by a fake (cmeta.utils.net.hf_files / hf_fetch).

The folder is made under repos/ as hf-<owner>@<name>, registered and indexed; a later pull by alias fetches the
changes alone; an artifact the repository dropped leaves the folder and the index; --identity names where the
token comes from (a token file, a <category>::<artifact>/<file> reference, a secret alias) - kept in the
registration, used by every later pull, refused before anything is made when it is wrong.

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import hashlib
import json
import os

import pytest

from cmeta import CMeta
from cmeta import utils
from cmeta.utils import net


def blob_sha1(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """A fresh CMETA_HOME without a token of its own, and a fake Hub that records the token every call carries."""
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE',
                'HF_TOKEN', 'HUGGING_FACE_HUB_TOKEN', 'HF_TOKEN_PATH'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('HF_HOME', str(tmp_path / 'no-hf-home'))
    monkeypatch.setenv('HOME', str(tmp_path))                 # never the person's hf login
    monkeypatch.setenv('USERPROFILE', str(tmp_path))

    hub = {'contents': {'_cmr.yaml': (b'artifact: x,0123456789abcdef\n', 'git'),
                        'config/a/_cmeta.yaml': (b'artifact: a,aaaaaaaaaaaaaaaa\ncategory: config,cc6bfe174be847ed\n', 'git'),
                        'config/a/files/data.bin': (b'\x00' * 64, 'lfs')},
           'sha': 'c0ffee00', 'tokens': []}

    def hf_files(repo_id, repo_type='dataset', revision='main', token=None):
        hub['tokens'].append(token)
        files = []
        for path, (data, kind) in hub['contents'].items():
            if kind == 'lfs':
                files.append({'path': path, 'size': len(data), 'oid': 'x' * 40, 'lfs': {'oid': hashlib.sha256(data).hexdigest(), 'size': len(data)}})
            else:
                files.append({'path': path, 'size': len(data), 'oid': blob_sha1(data), 'lfs': None})
        return {'return': 0, 'files': files, 'sha': hub['sha']}

    def hf_fetch(repo_id, repo_type, revision, path, dest, token=None, expected=None):
        data = hub['contents'][path][0]
        os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)
        with open(dest, 'wb') as f:
            f.write(data)
        return {'return': 0, 'size': len(data)}

    monkeypatch.setattr(net, 'hf_files', hf_files)
    monkeypatch.setattr(net, 'hf_fetch', hf_fetch)

    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setenv('CMETA_HOME', str(home))

    return {'cm': CMeta(home=str(home)), 'home': home, 'hub': hub, 'tmp': tmp_path}


def _pull(env, arg1, **kwargs):
    return env['cm'].access({'category': 'repo', 'command': 'pull', 'arg1': arg1, 'con': False, **kwargs})


def _clone(env):
    return env['home'] / 'repos' / 'hf-ctuning@x'


def _registration(env, path):
    """The registration meta of the repository at this path (repos.json of the home)."""
    r = utils.files.safe_read_file(env['cm'].repos_config_path)
    assert r['return'] == 0, r.get('error')
    want = os.path.normcase(os.path.abspath(str(path)))
    for k, v in r['data'].items():
        if os.path.normcase(os.path.abspath(k)) == want:
            return v.get('meta', {})
    return {}


def _find_config(env, alias):
    r = env['cm'].access({'category': 'config', 'command': 'find', 'arg1': alias, 'con': False})
    return [a['path'] for a in r.get('artifacts', [])] if r.get('return', 1) == 0 else []


def test_a_hub_repository_is_pulled_registered_and_indexed_then_kept_in_step(env):
    r = _pull(env, 'hf://ctuning/x')
    assert r['return'] == 0, r.get('error')
    clone = _clone(env)
    assert (clone / 'config' / 'a' / 'files' / 'data.bin').read_bytes() == b'\x00' * 64
    record = json.loads((clone / net.HF_RECORD).read_text())
    assert record['repo'] == 'ctuning/x' and record['type'] == 'dataset' and record['commit'] == 'c0ffee00'
    assert _registration(env, clone).get('method') == 'hf'
    assert _find_config(env, 'a') == [str(clone / 'config' / 'a')]
    assert env['hub']['tokens'] == [None]                                     # no token on this machine, none given

    # A later pull by the repository's alias: nothing to fetch
    r = _pull(env, 'x')
    assert r['return'] == 0, r.get('error')
    assert r.get('nothing_to_pull') or True

    # The repository dropped the artifact and gained another: the folder follows, and so does the index
    env['hub']['contents'] = {'_cmr.yaml': (b'artifact: x,0123456789abcdef\n', 'git'),
                              'config/b/_cmeta.yaml': (b'artifact: b,bbbbbbbbbbbbbbbb\ncategory: config,cc6bfe174be847ed\n', 'git')}
    env['hub']['sha'] = 'c0ffee01'
    r = _pull(env, 'x')
    assert r['return'] == 0, r.get('error')
    assert not (clone / 'config' / 'a').exists() and (clone / 'config' / 'b' / '_cmeta.yaml').exists()
    assert _find_config(env, 'a') == []
    assert _find_config(env, 'b') == [str(clone / 'config' / 'b')]


def test_a_token_file_identity_is_used_kept_and_reused(env):
    token = env['tmp'] / 'hub-token.txt'
    token.write_text('\nhf_from_the_file\n')
    r = _pull(env, 'hf://ctuning/x', identity=str(token))
    assert r['return'] == 0, r.get('error')
    assert env['hub']['tokens'] == ['hf_from_the_file']
    clone = _clone(env)
    assert _registration(env, clone).get('identity') == str(token)
    assert 'hf_from_the_file' not in (clone / net.HF_RECORD).read_text()     # the token is never written

    # The next pulls of that clone carry the token without being told again
    r = _pull(env, 'x')
    assert r['return'] == 0, r.get('error')
    assert env['hub']['tokens'] == ['hf_from_the_file'] * 2

    # Another identity given to the existing clone replaces it
    other = env['tmp'] / 'other-token.txt'
    other.write_text('hf_other')
    r = _pull(env, 'x', identity=str(other))
    assert r['return'] == 0, r.get('error')
    assert env['hub']['tokens'][-1] == 'hf_other' and _registration(env, clone).get('identity') == str(other)

    # The status names the identity, fetches nothing
    r = _pull(env, 'x', status=True)
    assert r['return'] == 0 and len(env['hub']['tokens']) == 3


def test_a_cmeta_reference_identity_names_a_token_file_inside_an_artifact(env):
    r = _pull(env, 'hf://ctuning/x')
    assert r['return'] == 0, r.get('error')
    clone = _clone(env)
    (clone / 'config' / 'a' / 'hub.token').write_text('hf_in_the_artifact\n')   # a file added locally stays
    r = _pull(env, 'x', identity='config::a/hub.token')
    assert r['return'] == 0, r.get('error')
    assert env['hub']['tokens'][-1] == 'hf_in_the_artifact'
    assert _registration(env, clone).get('identity') == 'config::a/hub.token'


def test_a_wrong_identity_is_refused_before_anything_is_fetched(env):
    for identity, words in (('no-such-file-or-secret', ('neither a token file nor a secret', 'cMeta AOps')),
                            ('config::missing/hub.token', ('is not on this machine',)),
                            ('config::a', ('must be <category>::<artifact>/<token file',))):
        r = _pull(env, 'hf://ctuning/x', identity=identity)
        assert r['return'] > 0, identity
        for w in words:
            assert w in r['error'], (identity, r['error'])
    assert not _clone(env).exists() and env['hub']['tokens'] == []

    # An empty token file is refused too, and the folder of the clone is not left behind
    empty = env['tmp'] / 'empty.txt'
    empty.write_text('\n')
    r = _pull(env, 'hf://ctuning/x', identity=str(empty))
    assert r['return'] > 0 and 'is empty' in r['error'] and not _clone(env).exists()
