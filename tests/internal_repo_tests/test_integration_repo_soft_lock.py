"""
Integration tests of the soft lock a repository asks for: a `_cmr.yaml` with `lock: soft` - a repository that
several systems write at once through a shared drive (a Windows tree plugged from WSL2 or from a container, a
network share), where the OS locks of the systems do not see each other - makes every lock file under that
repository use the soft lock: in the process that plugs it, and in every process that starts after it (the
engine registers it from the index of repositories at its start). Other repositories and the home keep the OS lock.

Each test runs against a fresh <CMETA_HOME> in tmp_path so it does not touch the user's real cMeta state.

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import logging
import os
import subprocess
import sys

import pytest

from cmeta import CMeta
from cmeta.utils import files

POSIX = sys.platform != 'win32'
OS_MODE = 'flock' if POSIX else 'windows'

LATER_PROCESS = r'''
import os, sys
from cmeta import CMeta
from cmeta.utils import files
home, shared, own = sys.argv[1:4]
cm = CMeta(home=home)
r = cm.access({'category': 'repo', 'command': 'find', 'arg1': 'shared', 'con': False})   # any first access of the engine
assert r['return'] == 0, r
a = files.PathLock(os.path.join(shared, 'z.lock')).acquire(timeout=5)
b = files.PathLock(os.path.join(own, 'z.lock')).acquire(timeout=5)
c = files.PathLock(os.path.join(home, 'z.lock')).acquire(timeout=5)
print(a.mode, b.mode, c.mode)
a.release()
b.release()
c.release()
'''


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX',
                'CMETA_DEBUG', 'CMETA_VERBOSE', 'CMETA_FAIL_ON_ERROR', 'CMETA_SOFT_LOCK_PATHS'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    monkeypatch.setattr(files, '_lock_soft_dirs', [])
    return CMeta(home=str(tmp_path))


def access(cm, **params):
    params.setdefault('con', False)
    return cm.access(params)


def make_repo(tmp_path, name, repo_uid, lock=None):
    repo = tmp_path / 'extra' / name
    repo.mkdir(parents=True)
    text = f'artifact: {name},{repo_uid}\ncategory: repo,f4f792ab40c7498f\n'
    if lock is not None:
        text += f'lock: {lock}\n'
    (repo / '_cmr.yaml').write_text(text, encoding='utf-8')
    return repo


def plug(cm, repo):
    r = access(cm, category='repo', command='plug', arg1=str(repo))
    assert r['return'] == 0, r.get('error')


def mode_under(folder):
    lock = files.PathLock(os.path.join(str(folder), 'probe.lock')).acquire(timeout=5)
    mode = lock.mode
    lock.release()
    assert not os.path.exists(os.path.join(str(folder), 'probe.lock'))
    return mode


def test_a_repository_that_asks_for_the_soft_lock_gets_it_and_the_others_keep_the_os_lock(cm, tmp_path):
    shared = make_repo(tmp_path, 'shared', 'a1b2c3d4e5f60718', lock='soft')
    own = make_repo(tmp_path, 'own', 'b1b2c3d4e5f60718')
    assert mode_under(shared) == OS_MODE                # not plugged yet: nothing asked
    plug(cm, shared)
    plug(cm, own)

    assert mode_under(shared) == 'soft'                 # the process that plugged it
    (shared / 'sub').mkdir()
    assert mode_under(shared / 'sub') == 'soft'
    assert mode_under(own) == OS_MODE
    assert mode_under(tmp_path) == OS_MODE              # the home keeps the OS lock

    # a process that starts later knows it from the index of repositories, with its first access of the engine
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    out = subprocess.run([sys.executable, '-c', LATER_PROCESS, str(tmp_path), str(shared), str(own)], env=env,
                         stdin=subprocess.DEVNULL, capture_output=True)
    assert out.returncode == 0, out.stderr.decode('utf-8', 'replace')
    assert out.stdout.decode('utf-8', 'replace').split() == ['soft', OS_MODE, OS_MODE]


def test_the_writes_of_the_engine_in_such_a_repository_take_the_soft_lock(cm, tmp_path, caplog):
    shared = make_repo(tmp_path, 'shared', 'a1b2c3d4e5f60718', lock='soft')
    own = make_repo(tmp_path, 'own', 'b1b2c3d4e5f60718')
    plug(cm, shared)
    plug(cm, own)
    caplog.set_level(logging.DEBUG)

    for repo, mode in ((shared, 'soft'), (own, OS_MODE)):
        caplog.clear()
        r = access(cm, category='log', command='create', arg1=f'{repo.name}:note-{repo.name}', meta={'x': 1}, yaml=True)
        assert r['return'] == 0, r.get('error')
        r = access(cm, category='log', command='update', arg1=f'{repo.name}:note-{repo.name}', meta={'y': 2})
        assert r['return'] == 0, r.get('error')
        taken = [rec.getMessage() for rec in caplog.records if 'PathLock - acquired' in rec.getMessage()]
        inside = [m for m in taken if os.path.normcase(str(repo)) in os.path.normcase(m)]
        assert inside, taken
        assert all(m.endswith(f'({mode})') for m in inside), inside

    assert not any(name.endswith('.lock') for root, dirs, names in os.walk(str(tmp_path)) for name in names)


def test_a_repository_that_asks_for_nothing_else_is_untouched(cm, tmp_path):
    other = make_repo(tmp_path, 'other', 'c1b2c3d4e5f60718', lock='os')      # any other value: the default
    plug(cm, other)
    assert mode_under(other) == OS_MODE
    assert files._lock_soft_dirs == []
