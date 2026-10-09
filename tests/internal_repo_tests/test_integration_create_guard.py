"""
Integration tests of a create under the index lock and of the writes around it: creates of one artifact
at once make one artifact, a create whose record cannot be written leaves nothing behind (and says who
holds the lock), the index of repositories takes the lock of repos.json, a find result can be edited
without changing the cached index of the process.

Each test runs against a fresh <CMETA_HOME> in tmp_path so it does not touch the user's real cMeta
state.

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


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX',
                'CMETA_DEBUG', 'CMETA_VERBOSE', 'CMETA_FAIL_ON_ERROR', 'CMETA_INDEX_LOCK_TIMEOUT', 'CMETA_LOCK_TIMEOUT'):
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


HOLDER = r'''
import sys, time
from cmeta.utils import files
lock = files.PathLock(sys.argv[1]).acquire(timeout=60, note=sys.argv[2])
print('LOCKED', flush=True)
time.sleep(float(sys.argv[3]))
lock.release()
'''


def hold(lock_file, note, seconds=60):
    """Another process holds `lock_file` with `note` for `seconds`; returns once it holds it."""
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    p = subprocess.Popen([sys.executable, '-c', HOLDER, str(lock_file), note, str(seconds)], env=env,
                         stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    line = p.stdout.readline().decode('utf-8', 'replace')
    assert 'LOCKED' in line, line
    return p


def stop(p):
    p.kill()
    p.communicate()


def index_aliases(tmp_path, category='log'):
    """(the lowercase aliases of the index, {uid: path}) of a category as the pickle on disk holds them."""
    with open(tmp_path / 'index' / f'{category}.pkl', 'rb') as f:
        data = pickle.load(f)
    return set(data['lowercase_aliases']), {uid: rec['path'] for uid, rec in data['uids'].items()}


def folders(home, category='log'):
    base = home / 'repos' / 'local' / category
    return {p.name.lower() for p in base.iterdir() if p.is_dir()} if base.is_dir() else set()


def test_creates_of_one_alias_at_once_make_one_artifact(cm, tmp_path):
    make(cm, 'present')

    procs = [start(['log', 'create', 'twin'], tmp_path) for _ in range(6)]
    results = [finish(p) for p in procs]

    codes = [rc for rc, _ in results]
    assert codes.count(0) == 1, results
    for rc, out in results:
        if rc != 0:
            assert rc == 8 and 'already exist' in out, (rc, out)

    aliases, paths = index_aliases(tmp_path)
    assert folders(tmp_path) == {'present', 'twin'}
    assert aliases == {'present', 'twin'}
    assert len([uid for uid, path in paths.items() if os.path.basename(path).lower() == 'twin']) == 1
    assert all(os.path.isdir(p) for p in paths.values())
    assert not (tmp_path / 'index.lock').exists()


def test_a_create_whose_record_cannot_be_written_leaves_nothing_behind(cm, tmp_path):
    make(cm, 'present')
    index_file = tmp_path / 'index' / 'log.pkl'

    holder = hold(str(index_file) + '.lock', 'a test holding the index file')
    try:
        t0 = time.time()
        rc, out = finish(start(['log', 'create', 'late'], tmp_path, CMETA_LOCK_TIMEOUT='5'), timeout=120)
        elapsed = time.time() - t0
    finally:
        stop(holder)

    assert rc != 0, out
    assert 'is locked by another process (a test holding the index file)' in out and 'the read of' in out, out
    assert 'stayed locked by another process (a test holding the index file)' in out and 'CMETA_LOCK_TIMEOUT' in out, out
    assert 4.5 <= elapsed < 60, elapsed

    # Nothing of the failed create is left: no folder, no record, no index lock
    assert folders(tmp_path) == {'present'}
    assert index_aliases(tmp_path)[0] == {'present'}
    assert not (tmp_path / 'index.lock').exists()


def test_the_index_of_repositories_takes_the_lock_of_repos_json(cm, tmp_path):
    make(cm, 'present')

    holder = hold(str(tmp_path / 'repos.json') + '.lock', 'a test holding repos.json')
    try:
        rc, out = finish(start(['repo', 'reindex', 'local'], tmp_path, CMETA_LOCK_TIMEOUT='2'), timeout=120)
    finally:
        stop(holder)

    assert rc != 0, out
    assert 'repos.json' in out and 'stayed locked by another process (a test holding repos.json)' in out, out
    assert index_aliases(tmp_path)[0] == {'present'}
    assert not (tmp_path / 'index.lock').exists()

    # Released: the same command works
    rc, out = finish(start(['repo', 'reindex', 'local'], tmp_path), timeout=120)
    assert rc == 0, out
    assert index_aliases(tmp_path)[0] == {'present'}


def test_a_find_result_can_be_edited_without_changing_the_index_of_the_process(cm, tmp_path):
    make(cm, 'tagged', tags=['one'])

    r = cm.access({'category': 'log', 'command': 'find', 'arg1': 'tagged', 'con': False})
    assert r['return'] == 0, r.get('error')
    artifact = r['artifacts'][0]
    artifact['cmeta']['tags'].append('added-by-the-caller')
    artifact['cmeta']['new_key'] = 1
    artifact['cmeta_ref_parts'] = {'replaced': True}
    artifact['path'] = 'elsewhere'

    # The same through a tag filter (the records are copied after the filters, for what is returned)
    r = cm.access({'category': 'log', 'command': 'find', 'arg1': 'tagged', 'tags': 'one', 'con': False})
    assert r['return'] == 0, r.get('error')
    assert r['artifacts'][0]['cmeta']['tags'] == ['one']
    r['artifacts'][0]['cmeta']['tags'].append('added-through-the-filter')

    r = cm.access({'category': 'log', 'command': 'find', 'arg1': 'tagged', 'con': False})
    assert r['return'] == 0, r.get('error')
    again = r['artifacts'][0]
    assert again['cmeta']['tags'] == ['one']
    assert 'new_key' not in again['cmeta']
    assert again['cmeta_ref_parts']['artifact_alias'] == 'tagged'
    assert again['path'] != 'elsewhere'
