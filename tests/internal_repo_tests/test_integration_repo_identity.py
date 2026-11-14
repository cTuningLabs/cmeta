"""
Integration tests for the git identity of a clone: `cx repo pull/get --identity`.

A throwaway CMETA_HOME, git's global and system configuration replaced by a throwaway one, a bare upstream
cloned through a file:// URL (git never calls ssh for it, so a fake key file stands for the key). The identity,
given as a key file or as a cMeta reference <category>::<artifact>/<file>, lands in the clone's own git
configuration (core.sshCommand) and in the repository's registration; a wrong identity is refused before
anything is cloned; an identity given to an existing clone is applied before the pull; a pull without one
changes nothing.

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from cmeta import CMeta
from cmeta import utils

pytestmark = pytest.mark.skipif(shutil.which('git') is None, reason='git is not installed')


def _git(cwd, *args):
    """Run git in cwd and return its stripped stdout."""
    p = subprocess.run(['git', *args], cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, text=True, check=True)
    return p.stdout.strip()


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """A fresh CMETA_HOME, an isolated git configuration, a bare upstream and a fake key file."""
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX',
                'CMETA_DEBUG', 'CMETA_VERBOSE', 'GIT_SSH_COMMAND'):
        monkeypatch.delenv(var, raising=False)

    gitconfig = tmp_path / 'gitconfig'
    gitconfig.write_text('[user]\n\tname = t\n\temail = t@example.com\n'
                         '[commit]\n\tgpgsign = false\n[tag]\n\tgpgsign = false\n'
                         '[init]\n\tdefaultBranch = main\n[pull]\n\trebase = false\n')
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', str(gitconfig))
    monkeypatch.setenv('GIT_CONFIG_NOSYSTEM', '1')
    monkeypatch.setenv('GIT_TERMINAL_PROMPT', '0')

    work = tmp_path / 'upstream-work'
    work.mkdir()
    _git(work, 'init', '-q', '-b', 'main')
    (work / 'f1.txt').write_text('1\n')
    _git(work, 'add', 'f1.txt')
    _git(work, 'commit', '-q', '-m', 'add f1')

    bare = tmp_path / 'upstream.git'
    _git(tmp_path, 'clone', '-q', '--bare', str(work), str(bare))

    # a file that stands for a private key (git never uses it for a file:// clone)
    key = tmp_path / 'keys' / 'id_test'
    key.parent.mkdir()
    key.write_text('not a real key\n')

    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setenv('CMETA_HOME', str(home))

    return {'cm': CMeta(home=str(home)), 'home': home, 'bare': bare, 'url': bare.as_uri(), 'key': key}


def _pull(env, **kwargs):
    return env['cm'].access({'category': 'repo', 'command': 'pull', 'arg1': 'demo',
                             'url': env['url'], 'con': False, **kwargs})


def _clone(env):
    return env['home'] / 'repos' / 'demo'


def _local(path, key):
    """A key of the clone's own git configuration ('' when it is not set)."""
    p = subprocess.run(['git', '-C', str(path), 'config', '--local', '--get', key], stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return p.stdout.strip()


def _registration(env, path):
    """The registration meta of the repository at this path (repos.json of the home)."""
    r = utils.files.safe_read_file(env['cm'].repos_config_path)
    assert r['return'] == 0, r.get('error')
    want = os.path.normcase(os.path.abspath(str(path)))
    for k, v in r['data'].items():
        if os.path.normcase(os.path.abspath(k)) == want:
            return v.get('meta', {})
    return {}


# ---------------------------------------------------------------------------
# A key file
# ---------------------------------------------------------------------------

def test_a_key_file_identity_lands_in_the_clone_and_the_registration(env):
    r = _pull(env, identity=str(env['key']))
    assert r['return'] == 0, r.get('error')

    path = _clone(env)
    cmd = _local(path, 'core.sshCommand')
    assert cmd.startswith('ssh -i "') and 'IdentitiesOnly=yes' in cmd
    assert str(env['key']).replace(os.sep, '/') in cmd

    assert _registration(env, path).get('identity') == str(env['key'])

    # the index says so too (cx repo status prints it)
    r = env['cm'].access({'category': 'repo', 'command': 'find', 'arg1': 'demo', 'con': False})
    assert r['return'] == 0 and len(r['artifacts']) == 1
    assert r['artifacts'][0]['cmeta'].get('identity') == str(env['key'])

    # the shared descriptor of the repository never carries it
    cmr = (path / '_cmr.yaml').read_text(encoding='utf-8')
    assert 'identity' not in cmr


# ---------------------------------------------------------------------------
# A key inside an artifact: <category>::<artifact>/<file>
# ---------------------------------------------------------------------------

def test_a_cmeta_reference_identity(env):
    r = env['cm'].access({'category': 'config', 'command': 'add', 'arg1': 'ident-key', 'con': False})
    assert r['return'] == 0, r.get('error')
    art = Path(r['path'])
    (art / 'files').mkdir()
    (art / 'files' / 'id_test').write_text('not a real key\n')

    r = _pull(env, identity='config::ident-key/files/id_test')
    assert r['return'] == 0, r.get('error')

    cmd = _local(_clone(env), 'core.sshCommand')
    assert str(art / 'files' / 'id_test').replace(os.sep, '/') in cmd
    assert _registration(env, _clone(env)).get('identity') == 'config::ident-key/files/id_test'


# ---------------------------------------------------------------------------
# Refusals, before anything is cloned
# ---------------------------------------------------------------------------

def test_a_wrong_identity_is_refused_before_anything_is_cloned(env):
    r = _pull(env, identity='no-such-key-or-secret')
    assert r['return'] > 0
    assert 'no-such-key-or-secret' in r['error']
    # a fresh home has no secret category (cMeta AOps): the error says what a secret alias needs
    assert 'cMeta AOps' in r['error'] and 'works without it' in r['error']
    assert not _clone(env).exists()

    r = _pull(env, identity='config::no-such-artifact/files/id')
    assert r['return'] > 0 and 'no-such-artifact' in r['error']
    assert not _clone(env).exists()

    r = _pull(env, identity='config::ident-key')
    assert r['return'] > 0 and 'must be' in r['error']
    assert not _clone(env).exists()


# ---------------------------------------------------------------------------
# An existing clone
# ---------------------------------------------------------------------------

def test_an_identity_given_to_an_existing_clone(env):
    assert _pull(env)['return'] == 0
    path = _clone(env)
    assert _local(path, 'core.sshCommand') == ''
    assert 'identity' not in _registration(env, path)

    r = env['cm'].access({'category': 'repo', 'command': 'pull', 'arg1': 'demo',
                          'identity': str(env['key']), 'con': False})
    assert r['return'] == 0, r.get('error')
    assert 'IdentitiesOnly=yes' in _local(path, 'core.sshCommand')
    assert _registration(env, path).get('identity') == str(env['key'])


def test_a_pull_without_identity_keeps_the_one_given_before(env):
    assert _pull(env, identity=str(env['key']))['return'] == 0

    r = env['cm'].access({'category': 'repo', 'command': 'pull', 'arg1': 'demo', 'con': False})
    assert r['return'] == 0, r.get('error')
    assert 'IdentitiesOnly=yes' in _local(_clone(env), 'core.sshCommand')
    assert _registration(env, _clone(env)).get('identity') == str(env['key'])


def test_an_identity_is_never_given_to_every_clone_at_once(env):
    """A pull of every repository (no name) or a pattern matching several refuses --identity before anything runs."""
    assert _pull(env)['return'] == 0
    r = env['cm'].access({'category': 'repo', 'command': 'pull', 'arg1': 'demo2', 'url': env['url'], 'con': False})
    assert r['return'] == 0, r.get('error')

    r = env['cm'].access({'category': 'repo', 'command': 'pull', 'identity': str(env['key']), 'con': False, 'quiet': True})
    assert r['return'] == 1 and '--identity is given to one repository' in r['error']

    r = env['cm'].access({'category': 'repo', 'command': 'pull', 'arg1': 'demo*', 'identity': str(env['key']), 'con': False})
    assert r['return'] == 1 and '--identity is given to one repository' in r['error']

    for name in ('demo', 'demo2'):
        assert _local(env['home'] / 'repos' / name, 'core.sshCommand') == ''


def test_a_clone_without_identity_has_none(env):
    assert _pull(env)['return'] == 0
    assert _local(_clone(env), 'core.sshCommand') == ''
    assert 'identity' not in _registration(env, _clone(env))
