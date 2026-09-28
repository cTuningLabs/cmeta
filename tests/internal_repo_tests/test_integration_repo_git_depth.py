"""
Integration tests for shallow git repositories: `cx repo get/clone/pull/checkout --depth`.

Each test clones a local upstream (a branch, a tag and three commits on main) through a
file:// URL - git ignores --depth for plain local paths - into a fresh CMETA_HOME, with
git's global and system configuration replaced by a throwaway one (no signing, no prompts).

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from cmeta import CMeta

pytestmark = pytest.mark.skipif(shutil.which('git') is None, reason='git is not installed')


def _git(cwd, *args):
    """Run git in cwd and return its stripped stdout."""
    p = subprocess.run(['git', *args], cwd=str(cwd), capture_output=True, text=True, check=True)
    return p.stdout.strip()


def _commit(repo, name, text):
    (Path(repo) / name).write_text(text + '\n')
    _git(repo, 'add', name)
    _git(repo, 'commit', '-q', '-m', f'add {name}')
    return _git(repo, 'rev-parse', 'HEAD')


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """A fresh CMETA_HOME, an isolated git configuration and a bare upstream repository."""
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX',
                'CMETA_DEBUG', 'CMETA_VERBOSE'):
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
    shas = [_commit(work, f'f{i}.txt', str(i)) for i in (1, 2, 3)]
    _git(work, 'tag', 'v1', shas[0])
    _git(work, 'branch', 'cmeta')
    _git(work, 'checkout', '-q', '-b', 'other')
    other_sha = _commit(work, 'other.txt', 'other')
    _git(work, 'checkout', '-q', 'main')

    bare = tmp_path / 'upstream.git'
    _git(tmp_path, 'clone', '-q', '--bare', str(work), str(bare))

    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setenv('CMETA_HOME', str(home))

    return {'cm': CMeta(home=str(home)), 'home': home, 'work': work, 'bare': bare,
            'url': bare.as_uri(), 'shas': shas, 'other_sha': other_sha}


def _get(env, **kwargs):
    return env['cm'].access({'category': 'repo', 'command': 'get', 'arg1': 'demo',
                             'url': env['url'], 'con': False, **kwargs})


def _clone_path(env):
    return env['home'] / 'repos' / 'demo'


def _shallow(path):
    return _git(path, 'rev-parse', '--is-shallow-repository') == 'true'


def _count(path):
    return int(_git(path, 'rev-list', '--count', 'HEAD'))


# ---------------------------------------------------------------------------
# Clone
# ---------------------------------------------------------------------------

def test_get_without_depth_is_a_full_clone(env):
    assert _get(env)['return'] == 0
    path = _clone_path(env)
    assert not _shallow(path)
    assert _count(path) == 3


def test_get_depth_1_downloads_no_history(env):
    assert _get(env, depth=1)['return'] == 0
    path = _clone_path(env)
    assert _shallow(path)
    assert _count(path) == 1
    assert _git(path, 'rev-parse', 'HEAD') == env['shas'][2]


def test_get_depth_from_the_cli_as_a_string(env):
    assert _get(env, depth='2')['return'] == 0
    assert _count(_clone_path(env)) == 2


def test_get_depth_with_a_branch_checkout(env):
    assert _get(env, depth=1, checkout='cmeta')['return'] == 0
    path = _clone_path(env)
    assert _shallow(path)
    assert _git(path, 'branch', '--show-current') == 'cmeta'
    assert _count(path) == 1


def test_get_depth_with_a_tag_checkout(env):
    assert _get(env, depth=1, checkout='v1')['return'] == 0
    path = _clone_path(env)
    assert _shallow(path)
    assert _git(path, 'rev-parse', 'HEAD') == env['shas'][0]


def test_get_depth_with_a_commit_checkout(env):
    sha = env['shas'][1]
    assert _get(env, depth=1, checkout=sha)['return'] == 0
    path = _clone_path(env)
    assert _shallow(path)
    assert _git(path, 'rev-parse', 'HEAD') == sha


def test_get_without_depth_checkout_is_unchanged(env):
    assert _get(env, checkout='other')['return'] == 0
    path = _clone_path(env)
    assert not _shallow(path)
    assert _git(path, 'branch', '--show-current') == 'other'


def test_get_depth_with_an_unknown_branch_fails_cleanly(env):
    r = _get(env, depth=1, checkout='no-such-branch')
    assert r['return'] > 0
    assert not _clone_path(env).exists() or not any(_clone_path(env).iterdir())


@pytest.mark.parametrize('depth', [0, -1, 'x'])
def test_depth_must_be_a_positive_number(env, depth):
    r = _get(env, depth=depth)
    assert r['return'] == 1
    assert 'depth' in r['error']
    assert not _clone_path(env).exists()


def test_get_depth_with_subdir(env):
    assert _get(env, depth=1, subdir='_cmr')['return'] == 0
    path = _clone_path(env)
    assert _shallow(path)
    assert 'subdir: _cmr' in (path / '_cmr.yaml').read_text()
    assert (path / '_cmr').is_dir()


def test_clone_command_takes_depth(env):
    r = env['cm'].access({'category': 'repo', 'command': 'clone', 'arg1': 'demo',
                          'url': env['url'], 'depth': 1, 'con': False})
    assert r['return'] == 0
    assert _shallow(_clone_path(env))


# ---------------------------------------------------------------------------
# Later checkout and pull of a shallow clone
# ---------------------------------------------------------------------------

def test_checkout_fetches_a_branch_missing_from_a_shallow_clone(env):
    assert _get(env, depth=1)['return'] == 0
    r = env['cm'].access({'category': 'repo', 'command': 'checkout', 'arg1': 'demo',
                          'arg2': 'other', 'con': False})
    assert r['return'] == 0
    path = _clone_path(env)
    assert _git(path, 'branch', '--show-current') == 'other'
    assert _git(path, 'rev-parse', 'HEAD') == env['other_sha']
    assert _shallow(path)


def test_checkout_fetches_a_commit_missing_from_a_shallow_clone(env):
    assert _get(env, depth=1)['return'] == 0
    sha = env['shas'][0]
    r = env['cm'].access({'category': 'repo', 'command': 'checkout', 'arg1': 'demo',
                          'arg2': sha, 'con': False})
    assert r['return'] == 0
    assert _git(_clone_path(env), 'rev-parse', 'HEAD') == sha


def test_checkout_of_an_unknown_ref_in_a_shallow_clone_fails_cleanly(env):
    assert _get(env, depth=1)['return'] == 0
    r = env['cm'].access({'category': 'repo', 'command': 'checkout', 'arg1': 'demo',
                          'arg2': 'no-such-ref', 'con': False})
    assert r['return'] == 1
    assert 'shallow clone' in r['error']


def test_pull_keeps_a_shallow_clone_shallow_with_local_commits(env):
    # A working branch: clone it shallow, commit locally, then upstream moves on
    assert _get(env, depth=1, checkout='cmeta')['return'] == 0
    path = _clone_path(env)
    _commit(path, 'mine.txt', 'mine')

    _git(env['work'], 'checkout', '-q', 'cmeta')
    _commit(env['work'], 'f4.txt', '4')
    _git(env['work'], 'push', '-q', str(env['bare']), 'cmeta')

    # --depth on a pull is not passed to "git pull": that would cut the local commit's
    # history and git would refuse to merge ("unrelated histories")
    r = env['cm'].access({'category': 'repo', 'command': 'pull', 'arg1': 'demo',
                          'depth': 1, 'con': False})
    assert r['return'] == 0
    assert (path / 'mine.txt').is_file()
    assert (path / 'f4.txt').is_file()
    assert _shallow(path)


def test_full_clone_checkout_is_unchanged(env):
    assert _get(env)['return'] == 0
    r = env['cm'].access({'category': 'repo', 'command': 'checkout', 'arg1': 'demo',
                          'arg2': 'v1', 'con': False})
    assert r['return'] == 0
    path = _clone_path(env)
    assert _git(path, 'rev-parse', 'HEAD') == env['shas'][0]
    assert not _shallow(path)


def test_a_branch_fetched_into_a_shallow_clone_updates_on_pull(env):
    assert _get(env, depth=1)['return'] == 0
    assert env['cm'].access({'category': 'repo', 'command': 'checkout', 'arg1': 'demo',
                             'arg2': 'other', 'con': False})['return'] == 0

    _git(env['work'], 'checkout', '-q', 'other')
    _commit(env['work'], 'other2.txt', 'more')
    _git(env['work'], 'push', '-q', str(env['bare']), 'other')

    assert env['cm'].access({'category': 'repo', 'command': 'pull', 'arg1': 'demo',
                             'con': False})['return'] == 0
    path = _clone_path(env)
    assert (path / 'other2.txt').is_file()
    assert _shallow(path)
