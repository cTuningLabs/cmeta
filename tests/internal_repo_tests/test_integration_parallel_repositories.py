"""
Integration test of parallel manipulations of the repositories of one home: while one process indexes two
repositories again and again (`cx repo reindex`; one of them declares categories), another creates, updates and
deletes artifacts in a third repository (in the engine's log category and in a declared one), another unplugs
and plugs a fourth one, another rebuilds the whole index, and a fifth process looks the records of the first two
up all the time. Every incremental index, every full rebuild and every write of a record runs under the one index
lock and readers never lock, so: a record of a repository that is only indexed again is found at every moment,
every writer succeeds, and at the end the index is what a full rebuild makes of the disk - no record lost or left
over, no lock or temporary file left behind.

Each test runs against a fresh <CMETA_HOME> in tmp_path so it does not touch the user's real cMeta state.

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import pickle
import subprocess
import sys

import pytest

from cmeta import CMeta

CATEGORIES = {'cat-x': 'c1b2c3d4e5f60001', 'cat-y': 'c1b2c3d4e5f60002'}
LOG = 'log,487a7639093a4685'
REPO_UIDS = {'a': 'a1b2c3d4e5f60200', 'b': 'a1b2c3d4e5f60201', 'c': 'a1b2c3d4e5f60202', 'd': 'a1b2c3d4e5f60203'}

# The reindexer: the repositories named, again and again
REINDEXER = r'''
import sys
from cmeta import CMeta
home, n, aliases = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
cm = CMeta(home=home)
for i in range(n):
    for alias in aliases:
        r = cm.access({'category': 'repo', 'command': 'reindex', 'arg1': alias, 'con': False})
        if r['return'] > 0:
            print('ERROR reindex', alias, r.get('error'), flush=True)
            sys.exit(3)
print('OK', flush=True)
'''

# The churner: creates, updates and deletes every other one of its artifacts in one repository, in the engine's log
# category and in a category another repository declares; prints what it kept as category:alias
CHURNER = r'''
import os, sys
from cmeta import CMeta
home, repo, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
cm = CMeta(home=home)
kept = []
for i in range(n):
    category = 'log' if i % 3 else 'cat-x'
    alias = 'churn-%03d' % i
    for command, extra in (('create', {'meta': {'n': i}, 'yaml': True}), ('update', {'meta': {'touched': True}})):
        r = cm.access(dict({'category': category, 'command': command, 'arg1': '%s:%s' % (repo, alias), 'con': False}, **extra))
        if r['return'] > 0:
            print('ERROR', command, alias, r.get('error'), flush=True)
            sys.exit(3)
    if i % 2 == 0:
        r = cm.access({'category': category, 'command': 'delete', 'arg1': '%s:%s' % (repo, alias), 'force': True, 'con': False})
        if r['return'] > 0:
            print('ERROR delete', alias, r.get('error'), flush=True)
            sys.exit(3)
    else:
        kept.append('%s:%s' % (category, alias))
print('OK', ' '.join(kept), flush=True)
'''

# The rebuilder: the full reindex, a few times
REBUILDER = r'''
import sys
from cmeta import CMeta
home, n = sys.argv[1], int(sys.argv[2])
cm = CMeta(home=home)
for i in range(n):
    r = cm.repos.reindex()
    if r['return'] > 0:
        print('ERROR full reindex', r.get('error'), flush=True)
        sys.exit(3)
print('OK', flush=True)
'''

# The plugger: one repository unplugged and plugged again, again and again; it ends plugged
PLUGGER = r'''
import sys
from cmeta import CMeta
home, alias, path, n = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
cm = CMeta(home=home)
for i in range(n):
    for command, arg1 in (('unplug', alias), ('plug', path)):
        r = cm.access({'category': 'repo', 'command': command, 'arg1': arg1, 'con': False})
        if r['return'] > 0:
            print('ERROR', command, r.get('error'), flush=True)
            sys.exit(3)
print('OK', flush=True)
'''

# The finder: the records named (category:alias) must be found, exactly once, at every try
FINDER = r'''
import sys
from cmeta import CMeta
home, n = sys.argv[1], int(sys.argv[2])
wanted = [w.split(':') for w in sys.argv[3:]]
cm = CMeta(home=home)
misses = 0
for i in range(n):
    for category, alias in wanted:
        r = cm.access({'category': category, 'command': 'find', 'arg1': alias, 'con': False})
        if r['return'] > 0 or len(r['artifacts']) != 1:
            misses += 1
            print('MISS', category, alias, r.get('error', len(r.get('artifacts', []))), flush=True)
print('OK', misses, flush=True)
'''


def make_repo(path, alias, uid, declare_categories=False):
    path.mkdir(parents=True, exist_ok=True)
    (path / '_cmr.yaml').write_text(f'artifact: {alias},{uid}\ncategory: repo,f4f792ab40c7498f\n', encoding='utf-8')

    if declare_categories:
        for name, cuid in CATEGORIES.items():
            folder = path / 'category' / name
            folder.mkdir(parents=True)
            (folder / '_cmeta.yaml').write_text(f'artifact: {name},{cuid}\ncategory: category,dd9ea50e7f76467f\n', encoding='utf-8')


def make_artifact(repo, category, alias, uid):
    folder = repo / category / alias
    folder.mkdir(parents=True)
    ref = LOG if category == 'log' else f'{category},{CATEGORIES[category]}'
    (folder / '_cmeta.yaml').write_text(f'artifact: {alias},{uid}\ncategory: {ref}\n', encoding='utf-8')


def env_for(home):
    env = {k: v for k, v in os.environ.items() if not k.startswith('CMETA_') and k not in ('VIRTUAL_ENV', 'CONDA_PREFIX')}
    env['CMETA_HOME'] = str(home)
    env['PYTHONIOENCODING'] = 'utf-8'
    return env


def start(code, home, *args):
    return subprocess.Popen([sys.executable, '-c', code, str(home)] + [str(a) for a in args], env=env_for(home),
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def finish(proc, timeout=900):
    out, _ = proc.communicate(timeout=timeout)
    return proc.returncode, out.decode('utf-8', 'replace')


def index_records(home):
    """{uid: (file, repository uid, path)} of every category file of the index (repo.pkl and category.pkl left out),
    and the alias map of each file."""
    found = {}
    aliases = {}
    index = os.path.join(home, 'index')

    for name in sorted(os.listdir(index)):
        if not name.endswith('.pkl') or name in ('repo.pkl', 'category.pkl'):
            continue

        with open(os.path.join(index, name), 'rb') as f:
            data = pickle.load(f)

        for uid, rec in data['uids'].items():
            found[uid] = (name, rec['cmeta_ref_parts'].get('repo_uid'), os.path.normcase(os.path.normpath(rec['path'])))
        if data['lowercase_aliases']:
            # (an incremental run leaves an empty file for a category without artifacts, a full rebuild none)
            aliases[name] = {alias: sorted(uids) for alias, uids in data['lowercase_aliases'].items()}

    return found, aliases


def leftovers(home):
    """The files a lock, an atomic write or a take-over leaves when something went wrong."""
    found = []
    for top, dirs, names in os.walk(home):
        for name in names:
            if name.endswith(('.lock', '.tmp')) or '.take-' in name:
                found.append(os.path.join(top, name))
    return found


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """Four repositories: a declares the categories and holds artifacts of both, b holds artifacts of both, c is
    empty (the churner's), d holds log artifacts (the plugger's)."""
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE',
                'CMETA_FAIL_ON_ERROR', 'CMETA_INDEX_LOCK_TIMEOUT', 'CMETA_LOCK_TIMEOUT', 'CMETA_SOFT_LOCK_PATHS'):
        monkeypatch.delenv(var, raising=False)
    home = tmp_path / 'home'
    monkeypatch.setenv('CMETA_HOME', str(home))

    repos = {}
    for ri, alias in enumerate(('a', 'b', 'c', 'd')):
        repo = tmp_path / alias
        make_repo(repo, alias, REPO_UIDS[alias], declare_categories=(alias == 'a'))
        if alias in ('a', 'b'):
            for ci, category in enumerate(CATEGORIES):
                for k in range(10):
                    make_artifact(repo, category, f'{alias}-{category}-{k:02d}', f'b1b2c3d4e5f6{ri}{ci}{k:02d}')
        if alias == 'd':
            for k in range(10):
                make_artifact(repo, 'log', f'd-log-{k:02d}', f'b1b2c3d4e5f6{ri}9{k:02d}')
        repos[alias] = repo

    cm = CMeta(home=str(home))
    for alias in ('a', 'b', 'c', 'd'):
        r = cm.access({'category': 'repo', 'command': 'plug', 'arg1': str(repos[alias]), 'con': False})
        assert r['return'] == 0, r.get('error')

    return cm, home, repos


def test_parallel_reindexes_writes_plugs_and_finds_leave_a_consistent_index(home):
    cm, home, repos = home
    wanted = [f'{category}:{alias}-{category}-{k:02d}' for alias in ('a', 'b') for category in CATEGORIES for k in (0, 5, 9)]

    procs = {
        'reindexer': start(REINDEXER, home, 12, 'a', 'b'),
        'churner': start(CHURNER, home, 'c', 24),
        'plugger': start(PLUGGER, home, 'd', str(repos['d']), 6),
        'rebuilder': start(REBUILDER, home, 3),
        'finder': start(FINDER, home, 100, *wanted),
    }
    results = {name: finish(proc) for name, proc in procs.items()}

    # Every worker did all its work; the finder never missed a record of a or b
    for name, (rc, out) in results.items():
        assert rc == 0, f'{name}: {out}'
    assert results['finder'][1].strip().splitlines()[-1] == 'OK 0', results['finder'][1]
    kept = set(results['churner'][1].strip().splitlines()[-1].split()[1:])

    # The index is what a full rebuild makes of the disk: the same records at the same paths, the same aliases
    records, aliases = index_records(home)
    assert cm.repos.reindex()['return'] == 0
    rebuilt_records, rebuilt_aliases = index_records(home)
    assert records == rebuilt_records
    assert aliases == rebuilt_aliases
    assert all(os.path.isdir(path) for (_, _, path) in records.values())

    # What the churner kept is there, what it deleted is not; d's records are back; a's and b's are all there
    assert {name[:-4] + ':' + os.path.basename(path) for (name, repo_uid, path) in records.values()
            if repo_uid == REPO_UIDS['c']} == kept
    assert len([1 for (name, repo_uid, path) in records.values() if repo_uid == REPO_UIDS['d']]) == 10
    for alias in ('a', 'b'):
        assert len([1 for (name, repo_uid, path) in records.values() if repo_uid == REPO_UIDS[alias]]) == 20

    assert leftovers(home) == []
