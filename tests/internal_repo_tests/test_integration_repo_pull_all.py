"""
Integration tests for updating every repository at once: `cx repo pull` (or `get`) with no
name asks first in a terminal - "[Y/n]", Enter means yes - and never asks with --quiet (-q),
without a terminal, or when a repository is named.

The upstream is a local bare repository reached through a file:// URL, in a fresh
CMETA_HOME, with git's global and system configuration replaced by a throwaway one.

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from cmeta import CMeta

pytestmark = pytest.mark.skipif(shutil.which('git') is None, reason='git is not installed')


def _git(cwd, *args):
    p = subprocess.run(['git', *args], cwd=str(cwd), capture_output=True, text=True, check=True)
    return p.stdout.strip()


def _commit(repo, name):
    (Path(repo) / name).write_text(name + '\n')
    _git(repo, 'add', name)
    _git(repo, 'commit', '-q', '-m', f'add {name}')


class _Stdin:
    """A stand-in for sys.stdin that says whether it is a terminal."""

    def __init__(self, tty):
        self.tty = tty

    def isatty(self):
        return self.tty


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
    _commit(work, 'f1.txt')

    bare = tmp_path / 'upstream.git'
    _git(tmp_path, 'clone', '-q', '--bare', str(work), str(bare))

    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setenv('CMETA_HOME', str(home))

    cm = CMeta(home=str(home))
    r = cm.access({'category': 'repo', 'command': 'get', 'arg1': 'demo', 'url': bare.as_uri(), 'con': False})
    assert r['return'] == 0, r.get('error')

    # A new upstream commit, which only a pull brings into the clone
    _commit(work, 'f2.txt')
    _git(work, 'push', '-q', str(bare), 'main')

    return {'cm': cm, 'clone': home / 'repos' / 'demo'}


def _pull(env, monkeypatch, answer='', tty=True, **params):
    """Run the pull in console mode with a scripted answer; return the result and the prompts."""
    prompts = []

    def fake_input(prompt=''):
        prompts.append(prompt)
        return answer

    monkeypatch.setattr('builtins.input', fake_input)
    monkeypatch.setattr(sys, 'stdin', _Stdin(tty))

    r = env['cm'].access({'category': 'repo', 'command': params.pop('command', 'pull'), 'con': True, **params})
    return r, prompts


@pytest.mark.parametrize('answer', ['', 'y', 'Yes'])
def test_yes_or_enter_updates_every_repository(env, monkeypatch, capsys, answer):
    r, prompts = _pull(env, monkeypatch, answer=answer)
    assert r['return'] == 0, r.get('error')
    assert len(prompts) == 1 and '[Y/n]' in prompts[0]
    assert 'demo' in capsys.readouterr().out
    assert (env['clone'] / 'f2.txt').is_file()


@pytest.mark.parametrize('answer', ['n', 'no'])
def test_no_updates_nothing(env, monkeypatch, answer):
    r, prompts = _pull(env, monkeypatch, answer=answer)
    assert r['return'] == 0, r.get('error')
    assert r.get('skipped') is True
    assert len(prompts) == 1
    assert not (env['clone'] / 'f2.txt').exists()


def test_quiet_does_not_ask(env, monkeypatch):
    r, prompts = _pull(env, monkeypatch, answer='n', quiet=True)
    assert r['return'] == 0, r.get('error')
    assert prompts == []
    assert (env['clone'] / 'f2.txt').is_file()


def test_without_a_terminal_it_does_not_ask(env, monkeypatch):
    r, prompts = _pull(env, monkeypatch, answer='n', tty=False)
    assert r['return'] == 0, r.get('error')
    assert prompts == []
    assert (env['clone'] / 'f2.txt').is_file()


def test_a_named_repository_is_not_asked_about(env, monkeypatch):
    r, prompts = _pull(env, monkeypatch, answer='n', arg1='demo')
    assert r['return'] == 0, r.get('error')
    assert prompts == []
    assert (env['clone'] / 'f2.txt').is_file()


def test_get_with_no_name_asks_too(env, monkeypatch):
    r, prompts = _pull(env, monkeypatch, answer='n', command='get')
    assert r['return'] == 0, r.get('error')
    assert len(prompts) == 1
    assert not (env['clone'] / 'f2.txt').exists()
