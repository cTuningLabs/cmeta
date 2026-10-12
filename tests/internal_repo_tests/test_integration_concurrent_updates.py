"""
Integration test of many processes that update one artifact at once through the engine's API: each one adds
keys of its own to the same part of the meta (`update` merges), with the OS lock and with the soft lock that
`CMETA_SOFT_LOCK_PATHS` asks for. Every key must be in the meta at the end, the index must hold the artifact
once, with the meta of its file, and no lock file, temporary file or take-over file may be left in the home.
The order in which two updates reach the index is also forced once: the one that comes last must not bring
an older meta than the file holds.

Each test runs against a fresh <CMETA_HOME> in tmp_path so it does not touch the user's real cMeta state.

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import json
import os
import pickle
import subprocess
import sys
import threading

import pytest

from cmeta import CMeta

WORKERS = 8
UPDATES = 10

# A worker: its own updates of the same artifact, then the mode of a lock under the home
WORKER = r'''
import os, sys
from cmeta import CMeta
from cmeta.utils import files
home, alias, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
cm = CMeta(home=home)
pid = os.getpid()
for i in range(n):
    r = cm.access({'category': 'log', 'command': 'update', 'arg1': alias,
                   'meta': {'keys': {'%d-%d' % (pid, i): i}}, 'con': False})
    if r['return'] > 0:
        print('ERROR', r.get('error'), flush=True)
        sys.exit(3)
probe = files.PathLock(os.path.join(home, 'probe-%d.lock' % pid)).acquire(timeout=30)
mode = probe.mode
probe.release()
print('OK', pid, mode, flush=True)
'''


def env_for(home, **extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith('CMETA_') and k not in ('VIRTUAL_ENV', 'CONDA_PREFIX')}
    env['CMETA_HOME'] = str(home)
    env['PYTHONIOENCODING'] = 'utf-8'
    env.update(extra)
    return env


@pytest.fixture()
def home(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE',
                'CMETA_FAIL_ON_ERROR', 'CMETA_INDEX_LOCK_TIMEOUT', 'CMETA_LOCK_TIMEOUT', 'CMETA_SOFT_LOCK_PATHS'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))

    cm = CMeta(home=str(tmp_path))
    r = cm.access({'category': 'log', 'command': 'create', 'arg1': 'local:shared', 'meta': {'keys': {}}, 'con': False})
    assert r['return'] == 0, r.get('error')
    return tmp_path


def leftovers(home):
    """The files a lock, an atomic write or a take-over leaves when something went wrong."""
    found = []
    for top, dirs, names in os.walk(home):
        for name in names:
            if name.endswith(('.lock', '.tmp')) or '.take-' in name:
                found.append(os.path.join(top, name))
    return found


@pytest.mark.parametrize('mode', ['os', 'soft'])
def test_many_processes_update_one_artifact_and_no_key_is_lost(home, mode):
    extra = {'CMETA_SOFT_LOCK_PATHS': str(home)} if mode == 'soft' else {}
    env = env_for(home, **extra)

    procs = [subprocess.Popen([sys.executable, '-c', WORKER, str(home), 'shared', str(UPDATES)], env=env,
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
             for _ in range(WORKERS)]

    results = []
    for p in procs:
        out, _ = p.communicate(timeout=600)
        results.append((p.returncode, out.decode('utf-8', 'replace')))

    # Every worker did all its updates, with the lock that was asked for
    expected_mode = 'soft' if mode == 'soft' else None
    pids = []
    for rc, out in results:
        assert rc == 0, out
        words = out.strip().splitlines()[-1].split()
        assert words[0] == 'OK', out
        pids.append(int(words[1]))
        if expected_mode is not None:
            assert words[2] == expected_mode, out
        else:
            assert words[2] != 'soft', out

    # Every key of every worker is in the meta
    meta_file = home / 'repos' / 'local' / 'log' / 'shared' / '_cmeta.json'
    meta = json.loads(meta_file.read_text(encoding='utf-8'))
    expected = {f'{pid}-{i}' for pid in pids for i in range(UPDATES)}
    assert set(meta['keys']) == expected, sorted(expected - set(meta['keys']))

    # The index holds the artifact once, at its folder
    with open(home / 'index' / 'log.pkl', 'rb') as f:
        index = pickle.load(f)
    records = [rec for rec in index['uids'].values() if os.path.basename(rec['path']).lower() == 'shared']
    assert len(records) == 1, records
    assert set(records[0]['cmeta'].get('keys', {})) == expected

    assert leftovers(home) == []


def test_an_update_that_reaches_the_index_last_brings_the_meta_of_the_file(home, monkeypatch):
    """An update writes the meta file under the file's lock and then the record of the index under the index
    lock. Between the two another update can do both: the index must end with the meta that is in the file,
    not with the older meta of the update that came to the index last. The order is forced here: the first
    update waits right before the index lock until a second one has finished."""
    from cmeta import repos as cmeta_repos

    real = cmeta_repos.Repos._lock_index
    paused = threading.Event()
    second_done = threading.Event()

    def lock_index(self, *args, **kwargs):
        if threading.current_thread().name == 'first' and not paused.is_set():
            paused.set()
            assert second_done.wait(120)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(cmeta_repos.Repos, '_lock_index', lock_index)

    results = {}

    def update(name, key):
        cm = CMeta(home=str(home))
        results[name] = cm.access({'category': 'log', 'command': 'update', 'arg1': 'shared',
                                   'meta': {'keys': {key: 1}}, 'con': False})

    # The first update writes the file and stops before the index; the second one does both in full
    first = threading.Thread(target=update, args=('first', 'from-first'), name='first')
    first.start()
    try:
        assert paused.wait(120)
        update('second', 'from-second')
    finally:
        second_done.set()
        first.join(120)

    assert results['first']['return'] == 0, results['first'].get('error')
    assert results['second']['return'] == 0, results['second'].get('error')

    meta_file = home / 'repos' / 'local' / 'log' / 'shared' / '_cmeta.json'
    assert set(json.loads(meta_file.read_text(encoding='utf-8'))['keys']) == {'from-first', 'from-second'}

    with open(home / 'index' / 'log.pkl', 'rb') as f:
        index = pickle.load(f)
    records = [rec for rec in index['uids'].values() if os.path.basename(rec['path']).lower() == 'shared']
    assert len(records) == 1, records
    assert set(records[0]['cmeta']['keys']) == {'from-first', 'from-second'}
