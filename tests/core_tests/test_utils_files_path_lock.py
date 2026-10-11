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

STALE_RACE_WORKER = r'''
import logging, os, random, subprocess, sys, time
from cmeta.utils import files
logging.disable(logging.CRITICAL)
folder, rounds, crash = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
lock_file, marker = os.path.join(folder, 'x.lock'), os.path.join(folder, 'in-the-lock')
files._lock_soft_paths.add(lock_file)
files.LOCK_SOFT_CHECK_SECONDS = 0.0     # every failed attempt judges the file: the waiters meet as often as they can
gone = 2147483644                       # no process has this pid (a pid that was used could be given to a new process meanwhile)
if files._lock_pid_alive(gone):
    child = subprocess.Popen([sys.executable, '-c', 'pass'], stdin=subprocess.DEVNULL)
    child.wait()
    gone = child.pid
rnd = random.Random(os.getpid())
together = 0
for i in range(rounds):
    lock = files.PathLock(lock_file).acquire(timeout=120)
    try:
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        together += 1                   # another process is inside the lock
    except OSError:
        pass                            # Windows: the marker of the previous holder is still being removed
    else:
        os.close(fd)
        time.sleep(0.0003)
        try:
            os.unlink(marker)
        except OSError:
            pass
    if rnd.randrange(crash) == 0:
        # the crash of a holder: its file stays, with the line of a process that is gone; it beats no more and
        # has no file open any more
        lock._stop_heartbeat()
        with open(lock_file, 'w') as f:
            f.write('%d %s %.3f %s\n' % (gone, files._lock_host_name(), time.time() - 5, files._lock_system_id()))
        os.close(lock._fd)
        lock._fd = None
        lock._remove_soft_file = lambda: None
    lock.release()
print('OK together', together)
'''

SOFT_ASKED = r'''
import os, sys
from cmeta.utils import files
asked, other = sys.argv[1], sys.argv[2]
a = files.PathLock(os.path.join(asked, 'a.lock')).acquire(timeout=5)
b = files.PathLock(os.path.join(other, 'b.lock')).acquire(timeout=5)
print(a.mode, b.mode, files._lock_system_id())
a.release()
b.release()
'''

SOFT_HOLDER = r'''
import sys, time
from cmeta.utils import files
files._lock_soft_paths.add(sys.argv[1])
lock = files.PathLock(sys.argv[1]).acquire(timeout=60)
print('LOCKED', lock.mode, flush=True)
sys.stdin.readline()                    # holds the lock until told to release it (or killed)
lock.release()
print('RELEASED', flush=True)
time.sleep(float(sys.argv[2]))
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
        pid, host, when, system = f.read().split()
    assert int(pid) == os.getpid() and host == files._lock_host_name() and system == files._lock_system_id()
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

    # Fresh, the file of a dead pid is a release in flight: waited for - whatever time the drive gave the file
    # (an hour old here: a drive whose clock is behind this machine's)
    hour_ago = time.time() - 3600
    os.utime(soft, (hour_ago, hour_ago))
    with pytest.raises(TimeoutError):
        files.PathLock(soft).acquire(timeout=0.3)
    assert os.path.isfile(soft)

    # Taken long enough ago - by the time its holder wrote into it - it is the leftover of a crash: one try
    # takes the lock (the probe of a cache entry is such a try), whatever time the drive gave the file
    with open(soft, 'w') as f:
        f.write(f'{gone.pid} {files._lock_host_name()} {time.time() - 2 * files.LOCK_SOFT_DEAD_MIN_AGE_SECONDS:.3f}\n')
    hour_ahead = time.time() + 3600
    os.utime(soft, (hour_ahead, hour_ahead))
    lock = files.PathLock(soft).acquire(timeout=0)
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
    old = time.time() - 3600
    os.utime(soft, (old, old))                  # the drive's time for the file says nothing
    with pytest.raises(TimeoutError):
        files.PathLock(soft).acquire(timeout=0.3)
    with open(soft, 'w') as f:
        f.write(f'{os.getpid()} {files._lock_host_name()} {time.time() - 2 * files.LOCK_SOFT_DEAD_MIN_AGE_SECONDS:.3f}\n')
    lock = files.PathLock(soft).acquire(timeout=5)
    assert lock.mode == 'soft'
    lock.release()
    assert not os.path.exists(soft)

    # An empty lock file is a leftover of an OS-lock attempt (a soft holder writes its line at once). A waiter
    # dates it by its own watch: seen empty for less than the time, it is waited for - a drive five minutes
    # behind this machine changes nothing; seen empty for longer, it is taken over
    five_minutes = time.time() - 300
    open(soft, 'w').close()
    os.utime(soft, (five_minutes, five_minutes))
    monkeypatch.setattr(files, 'LOCK_SOFT_EMPTY_STALE_SECONDS', 30.0)
    with pytest.raises(TimeoutError):
        files.PathLock(soft).acquire(timeout=0.6)
    assert os.path.isfile(soft)
    monkeypatch.setattr(files, 'LOCK_SOFT_EMPTY_STALE_SECONDS', 0.4)
    started = time.monotonic()
    lock = files.PathLock(soft).acquire(timeout=5)
    assert lock.mode == 'soft' and 0.4 <= time.monotonic() - started < 3
    lock.release()
    assert not os.path.exists(soft)
    # a single try has not watched the file: it leaves it ...
    open(soft, 'w').close()
    monkeypatch.setattr(files, 'LOCK_SOFT_EMPTY_STALE_SECONDS', 0.0)
    with pytest.raises(TimeoutError):
        files.PathLock(soft).acquire(timeout=0)
    assert os.path.isfile(soft)
    # ... unless the drive dates it beyond any difference of clocks (the limit of a lock left by another host)
    os.utime(soft, (old, old))
    lock = files.PathLock(soft).acquire(timeout=0)
    assert lock.mode == 'soft'
    lock.release()
    assert not os.path.exists(soft)


def test_a_soft_lock_of_another_host_is_stale_only_after_the_age(soft, monkeypatch):
    with open(soft, 'w') as f:
        f.write(f'12345 some-other-host {time.time():.3f}\n')
    old = time.time() - 2 * files.LOCK_SOFT_STALE_SECONDS
    os.utime(soft, (old, old))                  # a drive twenty minutes behind: the lock was taken a moment ago
    with pytest.raises(TimeoutError):
        files.PathLock(soft).acquire(timeout=0.3)
    assert os.path.isfile(soft)

    # Taken longer ago than the limit, by the time its holder wrote into it
    with open(soft, 'w') as f:
        f.write(f'12345 some-other-host {old:.3f}\n')
    ahead = time.time() + 3600
    os.utime(soft, (ahead, ahead))              # ... and a drive an hour ahead changes nothing
    lock = files.PathLock(soft).acquire(timeout=5)
    assert lock.mode == 'soft'
    lock.release()
    assert not os.path.exists(soft)

    # A holder whose clock is ahead of this machine's (its time lies in our future) is not stale for it
    with open(soft, 'w') as f:
        f.write(f'12345 some-other-host {time.time() + 3600:.3f}\n')
    with pytest.raises(TimeoutError):
        files.PathLock(soft).acquire(timeout=0.3)
    os.unlink(soft)


def test_a_soft_lock_line_without_a_time_is_dated_by_its_file(soft):
    # A lock file that this code did not write (no time in its line, a time that is no number, digits that are
    # no number): the time of the file is all there is, and no content makes the lock fail
    for content in ('12345 some-other-host\n', '12345 some-other-host nan\n', '²³ x y\n', 'pid 1 reindexes\n'):
        with open(soft, 'w', encoding='utf-8') as f:
            f.write(content)
        with pytest.raises(TimeoutError):
            files.PathLock(soft).acquire(timeout=0.3)
        old = time.time() - 2 * files.LOCK_SOFT_STALE_SECONDS
        os.utime(soft, (old, old))
        lock = files.PathLock(soft).acquire(timeout=5)
        assert lock.mode == 'soft'
        lock.release()
        assert not os.path.exists(soft)


def stale_line(seconds_ago=5.0, system=True):
    """The line of a soft lock whose holder is gone: a pid that no process has, on this system, taken a while
    ago (`system=False`: the line of a holder of cMeta before 0.35.0, without the system)."""
    gone = 2147483644
    if files._lock_pid_alive(gone):
        child = subprocess.Popen([sys.executable, '-c', 'pass'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        child.wait()
        gone = child.pid
    tail = f' {files._lock_system_id()}' if system else ''
    return f'{gone} {files._lock_host_name()} {time.time() - seconds_ago:.3f}{tail}\n'


def test_a_stale_soft_lock_is_replaced_in_one_step_and_never_moved_from_the_path(soft, monkeypatch):
    """The waiter replaces the stale file by its own in one rename: the path is never free in between, and no
    file is renamed AWAY from the path (the previous way - away, checked, put back when it was not the judged
    one - left the path free for a third process meanwhile)."""
    moves = []
    real_rename, real_replace = os.rename, os.replace

    def rename(src, dst, *args, **kwargs):
        moves.append((src, dst))
        return real_rename(src, dst, *args, **kwargs)

    def replace(src, dst, *args, **kwargs):
        moves.append((src, dst))
        return real_replace(src, dst, *args, **kwargs)
    monkeypatch.setattr(os, 'rename', rename)
    monkeypatch.setattr(os, 'replace', replace)

    with open(soft, 'w') as f:
        f.write(stale_line())
    lock = files.PathLock(soft).acquire(timeout=0)
    assert lock.mode == 'soft'
    assert len(moves) == 1 and moves[0][0].startswith(soft + '.take-') and moves[0][1] == soft
    assert os.listdir(os.path.dirname(soft)) == [os.path.basename(soft)]
    with open(soft) as f:
        assert int(f.read().split()[0]) == os.getpid()
    lock.release()
    assert os.listdir(os.path.dirname(soft)) == []


def test_a_waiter_a_step_behind_leaves_the_file_of_the_one_that_took_the_stale_lock(soft, monkeypatch):
    """Two waiters judge the same stale file and one takes the lock over. The other, a step behind, finds that
    the file at the path is not the one it judged, and leaves it where it is."""
    with open(soft, 'w') as f:
        f.write(stale_line())
    # the line of the other waiter: a live process (this one), taken half a second ago - never the very line the
    # waiter under test writes in the same millisecond (a line tells its writer by pid, host and time)
    fresh = f'{os.getpid()} {files._lock_host_name()} {time.time() - 0.5:.3f}\n'
    real = files.PathLock._soft_file_is_stale
    seen = {}

    def judged_then_overtaken(self, path, read):
        stale = real(self, path, read)
        if stale and path == soft and not seen:
            with open(soft + '.other', 'w') as f:       # the other waiter's take-over, right after the judgement
                f.write(fresh)
            os.replace(soft + '.other', soft)
            seen['ino'] = os.stat(soft).st_ino
        return stale
    monkeypatch.setattr(files.PathLock, '_soft_file_is_stale', judged_then_overtaken)

    with pytest.raises(TimeoutError):
        files.PathLock(soft).acquire(timeout=0)
    assert seen and os.stat(soft).st_ino == seen['ino']
    with open(soft) as f:
        assert f.read() == fresh
    assert os.listdir(os.path.dirname(soft)) == [os.path.basename(soft)]
    os.unlink(soft)


def test_one_waiter_at_a_time_takes_a_stale_soft_lock_over(soft):
    """The file that replaces a stale lock file is made exclusively, under a name of that stale file: a second
    waiter finds it and waits. The take file of a waiter that died meanwhile is a leftover, and goes."""
    stale = stale_line()
    with open(soft, 'w') as f:
        f.write(stale)
    probe = files.PathLock(soft)
    take = probe._take_file(probe._read_lock_file(soft))
    assert take.startswith(soft + '.take-')
    with open(take, 'w') as f:                  # another waiter (alive: this process) is taking it over right now
        f.write(f'{os.getpid()} {files._lock_host_name()} {time.time():.3f}\n')
    with pytest.raises(TimeoutError):
        files.PathLock(soft).acquire(timeout=0.6)
    with open(soft) as f:
        assert f.read() == stale
    assert os.path.isfile(take)

    with open(take, 'w') as f:                  # that waiter died before it replaced the file
        f.write(stale_line())
    lock = files.PathLock(soft).acquire(timeout=5)
    assert lock.mode == 'soft'
    assert os.listdir(os.path.dirname(soft)) == [os.path.basename(soft)]
    lock.release()
    assert os.listdir(os.path.dirname(soft)) == []


def test_a_soft_lock_taken_over_is_not_removed_by_its_former_holder(soft):
    lock = files.PathLock(soft).acquire(timeout=5)
    theirs = f'12345 some-other-host {time.time():.3f}\n'
    with open(soft + '.new', 'w') as f:
        f.write(theirs)
    if POSIX:
        os.replace(soft + '.new', soft)         # this holder was judged gone (it was not) and its lock taken over
        lock.release()
        with open(soft) as f:
            assert f.read() == theirs
        os.unlink(soft)
    else:
        # Windows: a holder keeps its lock file open, and an open file cannot be replaced - the lock of a holder
        # that is alive cannot be taken over at all
        with pytest.raises(PermissionError):
            os.replace(soft + '.new', soft)
        os.unlink(soft + '.new')
        lock.release()
        assert not os.path.exists(soft)


def test_a_live_soft_holder_judged_gone_by_mistake(tmp_path, monkeypatch):
    """A waiter that takes a live holder for a dead one (it cannot see its pid: another system on a shared
    folder). On Windows it cannot take the lock over - the holder has its file open - and nothing is left behind;
    elsewhere it can, and the former holder then leaves the lock of the other alone when it releases."""
    lock_file = str(tmp_path / 'live.lock')
    holder = subprocess.Popen([sys.executable, '-c', SOFT_HOLDER, lock_file, '60'],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    line = holder.stdout.readline().decode('utf-8', 'replace')
    assert line.startswith('LOCKED soft'), line
    try:
        monkeypatch.setattr(files, '_lock_soft_paths', {lock_file})
        monkeypatch.setattr(files, '_lock_pid_alive', lambda pid: False)
        monkeypatch.setattr(files, 'LOCK_SOFT_DEAD_MIN_AGE_SECONDS', 0.0)
        if POSIX:
            lock = files.PathLock(lock_file).acquire(timeout=5)
            with open(lock_file) as f:
                assert int(f.read().split()[0]) == os.getpid()
            holder.stdin.write(b'release\n')
            holder.stdin.flush()
            assert holder.stdout.readline().decode('utf-8', 'replace').startswith('RELEASED')
            with open(lock_file) as f:                              # the former holder left it alone
                assert int(f.read().split()[0]) == os.getpid()
            lock.release()
        else:
            with pytest.raises(TimeoutError):
                files.PathLock(lock_file).acquire(timeout=1)
            with open(lock_file) as f:
                assert int(f.read().split()[0]) == holder.pid
            assert os.listdir(str(tmp_path)) == [os.path.basename(lock_file)]
            holder.stdin.write(b'release\n')
            holder.stdin.flush()
            assert holder.stdout.readline().decode('utf-8', 'replace').startswith('RELEASED')
        assert os.listdir(str(tmp_path)) == []
    finally:
        holder.kill()
        holder.wait(30)


@pytest.mark.skipif(not POSIX, reason='on Windows a file cannot be replaced while its maker has it open')
def test_a_soft_lock_file_taken_over_while_it_is_made_is_not_held(soft, monkeypatch):
    """A process stopped between creating its soft lock file and writing into it finds, when it goes on, that a
    waiter has taken the empty file over: it does not hold the lock, and leaves the file of the other."""
    theirs = f'12345 some-other-host {time.time():.3f}\n'
    real_write = os.write
    state = {'n': 0}

    def write_after_a_take_over(fd, data):
        state['n'] += 1
        if state['n'] == 1:
            with open(soft + '.new', 'w') as f:
                f.write(theirs)
            os.replace(soft + '.new', soft)
        return real_write(fd, data)
    monkeypatch.setattr(os, 'write', write_after_a_take_over)

    with pytest.raises(TimeoutError):
        files.PathLock(soft).acquire(timeout=0.3)
    monkeypatch.setattr(os, 'write', real_write)
    with open(soft) as f:
        assert f.read() == theirs
    os.unlink(soft)


def test_a_soft_lock_file_that_the_file_system_shows_late_is_still_this_lock(soft, monkeypatch):
    """A file system that does not show a new file at once: the holder cannot confirm its lock file in its first
    attempt. The file with its line, found at the path in the next attempt, is its lock - and when the acquire
    gives up before that (a single try), the file goes, or it would keep everybody out while the process lives."""
    real = files.PathLock._open_if_mine
    state = {'n': 0}

    def not_there_at_first(self, line):
        state['n'] += 1
        return ('gone', None) if state['n'] <= 3 else real(self, line)   # the three looks of the first attempt
    monkeypatch.setattr(files.PathLock, '_open_if_mine', not_there_at_first)
    monkeypatch.setattr(files.PathLock, '_identity', staticmethod(lambda st: None))   # ... and it reports no inode numbers

    lock = files.PathLock(soft).acquire(timeout=5)
    assert lock.mode == 'soft' and state['n'] > 3
    with open(soft) as f:
        assert int(f.read().split()[0]) == os.getpid()
    lock.release()
    assert not os.path.exists(soft)

    state['n'] = 0
    with pytest.raises(TimeoutError):
        files.PathLock(soft).acquire(timeout=0)
    assert state['n'] == 3 and not os.path.exists(soft)
    lock = files.PathLock(soft).acquire(timeout=0)              # ... and the lock is free for the next one
    lock.release()
    assert os.listdir(os.path.dirname(soft)) == []


def test_waiters_on_the_soft_lock_of_crashed_holders_never_hold_it_together(tmp_path):
    """Six processes take one soft lock sixty times each, and one holder in four "crashes" (its lock file stays,
    with the line of a process that is gone): the waiters judge and take over stale files side by side, and
    never two of them are inside the lock at once. No take file is left."""
    folder = tmp_path / 'race'
    folder.mkdir()
    outputs = run_workers(STALE_RACE_WORKER, [(str(folder), 60, 4)] * 6)
    for rc, out in outputs:
        assert rc == 0 and out.strip().endswith('OK together 0'), out
    assert os.listdir(str(folder)) in ([], ['x.lock'])      # the last crash may have left its lock file


def test_the_lock_file_goes_where_a_file_gets_its_identity_at_the_first_write(tmp_path, monkeypatch):
    """exFAT on macOS: an empty file reports a placeholder inode that becomes a real one at the first write. The
    lock noted the identity of its (empty) file when it took it, the note changed it, and at release "the file
    at the path is not ours" left the lock file behind after every noted lock."""
    real = files.PathLock._identity

    def placeholder_until_written(st):
        ident = real(st)
        if ident is None:
            return None
        return (2 ** 64 - 1, ident[1]) if st.st_size == 0 else ident
    monkeypatch.setattr(files.PathLock, '_identity', staticmethod(placeholder_until_written))

    lock_file = str(tmp_path / 'noted.lock')
    lock = files.PathLock(lock_file).acquire(timeout=5, note='pid 1 reindexes')
    assert lock.mode != 'soft' and files.PathLock.read_note(lock_file) == 'pid 1 reindexes'
    lock.release()
    assert not os.path.exists(lock_file)

    lock = files.PathLock(lock_file).acquire(timeout=5)         # without a note the file stays empty
    lock.release()
    assert not os.path.exists(lock_file)


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

    started = time.monotonic()
    lock = files.PathLock(lock_file).acquire(timeout=5)
    assert lock.mode == 'soft'
    # the empty file the refused attempt left is taken over at once, not watched like an empty file of unknown origin
    assert time.monotonic() - started < files.LOCK_SOFT_EMPTY_STALE_SECONDS / 2
    assert lock_file in files._lock_soft_paths
    assert any('soft lock' in rec.getMessage() for rec in caplog.records)
    assert os.listdir(str(tmp_path)) == [os.path.basename(lock_file)]
    lock.release()
    assert not os.path.exists(lock_file)

    again = files.PathLock(lock_file).acquire(timeout=5)   # remembered: soft at once
    assert again.mode == 'soft'
    again.release()
    assert os.listdir(str(tmp_path)) == []


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
# The heartbeat of a soft holder, the system named in its line, and the soft lock asked for

def test_a_soft_lock_line_names_the_system_and_the_heartbeat_rewrites_its_time(soft, monkeypatch):
    monkeypatch.setattr(files, 'LOCK_SOFT_HEARTBEAT_SECONDS', 0.05)
    lock = files.PathLock(soft).acquire(timeout=5)
    with open(soft) as f:
        first = f.read()
    words = first.split()
    assert len(words) == 4 and int(words[0]) == os.getpid() and words[1] == files._lock_host_name()
    assert words[3] == files._lock_system_id() and len(words[3]) == 12
    assert id(lock) in files._beat_held and files._beat_thread.is_alive()

    deadline = time.monotonic() + 5
    data = first
    while data == first and time.monotonic() < deadline:
        time.sleep(0.02)
        with open(soft) as f:
            data = f.read()
    beat = data.split()
    assert float(beat[2]) > float(words[2]) and beat[0] == words[0] and beat[1] == words[1] and beat[3] == words[3]
    assert len(data) == len(first) and data.endswith('\n')          # rewritten in place: the same length, never empty
    assert lock._line != first.encode()                              # the holder knows the line it wrote last

    # the processes of one system agree on its name
    out = subprocess.run([sys.executable, '-c', 'from cmeta.utils import files; print(files._lock_system_id())'],
                         stdin=subprocess.DEVNULL, capture_output=True)
    assert out.stdout.decode('utf-8', 'replace').split() == [files._lock_system_id()]

    lock.release()
    assert id(lock) not in files._beat_held            # the one thread of the process beats on for the other soft locks
    assert not os.path.exists(soft)


def test_a_silent_holder_of_another_system_is_taken_over_after_the_silence_and_a_beating_one_never(soft, monkeypatch):
    monkeypatch.setattr(files, 'LOCK_SOFT_SILENT_SECONDS', 0.6)
    monkeypatch.setattr(files, '_lock_pid_alive', lambda pid: False)   # that pid is dead HERE - but it is a pid of another system
    foreign = 'ffffffffffff'
    with open(soft, 'w') as f:                  # taken a moment ago, by its own time: no age rule can take it
        f.write(f'12345 some-other-host {time.time():.3f} {foreign}\n')
    with pytest.raises(TimeoutError):
        files.PathLock(soft).acquire(timeout=0.3)
    started = time.monotonic()
    lock = files.PathLock(soft).acquire(timeout=5)
    assert lock.mode == 'soft' and 0.6 <= time.monotonic() - started < 4
    lock.release()
    assert not os.path.exists(soft)

    # A holder that beats is never taken over - whatever its clock reads (an hour behind here: the time in its
    # line is not compared with this machine's clock)
    stop = threading.Event()

    def beat():
        n = 0
        while not stop.wait(0.1):
            n += 1
            with open(soft, 'r+') as f:
                f.write(f'12345 some-other-host {time.time() - 3600 + n / 1000:.3f} {foreign}\n')
    with open(soft, 'w') as f:
        f.write(f'12345 some-other-host {time.time() - 3600:.3f} {foreign}\n')
    beater = threading.Thread(target=beat, daemon=True)
    beater.start()
    try:
        with pytest.raises(TimeoutError):
            files.PathLock(soft).acquire(timeout=1.5)
    finally:
        stop.set()
        beater.join(5)
    os.unlink(soft)


def test_a_dead_holder_of_this_system_is_known_by_its_pid_before_the_silence(soft, monkeypatch):
    monkeypatch.setattr(files, 'LOCK_SOFT_SILENT_SECONDS', 3600.0)
    with open(soft, 'w') as f:
        f.write(stale_line())                   # four words: a pid of this system that is gone, taken 5 s ago
    lock = files.PathLock(soft).acquire(timeout=0)
    assert lock.mode == 'soft'
    lock.release()

    # ... while a pid of this system that is alive keeps its lock, silent or not
    with open(soft, 'w') as f:
        f.write(f'{os.getpid()} {files._lock_host_name()} {time.time() - 5:.3f} {files._lock_system_id()}\n')
    with pytest.raises(TimeoutError):
        files.PathLock(soft).acquire(timeout=0.3)

    # ... and the same pid of ANOTHER system is not checked here: that holder is judged by its silence alone
    monkeypatch.setattr(files, 'LOCK_SOFT_SILENT_SECONDS', 0.4)
    with open(soft, 'w') as f:
        f.write(f'{os.getpid()} {files._lock_host_name()} {time.time() - 5:.3f} ffffffffffff\n')
    started = time.monotonic()
    lock = files.PathLock(soft).acquire(timeout=5)
    assert lock.mode == 'soft' and 0.4 <= time.monotonic() - started < 4
    lock.release()
    assert not os.path.exists(soft)


@pytest.mark.skipif(not hasattr(os, 'fork'), reason='fork is a POSIX matter')
def test_a_forked_child_never_releases_the_lock_of_its_parent(tmp_path, monkeypatch):
    import warnings
    soft_file, own = str(tmp_path / 'soft.lock'), str(tmp_path / 'own.lock')
    monkeypatch.setattr(files, '_lock_soft_paths', {soft_file, own})
    for lock_file in (str(tmp_path / 'os.lock'), soft_file):
        lock = files.PathLock(lock_file).acquire(timeout=5)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', DeprecationWarning)     # the heartbeat thread of the soft holder is running
            pid = os.fork()
        if pid == 0:                            # the child: a copy of the holder that is not the holder
            try:
                lock.release()
                code = 0 if os.path.exists(lock_file) and not lock.is_locked else 1
                # ... and a process of its own: the parent's lock is held by another process for it, and it
                # takes and beats soft locks of its own (the module's thread locks were made anew for it)
                try:
                    files.PathLock(lock_file).acquire(timeout=0.3)
                    code = 3
                except TimeoutError as e:
                    if 'another process' not in str(e):
                        code = 4
                mine = files.PathLock(own).acquire(timeout=5)
                if not mine.is_locked or id(mine) not in files._beat_held or files._beat_thread is None:
                    code = 5
                mine.release()
                if os.path.exists(own):
                    code = 6
            except BaseException:
                code = 2
            os._exit(code)
        _, status = os.waitpid(pid, 0)
        assert os.WEXITSTATUS(status) == 0, lock_file
        assert lock.is_locked and os.path.exists(lock_file)
        with pytest.raises(TimeoutError):       # still held
            files.PathLock(lock_file).acquire(timeout=0.2)
        lock.release()
        assert not os.path.exists(lock_file)


def test_the_soft_lock_is_used_under_the_folders_the_environment_names(tmp_path):
    asked, other = tmp_path / 'shared', tmp_path / 'own'
    asked.mkdir()
    other.mkdir()

    def modes(value):
        env = dict(os.environ)
        env['PYTHONIOENCODING'] = 'utf-8'
        env.pop('CMETA_SOFT_LOCK_PATHS', None)
        if value is not None:
            env['CMETA_SOFT_LOCK_PATHS'] = value
        out = subprocess.run([sys.executable, '-c', SOFT_ASKED, str(asked), str(other)], env=env,
                             stdin=subprocess.DEVNULL, capture_output=True)
        assert out.returncode == 0, out.stderr.decode('utf-8', 'replace')
        a, b, system = out.stdout.decode('utf-8', 'replace').split()
        assert system == files._lock_system_id()
        return a, b

    os_mode = 'windows' if not POSIX else 'flock'
    assert modes(None) == (os_mode, os_mode)
    assert modes(str(asked)) == ('soft', os_mode)
    assert modes(os.pathsep.join([str(other), str(asked)])) == ('soft', 'soft')
    assert modes('*') == ('soft', 'soft')
    assert sorted(os.listdir(str(asked))) == [] and sorted(os.listdir(str(other))) == []


def test_use_soft_lock_under_a_folder_and_not_next_to_it(tmp_path, monkeypatch):
    monkeypatch.setattr(files, '_lock_soft_dirs', [])
    folder = tmp_path / 'repo'
    (folder / 'sub').mkdir(parents=True)
    (tmp_path / 'repo2').mkdir()
    assert files.use_soft_lock_under(str(folder)) == {'return': 0}
    files.use_soft_lock_under(str(folder))          # once is enough
    assert len(files._lock_soft_dirs) == 1

    inside = files.PathLock(str(folder / 'sub' / 'x.lock')).acquire(timeout=5)
    beside = files.PathLock(str(tmp_path / 'repo2' / 'x.lock')).acquire(timeout=5)   # the same letters, another folder
    outside = files.PathLock(str(tmp_path / 'x.lock')).acquire(timeout=5)
    assert inside.mode == 'soft' and beside.mode != 'soft' and outside.mode != 'soft'
    for lock in (inside, beside, outside):
        lock.release()
    assert not any(name.endswith('.lock') for root, dirs, names in os.walk(str(tmp_path)) for name in names)


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
