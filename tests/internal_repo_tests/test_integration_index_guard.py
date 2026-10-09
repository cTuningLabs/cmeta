"""
Integration tests of the index lock (`<home>/index.lock`): a full reindex holds it for its whole rebuild
and swap, the index of pulled or plugged repositories for its duration, and every write of a record for
a moment - so the writes made while a reindex runs wait for it and land in the new index instead of in
the one it replaces, two rebuilds run one after the other, several first runs on a fresh home build one
index, the leftovers of killed rebuilds are removed, and a waiter says so and gives up after
CMETA_INDEX_LOCK_TIMEOUT seconds.

Each test runs against a fresh <CMETA_HOME> in tmp_path so it does not touch the user's real cMeta
state. The reindex of another process is paused by a hook on `Repos._index`: a marker file says that
it holds the lock, a go file lets it continue.

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import pickle
import subprocess
import sys
import time

import pytest

from cmeta import CMeta
from cmeta import repos as cmeta_repos
from cmeta.utils import files


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX',
                'CMETA_DEBUG', 'CMETA_VERBOSE', 'CMETA_FAIL_ON_ERROR', 'CMETA_INDEX_LOCK_TIMEOUT'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    monkeypatch.setattr(cmeta_repos, '_migrated_notices', set())
    return CMeta(home=str(tmp_path))


def make(cm, alias, **meta):
    r = cm.access({'category': 'log', 'command': 'create', 'arg1': f'local:{alias}', 'meta': meta, 'con': False})
    assert r['return'] == 0, r.get('error')
    return r['meta']['artifact']


def env_for(home, **extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith('CMETA_') and k not in ('VIRTUAL_ENV', 'CONDA_PREFIX')}
    env['CMETA_HOME'] = str(home)
    env['PYTHONIOENCODING'] = 'utf-8'
    env.update(extra)
    return env


def start(args, home, **extra):
    """A cMeta command line (cx <args>) in another process, with a null input; its output is read by finish()."""
    return subprocess.Popen([sys.executable, '-m', 'cmeta'] + list(args), env=env_for(home, **extra),
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def finish(proc, timeout=300):
    out, _ = proc.communicate(timeout=timeout)
    return proc.returncode, out.decode('utf-8', 'replace')


PAUSED_REINDEX = r'''
import os, sys, time
home, marker, go = sys.argv[1:4]
from cmeta import CMeta
cm = CMeta(home=home)
original = cm.repos._index
def paused(*args, **kwargs):
    with open(marker, 'w') as f:
        f.write(str(os.getpid()))
    while not os.path.exists(go):
        time.sleep(0.01)
    return original(*args, **kwargs)
cm.repos._index = paused
r = cm.repos.reindex()
print('REINDEX', r['return'], r.get('error', ''), flush=True)
'''


def start_paused_reindex(tmp_path):
    """A full reindex in another process that holds the index lock and waits for the go file."""
    marker = tmp_path / 'reindex-holds-the-lock'
    go = tmp_path / 'reindex-go'
    proc = subprocess.Popen([sys.executable, '-c', PAUSED_REINDEX, str(tmp_path), str(marker), str(go)],
                            env=env_for(tmp_path), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    deadline = time.time() + 60
    while not marker.exists():
        if proc.poll() is not None:
            raise AssertionError('the reindex ended before it held the lock: ' + finish(proc)[1])
        if time.time() > deadline:
            proc.kill()
            raise AssertionError('the paused reindex did not take the lock in 60 s')
        time.sleep(0.01)
    return proc, go


def index_aliases(tmp_path, category='log'):
    """(the lowercase aliases of the index, {uid: path}) of a category as the pickle on disk holds them."""
    with open(tmp_path / 'index' / f'{category}.pkl', 'rb') as f:
        data = pickle.load(f)
    return set(data['lowercase_aliases']), {uid: rec['path'] for uid, rec in data['uids'].items()}


def folders(home, category='log'):
    base = home / 'repos' / 'local' / category
    return {p.name.lower() for p in base.iterdir() if p.is_dir()} if base.is_dir() else set()


def leftovers(home):
    return sorted(p.name for p in home.iterdir() if p.name.startswith(('index.tmp-', 'index.old-', 'index.lock')))


def test_writes_during_a_full_reindex_wait_for_it_and_land_in_the_new_index(cm, tmp_path):
    for i in range(12):
        make(cm, f'kept-{i}', n=i)
    for i in range(3):
        make(cm, f'doomed-{i}')

    reindex, go = start_paused_reindex(tmp_path)

    writers = {
        'create': [start(['log', 'create', f'born-{i}'], tmp_path) for i in range(3)],
        'delete': [start(['log', 'delete', f'doomed-{i}', '-f'], tmp_path) for i in range(3)],
        'update': [start(['log', 'update', 'kept-0', '--new_tags=touched'], tmp_path)],
        'reindex one': [start(['log', 'reindex', 'kept-1'], tmp_path)],
        'repo reindex': [start(['repo', 'reindex', 'local'], tmp_path)],
    }
    every = [p for group in writers.values() for p in group]

    # While the reindex holds the lock none of the writers gets through
    time.sleep(2.0)
    assert all(p.poll() is None for p in every), 'a writer finished while the reindex held the index lock'

    go.touch()
    rc, out = finish(reindex)
    assert rc == 0 and 'REINDEX 0' in out, out

    for kind, group in writers.items():
        for p in group:
            rc, out = finish(p)
            assert rc == 0, f'{kind}: {out}'

    # The index equals the disk: the creations are in, the deletions are out, the update is in
    aliases, paths = index_aliases(tmp_path)
    expected = {f'kept-{i}' for i in range(12)} | {f'born-{i}' for i in range(3)}
    assert folders(tmp_path) == expected
    assert aliases == expected
    assert all(os.path.isdir(p) for p in paths.values())
    r = cm.access({'category': 'log', 'command': 'find', 'arg1': 'kept-0', 'con': False})
    assert r['return'] == 0 and 'touched' in r['artifacts'][0]['cmeta'].get('tags', []), r
    assert leftovers(tmp_path) == []


def test_two_full_reindexes_at_once_run_one_after_the_other(cm, tmp_path):
    for i in range(10):
        make(cm, f'a-{i}')

    procs = [start(['--reindex'], tmp_path) for _ in range(2)]
    for p in procs:
        rc, out = finish(p)
        assert rc == 0, out

    aliases, paths = index_aliases(tmp_path)
    assert aliases == folders(tmp_path) == {f'a-{i}' for i in range(10)}
    assert all(os.path.isdir(p) for p in paths.values())
    assert leftovers(tmp_path) == []


def test_several_first_runs_on_a_fresh_home_build_one_index(tmp_path):
    home = tmp_path / 'fresh'

    procs = [start(['repo', 'find', 'local'], home) for _ in range(4)]
    for p in procs:
        rc, out = finish(p)
        assert rc == 0, out

    assert (home / 'repos.json').is_file()
    assert (home / 'index' / 'repo.pkl').is_file()
    assert leftovers(home) == []


def test_the_leftovers_of_killed_rebuilds_are_removed_by_the_next_reindex(cm, tmp_path):
    make(cm, 'one')
    for name in ('index.tmp-424242', 'index.old-424243'):
        d = tmp_path / name
        d.mkdir()
        (d / 'log.pkl').write_bytes(b'leftover')

    r = cm.repos.reindex()
    assert r['return'] == 0, r.get('error')
    assert leftovers(tmp_path) == []
    assert (tmp_path / 'index' / 'repo.pkl').is_file()
    assert index_aliases(tmp_path)[0] == {'one'}


def test_a_writer_waiting_for_a_reindex_says_so_and_gives_up_after_the_limit(cm, tmp_path):
    make(cm, 'present')
    reindex, go = start_paused_reindex(tmp_path)
    try:
        t0 = time.time()
        writer = start(['log', 'create', 'late'], tmp_path, CMETA_INDEX_LOCK_TIMEOUT='5')
        rc, out = finish(writer, timeout=120)
        elapsed = time.time() - t0
    finally:
        go.touch()
        rc_reindex, out_reindex = finish(reindex)

    assert rc != 0, out
    assert 'is locked by another process' in out and 'the full reindex by pid' in out, out
    assert 'stayed locked by another process' in out and 'CMETA_INDEX_LOCK_TIMEOUT' in out, out
    assert 4.5 <= elapsed < 60, elapsed
    assert rc_reindex == 0 and 'REINDEX 0' in out_reindex, out_reindex


def test_the_note_of_a_lock_file_is_readable_by_a_waiter(tmp_path):
    lock_file = str(tmp_path / 'x.lock')
    lock = files.PathLock(lock_file).acquire(note='the full reindex by pid 7')
    try:
        assert lock.is_locked
        assert files.PathLock.read_note(lock_file) == 'the full reindex by pid 7'
    finally:
        lock.release()
    assert not os.path.exists(lock_file)
    assert files.PathLock.read_note(lock_file) == ''
