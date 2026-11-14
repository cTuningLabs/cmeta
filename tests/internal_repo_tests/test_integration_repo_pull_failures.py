"""
Integration tests for repositories that cannot be updated: `cx repo pull` (and `get`) tries every repository - a
failure never stops the others - and fails at the end, after the reindex, naming each repository it could not
update (the user, 2026-11-14: "try to update all of them, and then fail in the end with a list of failed ones").
Until then a failed `git pull` printed one warning line and the command answered success, so a clone stuck behind
local changes went unseen through several updates; a failed --checkout stopped the repositories after it.

A clone with nothing to pull from - no remote, a detached HEAD, a branch without an upstream, a remote without any
commit yet - is not a failure.

The upstreams are local bare repositories reached through file:// URLs, in a fresh CMETA_HOME, with git's global and
system configuration replaced by a throwaway one.

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


def _commit(repo, name, text=None):
    (Path(repo) / name).write_text((text or name) + '\n')
    _git(repo, 'add', name)
    _git(repo, 'commit', '-q', '-m', f'change {name}')


def _upstream(tmp_path, name, branches=()):
    """A bare upstream with one commit (f1.txt), its work tree to push new commits from, and extra branches."""
    work = tmp_path / f'{name}-work'
    work.mkdir()
    _git(work, 'init', '-q', '-b', 'main')
    _commit(work, 'f1.txt')
    for b in branches:
        _git(work, 'branch', b)
    bare = tmp_path / f'{name}.git'
    _git(tmp_path, 'clone', '-q', '--bare', str(work), str(bare))
    return work, bare


@pytest.fixture()
def env(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)

    gitconfig = tmp_path / 'gitconfig'
    gitconfig.write_text('[user]\n\tname = t\n\temail = t@example.com\n'
                         '[commit]\n\tgpgsign = false\n[tag]\n\tgpgsign = false\n'
                         '[init]\n\tdefaultBranch = main\n[pull]\n\trebase = false\n')
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', str(gitconfig))
    monkeypatch.setenv('GIT_CONFIG_NOSYSTEM', '1')
    monkeypatch.setenv('GIT_TERMINAL_PROMPT', '0')

    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setenv('CMETA_HOME', str(home))

    return {'cm': CMeta(home=str(home)), 'home': home, 'tmp': tmp_path}


def _get(env, alias, bare):
    r = env['cm'].access({'category': 'repo', 'command': 'get', 'arg1': alias, 'url': bare.as_uri(), 'con': False})
    assert r['return'] == 0, r.get('error')
    return env['home'] / 'repos' / alias


def _order(env):
    """The aliases of the git repositories in the order an update of every repository goes through them."""
    r = env['cm'].access({'category': 'repo', 'command': 'find', 'sort': False, 'base': True})
    return [a['cmeta_ref_parts'].get('artifact_alias') for a in r['artifacts'] if (a.get('cmeta') or {}).get('method') == 'git']


def _pull_all(env, **params):
    return env['cm'].access({'category': 'repo', 'command': 'pull', 'quiet': True, 'con': True, **params})


def _two_clones_one_stuck(env):
    """Two clones of their own upstreams, each upstream one commit ahead; the clone the update meets FIRST holds a
    local change to the file the new commit changes, so its pull stops ("would be overwritten") - the case of a test
    copy left in a host's clone."""
    ups = {}
    for name in ('demo-a', 'demo-b'):
        ups[name] = _upstream(env['tmp'], name)
        _get(env, name, ups[name][1])

    stuck, other = _order(env)
    for name, (work, bare) in ups.items():
        _commit(work, 'f1.txt', 'new upstream text')
        _git(work, 'push', '-q', str(bare), 'main')

    (env['home'] / 'repos' / stuck / 'f1.txt').write_text('a local change\n')
    return stuck, other


def test_a_failed_pull_does_not_stop_the_others_and_fails_at_the_end(env, capsys):
    stuck, other = _two_clones_one_stuck(env)

    r = _pull_all(env)
    out = capsys.readouterr().out

    # the clone met after the stuck one is updated all the same
    assert (env['home'] / 'repos' / other / 'f1.txt').read_text() == 'new upstream text\n'
    assert (env['home'] / 'repos' / stuck / 'f1.txt').read_text() == 'a local change\n'

    # and the command fails at the end, naming the stuck clone only
    assert r['return'] == 1
    assert [x['repo'] for x in r['failed']] == [stuck]
    assert f'1 of 2 repositories not updated: {stuck} (git pull: exit code' in r['error']
    assert 'the other 1 went through' in r['error']
    assert f'"git pull" failed in {stuck}' in out


def test_a_named_repository_that_cannot_be_pulled_fails(env):
    stuck, other = _two_clones_one_stuck(env)

    r = env['cm'].access({'category': 'repo', 'command': 'pull', 'arg1': stuck, 'con': False})
    assert r['return'] == 1
    assert r['error'].startswith(f'1 of 1 repositories not updated: {stuck} (git pull: exit code')

    r = env['cm'].access({'category': 'repo', 'command': 'pull', 'arg1': other, 'con': False})
    assert r['return'] == 0, r.get('error')


def test_nothing_to_pull_is_not_a_failure(env, capsys):
    # no remote; a detached HEAD; a branch without an upstream; a remote without any commit yet
    for name in ('no-remote', 'detached', 'local-branch'):
        _get(env, name, _upstream(env['tmp'], name)[1])

    _git(env['home'] / 'repos' / 'no-remote', 'remote', 'remove', 'origin')
    _git(env['home'] / 'repos' / 'detached', 'checkout', '-q', '--detach')
    _git(env['home'] / 'repos' / 'local-branch', 'checkout', '-q', '-b', 'mine')

    empty = env['tmp'] / 'empty.git'
    _git(env['tmp'], 'init', '-q', '--bare', '-b', 'main', str(empty))
    _get(env, 'empty', empty)

    r = _pull_all(env)
    out = capsys.readouterr().out

    assert r['return'] == 0, r.get('error')
    why = {x['repo']: x['why'] for x in r['nothing_to_pull']}
    assert why == {'no-remote': 'it has no remote',
                   'detached': 'its HEAD is detached (pinned at a commit or a tag)',
                   'local-branch': 'its branch mine has no upstream',
                   'empty': 'its remote has no commits yet'}
    assert 'cMeta info: nothing to pull in empty: its remote has no commits yet' in out


def test_a_failed_checkout_of_several_goes_on(env):
    ups = {}
    for name in ('demo-a', 'demo-b'):
        ups[name] = _upstream(env['tmp'], name)
        _get(env, name, ups[name][1])

    # only the clone the update meets SECOND has the branch: before, the first failure stopped the update there
    first, second = _order(env)
    _git(ups[second][0], 'branch', 'feature')
    _git(ups[second][0], 'push', '-q', str(ups[second][1]), 'feature')
    _git(env['home'] / 'repos' / second, 'fetch', '-q', 'origin')     # a full clone checks out what it has fetched

    r = _pull_all(env, checkout='feature')

    assert _git(env['home'] / 'repos' / second, 'rev-parse', '--abbrev-ref', 'HEAD') == 'feature'
    assert r['return'] == 1
    assert [x['repo'] for x in r['failed']] == [first]
    assert r['error'].startswith(f'1 of 2 repositories not updated: {first} (')


def test_one_repository_keeps_its_own_checkout_error(env):
    _get(env, 'demo', _upstream(env['tmp'], 'demo')[1])

    r = env['cm'].access({'category': 'repo', 'command': 'pull', 'arg1': 'demo', 'checkout': 'no-such-branch', 'con': False})
    assert r['return'] == 1
    assert 'failed' not in r and 'not updated' not in r['error']
