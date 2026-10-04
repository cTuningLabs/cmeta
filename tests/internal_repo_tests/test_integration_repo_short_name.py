"""
Integration tests for updating a repository by the short name it was fetched with:
`cx repo get cmeta-aops` clones into the alias `ctuninglabs@cmeta-aops`, so
`cx repo pull cmeta-aops` and a second `cx repo get cmeta-aops` must find that clone
and pull it, not try to clone it again into its existing directory.

The upstream is a local bare repository reached through a file:// URL, in a fresh
CMETA_HOME, with git's global and system configuration replaced by a throwaway one.

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from cmeta import CMeta

pytestmark = pytest.mark.skipif(shutil.which('git') is None, reason='git is not installed')


def _git(cwd, *args):
    p = subprocess.run(['git', *args], cwd=str(cwd), capture_output=True, text=True, check=True)
    return p.stdout.strip()


def _commit(repo, name, text):
    (Path(repo) / name).write_text(text + '\n')
    _git(repo, 'add', name)
    _git(repo, 'commit', '-q', '-m', f'add {name}')


@pytest.fixture()
def env(tmp_path, monkeypatch):
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
    _commit(work, 'f1.txt', '1')

    bare = tmp_path / 'upstream.git'
    _git(tmp_path, 'clone', '-q', '--bare', str(work), str(bare))

    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setenv('CMETA_HOME', str(home))

    cm = CMeta(home=str(home))
    # The alias "cx repo get shorty" would give the clone
    alias = cm.cfg['default_git_repo'] + '@shorty'
    r = cm.access({'category': 'repo', 'command': 'get', 'arg1': alias, 'url': bare.as_uri(), 'con': False})
    assert r['return'] == 0, r.get('error')

    clone = home / 'repos' / alias
    assert (clone / 'f1.txt').is_file()

    return {'cm': cm, 'work': work, 'bare': bare, 'clone': clone, 'alias': alias}


def _new_upstream_commit(env, name):
    _commit(env['work'], name, name)
    _git(env['work'], 'push', '-q', str(env['bare']), 'main')


@pytest.mark.parametrize('command', ['pull', 'get'])
def test_short_name_updates_the_clone(env, command):
    _new_upstream_commit(env, 'f2.txt')

    r = env['cm'].access({'category': 'repo', 'command': command, 'arg1': 'shorty', 'con': False})
    assert r['return'] == 0, r.get('error')
    assert (env['clone'] / 'f2.txt').is_file()


def test_full_alias_still_updates_the_clone(env):
    _new_upstream_commit(env, 'f3.txt')

    r = env['cm'].access({'category': 'repo', 'command': 'pull', 'arg1': env['alias'], 'con': False})
    assert r['return'] == 0, r.get('error')
    assert (env['clone'] / 'f3.txt').is_file()


def test_init_with_the_short_name_still_makes_a_new_local_repo(env):
    # "init" creates a local repository under exactly the name it is given
    r = env['cm'].access({'category': 'repo', 'command': 'init', 'arg1': 'shorty', 'con': False})
    assert r['return'] == 0, r.get('error')

    r = env['cm'].access({'category': 'repo', 'command': 'find', 'arg1': 'shorty', 'con': False})
    assert r['return'] == 0, r.get('error')
    assert len(r['artifacts']) == 1
