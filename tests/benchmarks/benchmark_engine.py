"""
A benchmark of the cMeta engine's hot paths: the index reads behind `find`, the locked index writes behind
`create`, `update`, `delete` and `reindex`, the full reindex, the reload of a changed index, and the primitives
they are built on (stat, file lock, record copy, pickle, atomic replace). It makes a home of its own with N
hand-made artifacts in one category and prints one table; with --json it also writes the numbers, and with
--compare <json> it prints every number next to the one of an earlier run (the before/after check of an engine
change). With --procs P it also lets P processes create artifacts in the same category at once and reports
the throughput and whether every record made it into the index.

    python tests/benchmarks/benchmark_engine.py --home <empty folder> --n 10000 --json before.json
    python tests/benchmarks/benchmark_engine.py --home <empty folder> --n 10000 --json after.json --compare before.json

Nothing outside --home is touched: CMETA_HOME is set to it for this process and its workers. The folder is
removed first when it holds the marker of an earlier run and refused otherwise. The pytest module next to
this file runs it with a small N as a smoke test; the numbers themselves are not asserted (the speed of a
CI runner varies).

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import argparse
import copy
import json
import os
import pickle
import platform
import random
import shutil
import statistics
import subprocess
import sys
import time

MARKER = '.cmeta-benchmark-home'
CATEGORY = 'log'
CATEGORY_REF = 'log,487a7639093a4685'
REPO_ALIAS = 'bench-repo'
REPO_UID = 'b0c4e5f6a7b8c9d0'
ENV_TO_DROP = ('CMETA_HOME', 'CMETA_HOME2', 'CMETA_VERBOSE', 'CMETA_DEBUG', 'CMETA_FAIL_ON_ERROR',
               'CMETA_INTERNAL_REPO_PATH', 'VIRTUAL_ENV', 'CONDA_PREFIX')


##########################################################################################
# Timing helpers

def timed_calls(fn, repeat):
    """Every call timed on its own; returns the list of durations in seconds."""
    times = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return times


class Results:
    """The measurements of one run: name -> median, min, max, unit, repeats, note."""

    UNITS = {'us': 1e6, 'ms': 1e3, 's': 1.0}

    def __init__(self):
        self.rows = {}
        self.order = []

    def add(self, name, times, unit, note=''):
        scale = self.UNITS[unit]
        row = {'median': statistics.median(times) * scale, 'min': min(times) * scale, 'max': max(times) * scale,
               'unit': unit, 'n': len(times), 'note': note}
        self.rows[name] = row
        self.order.append(name)
        print('  %-44s %12.2f %-3s (min %10.2f, max %10.2f, n=%d) %s' % (
            name, row['median'], unit, row['min'], row['max'], row['n'], note))
        return row

    def value(self, name, value, unit, note=''):
        row = {'median': value, 'min': value, 'max': value, 'unit': unit, 'n': 1, 'note': note}
        self.rows[name] = row
        self.order.append(name)
        print('  %-44s %12.2f %-3s %s' % (name, value, unit, note))
        return row


def section(title):
    print('')
    print('=== ' + title)


##########################################################################################
# The home with N hand-made artifacts

def prepare_home(home):
    if os.path.exists(home):
        if not os.path.isfile(os.path.join(home, MARKER)):
            sys.exit('refusing to remove %s: it is not the home of an earlier benchmark run (no %s)' % (home, MARKER))
        shutil.rmtree(home)
    os.makedirs(home)
    with open(os.path.join(home, MARKER), 'w') as f:
        f.write('made by tests/benchmarks/benchmark_engine.py - safe to delete\n')


def make_artifacts(home, n, seed=20261008):
    """A repository folder with N artifacts of the log category, written by hand (no engine call)."""
    rnd = random.Random(seed)
    repo = os.path.join(home, 'bench', REPO_ALIAS)
    cat_dir = os.path.join(repo, CATEGORY)
    os.makedirs(cat_dir)
    with open(os.path.join(repo, '_cmr.yaml'), 'w', encoding='utf-8') as f:
        f.write('artifact: %s,%s\ncategory: repo,f4f792ab40c7498f\n' % (REPO_ALIAS, REPO_UID))
    uids = []
    for i in range(n):
        alias = 'art-%06d' % i
        uid = '%016x' % rnd.getrandbits(64)
        uids.append(uid)
        folder = os.path.join(cat_dir, alias)
        os.mkdir(folder)
        with open(os.path.join(folder, '_cmeta.yaml'), 'w', encoding='utf-8') as f:
            f.write('artifact: %s,%s\ncategory: %s\ntags:\n  - bench\n  - g%d\n'
                    'desc: benchmark artifact number %d of the log category\nowner: benchmark\n'
                    'generator: script\n' % (alias, uid, CATEGORY_REF, i % 10, i))
    return repo, uids


##########################################################################################
# The lock candidates of the concurrency work (measured here, not used by the engine)

def candidate_lock(path, keep_file):
    """A lock that keeps the file at `path` the one every process locks: acquire, then check that the file
    opened is still the file at the path (it is not when another process removed it meanwhile); on release
    the file is removed BEFORE the lock is dropped (POSIX) or after the handle is closed (Windows, where a
    file still open elsewhere cannot be removed). With keep_file the lock file is never removed."""
    if os.name == 'nt':
        import msvcrt
        while True:
            try:
                fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
            except PermissionError:
                time.sleep(0.001)
                continue
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                return fd
            except OSError:
                os.close(fd)
                time.sleep(0.001)
    else:
        import fcntl
        while True:
            fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                os.close(fd)
                time.sleep(0.001)
                continue
            try:
                st = os.stat(path)
            except FileNotFoundError:
                st = None
            fst = os.fstat(fd)
            if st is None or (st.st_ino, st.st_dev) != (fst.st_ino, fst.st_dev):
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
                continue
            return fd


def candidate_unlock(path, fd, keep_file):
    if os.name == 'nt':
        import msvcrt
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        os.close(fd)
        if not keep_file:
            try:
                os.unlink(path)
            except OSError:
                pass
    else:
        import fcntl
        if not keep_file:
            try:
                os.unlink(path)
            except OSError:
                pass
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


##########################################################################################
# The worker of the concurrency measurement

def worker_create(home, prefix, count):
    for v in ENV_TO_DROP:
        os.environ.pop(v, None)
    os.environ['CMETA_HOME'] = home
    from cmeta import CMeta
    cm = CMeta(home=home)
    times = []
    errors = []
    for i in range(count):
        t0 = time.perf_counter()
        r = cm.access({'category': CATEGORY, 'command': 'create', 'arg1': '%s:%s-%04d' % (REPO_ALIAS, prefix, i),
                       'meta': {'tags': ['concurrent']}, 'yaml': True, 'con': False})
        times.append(time.perf_counter() - t0)
        if r['return'] > 0:
            errors.append(r.get('error', '?'))
    print(json.dumps({'times': times, 'errors': errors}))


def concurrent_creates(home, procs, per, results):
    section('Concurrent creates: %d processes x %d artifacts in the same category at once' % (procs, per))
    env = dict(os.environ)
    env['CMETA_HOME'] = home
    t0 = time.perf_counter()
    children = []
    for p in range(procs):
        children.append(subprocess.Popen([sys.executable, os.path.abspath(__file__), '--worker-create', 'cw%d' % p,
                                          str(per), '--home', home],
                                         stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env))
    times = []
    errors = []
    for child in children:
        out, err = child.communicate()
        try:
            data = json.loads(out.decode('utf-8', 'replace').strip().splitlines()[-1])
        except Exception:
            errors.append('worker output unreadable: %s %s' % (out[-300:], err[-300:]))
            continue
        times.extend(data['times'])
        errors.extend(data['errors'])
    wall = time.perf_counter() - t0
    results.value('concurrent creates: wall time', wall, 's', '%d creates' % (procs * per))
    if times:
        results.value('concurrent creates: creates per second', len(times) / wall, 's')
        results.add('concurrent create latency', times, 'ms')
    return errors


def check_index(home, cm, procs, per, results):
    """Every record the workers made is in the index, and the alias map agrees with the records."""
    r = cm.access({'category': CATEGORY, 'command': 'find', 'arg1': 'cw*', 'con': False})
    found = len(r.get('artifacts', [])) if r['return'] == 0 else 0
    expected = procs * per
    results.value('concurrent creates: records lost', expected - found, 's', 'of %d (0 = every write kept)' % expected)
    with open(os.path.join(home, 'index', CATEGORY + '.pkl'), 'rb') as f:
        index = pickle.load(f)
    uids = index['uids']
    bad = 0
    for alias, alias_uids in index['lowercase_aliases'].items():
        for uid in alias_uids:
            if uid not in uids:
                bad += 1
    for uid, rec in uids.items():
        alias = rec['cmeta_ref_parts'].get('artifact_alias_lowercase', rec['cmeta_ref_parts'].get('artifact_alias', '')).lower()
        if alias and uid not in index['lowercase_aliases'].get(alias, []):
            bad += 1
    results.value('index consistency: broken alias links', bad, 's', '0 = aliases and records agree')
    on_disk = 0
    cat_dir = os.path.join(home, 'bench', REPO_ALIAS, CATEGORY)
    for name in os.listdir(cat_dir):
        if name.startswith('cw'):
            on_disk += 1
    results.value('concurrent creates: folders on disk', on_disk, 's', 'of %d' % expected)


##########################################################################################
# CLI timings

def cli_timings(home, cx, results):
    section('CLI (a new process per call, as a user runs cx)')
    env = dict(os.environ)
    env['CMETA_HOME'] = home

    def run(args):
        r = subprocess.run([cx] + args, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if r.returncode != 0:
            raise RuntimeError('%s failed: %s' % (' '.join(args), r.stderr.decode('utf-8', 'replace')[-500:]))

    try:
        run(['--version'])
    except Exception as e:
        print('  cx not usable (%s), the CLI timings are skipped' % e)
        return
    results.add('cx --version', timed_calls(lambda: run(['--version']), 5), 'ms', 'process start + engine init')
    results.add('cx log find <alias>', timed_calls(lambda: run([CATEGORY, 'find', 'art-000001']), 5), 'ms')
    results.add('cx log reindex <alias>', timed_calls(lambda: run([CATEGORY, 'reindex', 'art-000001']), 3), 'ms')
    results.add('cx --reindex (full)', timed_calls(lambda: run(['--reindex']), 1), 's')


##########################################################################################
# Comparison with an earlier run

def compare(results, before_path):
    with open(before_path) as f:
        before = json.load(f)['results']
    section('Compared with ' + before_path + ' (ratio = now / before, by the medians)')
    print('  %-44s %12s %12s %8s' % ('measurement', 'before', 'now', 'ratio'))
    for name in results.order:
        now = results.rows[name]
        old = before.get(name)
        if old is None or old['unit'] != now['unit']:
            continue
        if old['median'] > 0:
            ratio = now['median'] / old['median']
            if 'per second' in name:                      # a rate: more is better
                flag = '  faster' if ratio > 1.25 else ('  slower' if ratio < 0.8 else '')
            elif name.endswith(('lost', 'links', 'on disk', 'index', 'size')):   # counts, not times
                flag = ''
            else:
                flag = '  slower' if ratio > 1.25 else ('  faster' if ratio < 0.8 else '')
            print('  %-44s %12.2f %12.2f %8.2f%s' % (name, old['median'], now['median'], ratio, flag))
        else:
            print('  %-44s %12.2f %12.2f %8s' % (name, old['median'], now['median'], '-'))


##########################################################################################

def main():
    parser = argparse.ArgumentParser(description='benchmark of the cMeta engine hot paths')
    parser.add_argument('--home', required=True, help='an empty folder (or the home of an earlier run) used as CMETA_HOME')
    parser.add_argument('--n', type=int, default=10000, help='artifacts in the category (default 10000)')
    parser.add_argument('--writes', type=int, default=100, help='creates/updates/reindexes/deletes timed (default 100)')
    parser.add_argument('--procs', type=int, default=4, help='processes of the concurrent-create measurement (0 = skip)')
    parser.add_argument('--per', type=int, default=25, help='creates per process in that measurement')
    parser.add_argument('--cli', action='store_true', help='also time the cx command line')
    parser.add_argument('--cx', default='cx', help='the cx executable for --cli')
    parser.add_argument('--json', help='write the numbers to this file')
    parser.add_argument('--compare', help='an earlier --json file to print the ratios against')
    parser.add_argument('--keep', action='store_true', help='keep the home after the run')
    parser.add_argument('--worker-create', nargs=2, metavar=('PREFIX', 'COUNT'), help=argparse.SUPPRESS)
    args = parser.parse_args()

    home = os.path.abspath(args.home)

    if args.worker_create:
        worker_create(home, args.worker_create[0], int(args.worker_create[1]))
        return

    for v in ENV_TO_DROP:
        os.environ.pop(v, None)
    os.environ['CMETA_HOME'] = home

    import cmeta
    from cmeta import CMeta
    from cmeta import utils

    results = Results()
    meta = {'python': sys.version.split()[0], 'platform': platform.platform(), 'machine': platform.machine(),
            'cmeta': cmeta.__version__, 'cmeta_path': os.path.dirname(cmeta.__file__), 'home': home, 'n': args.n,
            'pickle_default_protocol': pickle.DEFAULT_PROTOCOL, 'date': time.strftime('%Y-%m-%d %H:%M:%S')}
    section('Benchmark of the cMeta engine')
    for k in ('python', 'platform', 'cmeta', 'cmeta_path', 'home', 'n', 'pickle_default_protocol'):
        print('  %-24s %s' % (k, meta[k]))

    prepare_home(home)

    section('Engine start')
    t0 = time.perf_counter()
    cm = CMeta(home=home)
    results.value('CMeta() first run of a home', time.perf_counter() - t0, 'ms', 'the home and its index are made')
    results.add('CMeta() warm', timed_calls(lambda: CMeta(home=home), 5), 'ms', 'a new engine object on an existing home')

    section('Index build of %d hand-made artifacts' % args.n)
    t0 = time.perf_counter()
    repo, uids = make_artifacts(home, args.n)
    results.value('writing %d artifact folders by hand' % args.n, time.perf_counter() - t0, 's', 'not the engine')
    t0 = time.perf_counter()
    r = cm.access({'category': 'repo', 'command': 'plug', 'arg1': repo, 'con': False})
    assert r['return'] == 0, r.get('error')
    results.value('repo plug (incremental index of the repo)', time.perf_counter() - t0, 's')
    results.add('full reindex (cx --reindex)', timed_calls(lambda: cm.repos.reindex(con=False), 2), 's')
    index_file = os.path.join(home, 'index', CATEGORY + '.pkl')
    results.value('index file size', os.path.getsize(index_file) / 1024.0, 's', 'KB (unit column: KB)')
    with open(index_file, 'rb') as f:
        index_data = pickle.load(f)
    results.value('records in the index', len(index_data['uids']), 's', '(unit column: records)')

    section('Reads with a warm cache (the index already loaded in this process)')
    alias = 'art-%06d' % (args.n // 2)
    uid = uids[args.n // 2]

    def find(**p):
        p.setdefault('category', CATEGORY)
        p.setdefault('command', 'find')
        p.setdefault('con', False)
        return cm.access(p)

    r = find(arg1=alias)
    assert r['return'] == 0 and len(r['artifacts']) == 1, r
    results.add('find by alias (1 hit)', timed_calls(lambda: find(arg1=alias), 2000), 'us')
    results.add('find by UID (1 hit)', timed_calls(lambda: find(arg1=uid), 2000), 'us')
    results.add('find a missing alias (error 16)', timed_calls(lambda: find(arg1='no-such-artifact'), 2000), 'us')
    results.add('find by alias + tag filter', timed_calls(lambda: find(arg1=alias, tags='bench'), 1000), 'us')
    r = find(arg1='art-00*')
    hits = len(r.get('artifacts', []))
    results.add('find wildcard art-00* (%d hits)' % hits, timed_calls(lambda: find(arg1='art-00*'), 20), 'ms')
    r = find()
    hits = len(r.get('artifacts', []))
    results.add('find all (%d hits)' % hits, timed_calls(lambda: find(), 5), 'ms')
    r = find(tags='g3')
    hits = len(r.get('artifacts', []))
    results.add('find by tag g3 (%d hits)' % hits, timed_calls(lambda: find(tags='g3'), 5), 'ms', 'every record checked')

    section('Reads after the index changed (the reload a write by another process causes)')

    def bump_and_find():
        st = os.stat(index_file)
        os.utime(index_file, ns=(st.st_atime_ns, st.st_mtime_ns + 1000000000))
        r = find(arg1=alias)
        assert r['return'] == 0

    results.add('find by alias after a changed index', timed_calls(bump_and_find, 5), 'ms', 'the pickle load + 1 find')
    results.add('first find of a new engine object', timed_calls(lambda: CMeta(home=home).access(
        {'category': CATEGORY, 'command': 'find', 'arg1': alias, 'con': False}), 5), 'ms', 'CMeta() + load + find')

    section('Writes (each one rewrites the whole index file of the category under its lock)')
    w = args.writes

    def create(i):
        r = cm.access({'category': CATEGORY, 'command': 'create', 'arg1': '%s:new-%04d' % (REPO_ALIAS, i),
                       'meta': {'tags': ['new']}, 'yaml': True, 'con': False})
        assert r['return'] == 0, r.get('error')

    def update(i):
        r = cm.access({'category': CATEGORY, 'command': 'update', 'arg1': 'new-0000', 'meta': {'counter': i}, 'con': False})
        assert r['return'] == 0, r.get('error')

    def reindex_one():
        r = cm.access({'category': CATEGORY, 'command': 'reindex', 'arg1': alias, 'con': False})
        assert r['return'] == 0, r.get('error')

    def delete(i):
        r = cm.access({'category': CATEGORY, 'command': 'delete', 'arg1': 'new-%04d' % i, 'force': True, 'con': False})
        assert r['return'] == 0, r.get('error')

    times = []
    for i in range(w):
        t0 = time.perf_counter()
        create(i)
        times.append(time.perf_counter() - t0)
    results.add('create (meta file + index write)', times, 'ms')
    times = []
    for i in range(w):
        t0 = time.perf_counter()
        update(i)
        times.append(time.perf_counter() - t0)
    results.add('update (meta edit in place + index write)', times, 'ms')
    results.add('reindex one artifact', timed_calls(reindex_one, w), 'ms', 'folder scan + index write')
    times = []
    for i in range(w):
        t0 = time.perf_counter()
        delete(i)
        times.append(time.perf_counter() - t0)
    results.add('delete (index write + folder removal)', times, 'ms')

    section('Primitives (what one index read or write is made of)')
    results.add('os.stat of the index file', timed_calls(lambda: os.stat(index_file), 10000), 'us',
                '3 per find today (is_dir, exists, stat)')
    lock_target = os.path.join(home, 'index', 'lock-benchmark.bin')
    with open(lock_target, 'wb') as f:
        f.write(b'x')

    def engine_lock():
        lock = utils.files._acquire_lock(lock_target)
        utils.files._release_lock(lock_target, lock)

    results.add('engine lock acquire+release', timed_calls(engine_lock, 500), 'us', 'filelock + the lock file removed')
    try:
        from filelock import FileLock

        def library_lock():
            lock = FileLock(lock_target + '.lock')
            lock.acquire()
            lock.release()

        results.add('filelock acquire+release alone', timed_calls(library_lock, 500), 'us', 'the library by itself')
    except ImportError:
        pass
    cand = lock_target + '.cand'

    def cand_lock(keep):
        fd = candidate_lock(cand, keep)
        candidate_unlock(cand, fd, keep)

    results.add('candidate lock, file removed on release', timed_calls(lambda: cand_lock(False), 500), 'us',
                'verified identity, removed before release')
    results.add('candidate lock, file kept', timed_calls(lambda: cand_lock(True), 500), 'us', 'verified identity, never removed')
    try:
        os.unlink(cand)
    except OSError:
        pass

    records = list(index_data['uids'].values())

    def copy_level1(rec):
        c = dict(rec)
        c['cmeta'] = dict(rec['cmeta'])
        tags = c['cmeta'].get('tags')
        if isinstance(tags, list):
            c['cmeta']['tags'] = list(tags)
        return c

    def all_records(fn):
        for rec in records:
            fn(rec)

    results.add('copy of %d records: record.copy() (today)' % len(records), timed_calls(lambda: all_records(dict.copy), 5), 'ms')
    results.add('copy of %d records: record + cmeta + tags' % len(records), timed_calls(lambda: all_records(copy_level1), 5), 'ms',
                'the cheap copy that protects the cache')
    results.add('copy of %d records: deepcopy' % len(records), timed_calls(lambda: all_records(copy.deepcopy), 3), 'ms')

    for proto in sorted(set([4, 5, pickle.HIGHEST_PROTOCOL])):
        if proto > pickle.HIGHEST_PROTOCOL:
            continue
        data = pickle.dumps(index_data, protocol=proto)
        results.add('pickle dump of the index, protocol %d' % proto, timed_calls(lambda: pickle.dumps(index_data, protocol=proto), 5),
                    'ms', '%d KB' % (len(data) // 1024))
        results.add('pickle load of the index, protocol %d' % proto, timed_calls(lambda: pickle.loads(data), 5), 'ms')

    small = os.path.join(home, 'index', 'write-benchmark.yaml')
    payload = ('key%03d: value %d\n' % (i, i) for i in range(40))
    payload = ''.join(payload)

    def plain_write():
        with open(small, 'w', encoding='utf-8') as f:
            f.write(payload)

    def atomic_write():
        tmp = small + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(payload)
        os.replace(tmp, small)

    results.add('write a 1 KB file in place', timed_calls(plain_write, 500), 'us')
    results.add('write a 1 KB file atomically', timed_calls(atomic_write, 500), 'us', 'temp file + os.replace')
    for p in (small, lock_target):
        try:
            os.unlink(p)
        except OSError:
            pass

    errors = []
    if args.procs > 0:
        errors = concurrent_creates(home, args.procs, args.per, results)
        check_index(home, cm, args.procs, args.per, results)
        if errors:
            print('  worker errors (%d): %s' % (len(errors), errors[:3]))

    if args.cli:
        cli_timings(home, args.cx, results)

    if args.compare:
        compare(results, args.compare)

    if args.json:
        with open(args.json, 'w') as f:
            json.dump({'meta': meta, 'results': {k: results.rows[k] for k in results.order}, 'worker_errors': errors}, f, indent=1)
        print('')
        print('numbers written to ' + args.json)

    if not args.keep:
        shutil.rmtree(home, ignore_errors=True)


if __name__ == '__main__':
    main()
