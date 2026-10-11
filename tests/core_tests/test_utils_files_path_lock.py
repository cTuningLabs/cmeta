"""
Tests of the engine's own path lock (`cmeta.utils.files.PathLock`, behind `_acquire_lock` / `_release_lock`,
`safe_read_file(lock=True, keep_locked=True)`, `safe_write_file`, `safe_delete_directory`, `lock_path`):
one holder at a time across processes and across the threads of one process on every platform; the lock
file is created for the operation and removed by the process that releases it; a lock file removed under a
waiter is detected (the identity check) and never leads to two holders; a killed holder blocks nobody; the
soft lock used where the file system refuses OS locks, with its stale files; timeouts; the engine's own
read-modify-write cycle under contention.

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import json
import os
import subprocess
import sys
import threading
import time

import pytest

from cmeta.utils import files

POSIX = sys.platform != 'win32'


##########################################################################################
# Workers run as separate processes

COUNTER_WORKER = r'''
import os, sys, time
from cmeta.utils import files
mode, target, log_path, n = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
if len(sys.argv) > 5 and sys.argv[5] == 'soft':
    files._lock_soft_paths.add(target + '.lock')
pid = os.getpid()
for i in range(n):
    if mode == 'pathlock':
        lock = files.PathLock(target + '.lock').acquire(timeout=120)
        try:
            try:
                with open(target) as f:
                    v = int(f.read().strip() or '0')
            except FileNotFoundError:
                v = 0
            time.sleep(0.0005)
            with open(target, 'w') as f:
                f.write(str(v + 1))
            with open(log_path, 'a') as f:
                f.write('%d %d %s\n' % (pid, i, lock.mode))
        finally:
            lock.release()
    else:
        r = files.safe_read_file(target, lock=True, keep_locked=True, timeout=120)
        if r['return'] > 0:
            print('ERROR read', r['error']); sys.exit(3)
        data = r['data']
        data['n'] = data.get('n', 0) + 1
        time.sleep(0.0005)
        r = files.safe_write_file(target, data, file_lock=r['file_lock'], atomic=True, timeout=120)
        if r['return'] > 0:
            print('ERROR write', r['error']); sys.exit(4)
print('OK', pid)
'''

HOLDER = r'''
import sys, time
from cmeta.utils import files
lock = files.PathLock(sys.argv[1]).acquire(timeout=60)
print('LOCKED', lock.mode, flush=True)
time.sleep(float(sys.argv[2]) if len(sys.argv) > 2 else 60)
lock.release()
print('RELEASED', flush=True)
'''

HOOKED_WAITER = r'''
import os, sys, time
from cmeta.utils import files
lock_file, marker, go, out = sys.argv[1:5]
real = files.fcntl.flock
state = {'first': True}
def hooked(fd, op):
    # The first lock attempt: the file is open (the old file), tell the test and wait for its go
    if state['first'] and (op & files.fcntl.LOCK_NB):
        state['first'] = False
        open(marker, 'w').close()
        while not os.path.exists(go):
            time.sleep(0.002)
    return real(fd, op)
files.fcntl.flock = hooked
lock = files.PathLock(lock_file)
lock.acquire(timeout=60)
same = files.PathLock._identity(os.fstat(lock._fd)) == files.PathLock._identity(os.stat(lock_file))
with open(out, 'w') as f:
    f.write('%f %d %s %s\n' % (time.time(), lock.identity_retries, lock.mode, same))
lock.release()
'''


def run_workers(script, args_list, timeout=600):
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    procs = [subprocess.Popen([sys.executable, '-c', script] + [str(a) for a in args],
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
             for args in args_list]
    outputs = []
    for p in procs:
        out, _ = p.communicate(timeout=timeout)
        outputs.append((p.returncode, out.decode('utf-8', 'replace')))
    return outputs


def start(script, *args):
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    # The workers never read their input: an explicit null input keeps them independent of the
    # parent's standard-input handle (which some agent and service environments leave unusable)
    return subprocess.Popen([sys.executable, '-c', script] + [str(a) for a in args],
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)


def wait_for(path, seconds=30):
    deadline = time.time() + seconds
    while not os.path.exists(path):
        if time.time() > deadline:
            raise AssertionError(f'{path} did not appear in {seconds} s')
        time.sleep(0.005)


##########################################################################################
# The lock object

def test_one_holder_at_a_time_and_the_file_is_removed_on_release(tmp_path):
    lock_file = str(tmp_path / 'thing.lock')
    first = files.PathLock(lock_file).acquire(timeout=5)
    assert first.is_locked and first.mode in ('windows', 'flock', 'lockf', 'soft')
    assert os.path.isfile(lock_file)

    second = files.PathLock(lock_file)
    t0 = time.monotonic()
    with pytest.raises(TimeoutError):
        second.acquire(timeout=0.3)
    assert 0.25 <= time.monotonic() - t0 < 3
    assert not second.is_locked

    first.release()
    assert not first.is_locked
    assert not os.path.exists(lock_file)

    second.acquire(timeout=5)
    assert second.is_locked
    second.release()
    assert not os.path.exists(lock_file)


def test_context_manager_double_release_and_check(tmp_path):
    target = str(tmp_path / 'file.json')
    with files.PathLock(target + '.lock') as lock:
        assert lock.is_locked
        files._check_lock(target, lock)
    assert not lock.is_locked
    lock.release()   # a second release is harmless
    with pytest.raises(TimeoutError):
        files._check_lock(target, lock)
    assert not os.path.exists(target + '.lock')


def test_lock_path_and_unlock_path(tmp_path):
    target = str(tmp_path / 'folder')
    r = files.lock_path(target, timeout=5)
    assert r['return'] == 0 and r['file_lock'].is_locked
    assert os.path.isfile(target + '.lock')
    r2 = files.lock_path(target, timeout=0.2)
    assert r2['return'] > 0
    assert files.unlock_path(target, r['file_lock'])['return'] == 0
    assert not os.path.exists(target + '.lock')


def test_a_missing_folder_is_an_error_not_a_wait(tmp_path):
    t0 = time.monotonic()
    with pytest.raises(TimeoutError):
        files._acquire_lock(str(tmp_path / 'no-such-folder' / 'file'), timeout=5)
    assert time.monotonic() - t0 < 2


def test_threads_of_one_process_exclude_each_other(tmp_path):
    target = str(tmp_path / 'counter.txt')
    state = {'value': 0, 'inside': 0, 'overlap': 0, 'modes': set()}

    def work():
        for _ in range(50):
            lock = files.PathLock(target + '.lock').acquire(timeout=60)
            try:
                state['inside'] += 1
                if state['inside'] > 1:
                    state['overlap'] += 1
                v = state['value']
                time.sleep(0.0002)
                state['value'] = v + 1
                state['modes'].add(lock.mode)
                state['inside'] -= 1
            finally:
                lock.release()

    threads = [threading.Thread(target=work) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert state['value'] == 16 * 50
    assert state['overlap'] == 0
    assert not os.path.exists(target + '.lock')


def test_a_thread_waiting_on_another_thread_times_out_instead_of_hanging(tmp_path):
    lock_file = str(tmp_path / 'held.lock')
    held = files.PathLock(lock_file).acquire(timeout=5)
    result = {}

    def waiter():
        t0 = time.monotonic()
        try:
            files.PathLock(lock_file).acquire(timeout=0.3)
            result['got'] = True
        except TimeoutError as e:
            result['error'] = str(e)
        result['seconds'] = time.monotonic() - t0

    t = threading.Thread(target=waiter)
    t.start()
    t.join(10)
    assert 'error' in result and 'thread' in result['error']
    assert 0.25 <= result['seconds'] < 3
    held.release()


##########################################################################################
# Processes

def test_processes_exclude_each_other_through_pathlock(tmp_path):
    target = str(tmp_path / 'counter.txt')
    log_path = str(tmp_path / 'log.txt')
    outputs = run_workers(COUNTER_WORKER, [('pathlock', target, log_path, 60)] * 8)
    for rc, out in outputs:
        assert rc == 0 and out.startswith('OK'), out
    with open(target) as f:
        assert int(f.read().strip()) == 8 * 60
    with open(log_path) as f:
        lines = f.read().splitlines()
    assert len(lines) == 8 * 60 and len(set(lines)) == 8 * 60
    assert not os.path.exists(target + '.lock')


def test_the_engine_read_modify_write_cycle_under_contention(tmp_path):
    target = str(tmp_path / 'index.json')
    with open(target, 'w') as f:
        json.dump({'n': 0}, f)
    outputs = run_workers(COUNTER_WORKER, [('engine', target, '', 40)] * 6)
    for rc, out in outputs:
        assert rc == 0 and out.startswith('OK'), out
    with open(target) as f:
        assert json.load(f)['n'] == 6 * 40
    assert not os.path.exists(target + '.lock')
    assert not os.path.exists(target + '.tmp')


def test_a_killed_holder_blocks_nobody(tmp_path):
    lock_file = str(tmp_path / 'crash.lock')
    holder = start(HOLDER, lock_file, 60)
    line = holder.stdout.readline().decode('utf-8', 'replace')
    assert line.startswith('LOCKED'), line
    assert os.path.isfile(lock_file)

    with pytest.raises(TimeoutError):
        files.PathLock(lock_file).acquire(timeout=0.3)

    holder.kill()
    holder.wait(30)

    t0 = time.monotonic()
    lock = files.PathLock(lock_file).acquire(timeout=10)
    assert time.monotonic() - t0 < 5
    lock.release()
    assert not os.path.exists(lock_file)


@pytest.mark.skipif(POSIX, reason='Windows: a lock file held by another process cannot be removed')
def test_windows_keeps_a_held_lock_file_from_being_removed(tmp_path):
    lock_file = str(tmp_path / 'held.lock')
    holder = start(HOLDER, lock_file, 60)
    assert holder.stdout.readline().decode('utf-8', 'replace').startswith('LOCKED')
    with pytest.raises(PermissionError):
        os.remove(lock_file)
    holder.kill()
    holder.wait(30)


@pytest.mark.skipif(not POSIX, reason='the identity check is a POSIX matter (flock on a removed file)')
def test_a_lock_file_removed_under_a_waiter_never_gives_two_holders(tmp_path):
    """The race of the previous lock, replayed deterministically: a waiter has opened the lock file (A) and is
    about to flock it when the holder removes A and releases, and a newcomer creates B and holds it. The waiter's
    flock on A succeeds (nobody holds A any more) - and the identity check sends it back to try B."""
    lock_file = str(tmp_path / 'race.lock')
    marker, go, out = str(tmp_path / 'marker'), str(tmp_path / 'go'), str(tmp_path / 'out')

    holder = files.PathLock(lock_file).acquire(timeout=5)
    waiter = start(HOOKED_WAITER, lock_file, marker, go, out)
    wait_for(marker)                       # the waiter has opened A

    holder.release()                       # A is removed, then released
    assert not os.path.exists(lock_file)
    newcomer = files.PathLock(lock_file).acquire(timeout=5)   # B
    open(go, 'w').close()

    time.sleep(0.5)
    assert not os.path.exists(out), 'the waiter acquired while the newcomer held B'

    released_at = time.time()
    newcomer.release()
    waiter.wait(60)
    assert waiter.returncode == 0, waiter.stdout.read().decode('utf-8', 'replace')
    with open(out) as f:
        acquired_at, retries, mode, same = f.read().split()
    assert float(acquired_at) >= released_at - 0.001
    assert int(retries) >= 1
    assert mode == 'flock' and same == 'True'
    assert not os.path.exists(lock_file)


@pytest.mark.skipif(not POSIX, reason='on Windows the file cannot be removed while it is held')
def test_release_leaves_a_lock_file_that_is_not_its_own(tmp_path):
    lock_file = str(tmp_path / 'mine.lock')
    mine = files.PathLock(lock_file).acquire(timeout=5)
    os.unlink(lock_file)                   # a third party removed it ...
    with open(lock_file, 'w') as f:        # ... and another process made a new one
        f.write('theirs')
    mine.release()
    assert os.path.isfile(lock_file)       # theirs is kept
    with open(lock_file) as f:
        assert f.read() == 'theirs'
    os.unlink(lock_file)


##########################################################################################
# The soft lock (where the file system refuses OS locks)

@pytest.fixture()
def soft(monkeypatch, tmp_path):
    lock_file = str(tmp_path / 'soft.lock')
    monkeypatch.setattr(files, '_lock_soft_paths', {lock_file})
    return lock_file


def test_soft_lock_holds_pid_and_host_and_is_removed_on_release(soft, caplog):
    lock = files.PathLock(soft).acquire(timeout=5)
    assert lock.mode == 'soft'
    with open(soft) as f:
        pid, host, when = f.read().split()
    assert int(pid) == os.getpid() and host == files._lock_host_name()
    with pytest.raises(TimeoutError):
        files.PathLock(soft).acquire(timeout=0.3)
    assert os.path.isfile(soft)
    lock.release()
    assert not os.path.exists(soft)


def test_soft_lock_excludes_processes(tmp_path):
    target = str(tmp_path / 'counter.txt')
    log_path = str(tmp_path / 'log.txt')
    outputs = run_workers(COUNTER_WORKER, [('pathlock', target, log_path, 30, 'soft')] * 4)
    for rc, out in outputs:
        assert rc == 0 and 'OK' in out, out
        assert 'stale' not in out, out      # every holder is alive here: a "stale" removal would be a misjudgement
    with open(target) as f:
        assert int(f.read().strip()) == 4 * 30
    with open(log_path) as f:
        lines = f.read().splitlines()
    assert len(lines) == 4 * 30 and all(line.endswith(' soft') for line in lines)
    assert not os.path.exists(target + '.lock')


def test_a_stale_soft_lock_of_a_dead_process_is_removed(soft, caplog, monkeypatch):
    gone = subprocess.Popen([sys.executable, '-c', 'pass'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    gone.wait()
    with open(soft, 'w') as f:
        f.write(f'{gone.pid} {files._lock_host_name()} {time.time():.3f}\n')
    caplog.set_level('WARNING', logger='cmeta.utils.files')

    # Fresh, the file of a dead pid is a release in flight: waited for
    with pytest.raises(TimeoutError):
        files.PathLock(soft).acquire(timeout=0.3)
    assert os.path.isfile(soft)

    old = time.time() - 2 * files.LOCK_SOFT_DEAD_MIN_AGE_SECONDS
    os.utime(soft, (old, old))
    lock = files.PathLock(soft).acquire(timeout=5)
    assert lock.mode == 'soft'
    with open(soft) as f:
        assert int(f.read().split()[0]) == os.getpid()
    assert any('stale' in rec.getMessage() for rec in caplog.records)
    lock.release()


def test_a_soft_lock_marked_released_or_an_old_empty_one_is_cleared(soft, monkeypatch):
    # A holder that could not remove its file (a reader held it open on Windows for too long) marks it released
    with open(soft, 'w') as f:
        f.write('released 12345\n')
    lock = files.PathLock(soft).acquire(timeout=5)
    assert lock.mode == 'soft'
    lock.release()
    assert not os.path.exists(soft)

    # A fresh lock file of a live holder is never taken for a stale one, whatever the check says
    monkeypatch.setattr(files, '_lock_pid_alive', lambda pid: False)
    with open(soft, 'w') as f:
        f.write(f'{os.getpid()} {files._lock_host_name()} {time.time():.3f}\n')
    with pytest.raises(TimeoutError):
        files.PathLock(soft).acquire(timeout=0.3)
    old = time.time() - 2 * files.LOCK_SOFT_DEAD_MIN_AGE_SECONDS
    os.utime(soft, (old, old))
    lock = files.PathLock(soft).acquire(timeout=5)
    assert lock.mode == 'soft'
    lock.release()
    assert not os.path.exists(soft)

    # An empty lock file is a leftover of an OS-lock attempt (a soft holder writes its content at once):
    # fresh, it is waited for; old, it is cleared
    open(soft, 'w').close()
    monkeypatch.setattr(files, 'LOCK_SOFT_EMPTY_STALE_SECONDS', 30.0)
    with pytest.raises(TimeoutError):
        files.PathLock(soft).acquire(timeout=0.3)
    monkeypatch.setattr(files, 'LOCK_SOFT_EMPTY_STALE_SECONDS', 0.0)
    lock = files.PathLock(soft).acquire(timeout=5)
    assert lock.mode == 'soft'
    lock.release()
    assert not os.path.exists(soft)


def test_a_soft_lock_of_another_host_is_stale_only_after_the_age(soft, monkeypatch):
    with open(soft, 'w') as f:
        f.write(f'12345 some-other-host {time.time():.3f}\n')
    with pytest.raises(TimeoutError):
        files.PathLock(soft).acquire(timeout=0.3)
    assert os.path.isfile(soft)

    old = time.time() - 2 * files.LOCK_SOFT_STALE_SECONDS
    os.utime(soft, (old, old))
    lock = files.PathLock(soft).acquire(timeout=5)
    assert lock.mode == 'soft'
    lock.release()
    assert not os.path.exists(soft)


def test_soft_lock_is_used_where_the_os_lock_is_refused(tmp_path, monkeypatch, caplog):
    lock_file = str(tmp_path / 'refused.lock')
    err = OSError(files.errno.ENOLCK, 'No locks available')

    def refuse(*args, **kwargs):
        raise err

    if POSIX:
        monkeypatch.setattr(files.fcntl, 'flock', refuse)
        monkeypatch.setattr(files.fcntl, 'lockf', refuse)
    else:
        monkeypatch.setattr(files.msvcrt, 'locking', refuse)
    monkeypatch.setattr(files, '_lock_soft_paths', set())
    monkeypatch.setattr(files, '_lock_no_flock_dirs', set())
    caplog.set_level('WARNING', logger='cmeta.utils.files')

    lock = files.PathLock(lock_file).acquire(timeout=5)
    assert lock.mode == 'soft'
    assert lock_file in files._lock_soft_paths
    assert any('soft lock' in rec.getMessage() for rec in caplog.records)
    lock.release()
    assert not os.path.exists(lock_file)

    again = files.PathLock(lock_file).acquire(timeout=5)   # remembered: soft at once
    assert again.mode == 'soft'
    again.release()


@pytest.mark.skipif(not POSIX, reason='POSIX record locks are the POSIX fallback')
def test_posix_record_locks_are_used_where_flock_is_refused(tmp_path, monkeypatch):
    lock_file = str(tmp_path / 'nfs-like.lock')

    def refuse(*args, **kwargs):
        raise OSError(files.errno.ENOLCK, 'No locks available')

    monkeypatch.setattr(files.fcntl, 'flock', refuse)
    monkeypatch.setattr(files, '_lock_no_flock_dirs', set())
    lock = files.PathLock(lock_file).acquire(timeout=5)
    assert lock.mode == 'lockf'
    assert os.path.dirname(lock_file) in files._lock_no_flock_dirs
    lock.release()
    assert not os.path.exists(lock_file)


##########################################################################################
# The engine's functions

def test_safe_delete_directory_takes_and_removes_its_lock(tmp_path):
    folder = tmp_path / 'artifact'
    folder.mkdir()
    (folder / 'f.txt').write_text('x')
    r = files.safe_delete_directory(str(folder))
    assert r['return'] == 0
    assert not folder.exists()
    assert not os.path.exists(str(folder) + '.lock')


def test_safe_write_file_releases_the_lock_it_took(tmp_path):
    target = str(tmp_path / 'data.json')
    r = files.safe_write_file(target, {'a': 1}, atomic=True)
    assert r['return'] == 0
    assert not os.path.exists(target + '.lock') and not os.path.exists(target + '.tmp')
    r = files.safe_read_file(target, lock=True)
    assert r['return'] == 0 and r['data'] == {'a': 1}
    assert not os.path.exists(target + '.lock')
