"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

The engine without psutil (2026-11-09): utils.sys.pid_exists and the host's cores and memory from the standard library
(ctypes on Windows), by psutil's own rules - psutil had no wheel for the free-threaded Python 3.15t, so cMeta did not
install there without a compiler. What is checked, on every platform the suite runs on:

- pid_exists says True for this process, a live child (which is STILL ALIVE after the check: os.kill(pid, 0) on
  Windows would have ended it), a process we may not look at (init / launchd, Windows' System), a zombie (as psutil);
  False for an exited child (also while a handle keeps its process object), a pid no process has, a negative or
  impossible one, a value that is not a pid, and on Linux a thread's id (psutil issue 687);
- PID 0 as psutil answers it: Windows (the System Idle Process) and macOS (kernel_task) True, Linux False;
- where psutil is importable, both agree on every pid of the process table and on random ones (a disagreement is
  looked at twice: a process may end between two calls);
- the soft lock's check of a holder's pid (_lock_pid_alive) uses it and answers "alive" when it cannot tell;
- the host's numbers: total and available memory, logical and physical cores, this process's memory - plausible on
  their own (the process's memory grows when the process allocates), equal to psutil's where it is importable
  (exactly for the total memory and the cores, within a tolerance for what moves), never "unknown" on Windows,
  Linux and macOS;
- no module of the engine imports psutil; pid_exists is fast enough for a waiter that asks every quarter second.
"""

import os
import random
import re
import subprocess
import sys
import threading
import time

import pytest

from cmeta.utils import files
from cmeta.utils import sys as cmeta_sys

try:
    import psutil
except ImportError:                       # the point of the change: the engine runs without it
    psutil = None

WIN = os.name == 'nt'
LINUX = sys.platform.startswith('linux')
MAC = sys.platform == 'darwin'
GONE = 2147483644                         # a pid no process has (above any pid_max; not a multiple of 4 on Windows)


def child(code='import time; time.sleep(60)'):
    return subprocess.Popen([sys.executable, '-c', code], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True)


def end(p):
    if p.poll() is None:
        p.kill()
    p.wait(30)


def test_this_process_and_a_live_child_exist_and_the_child_survives_the_check():
    assert cmeta_sys.pid_exists(os.getpid()) is True
    assert cmeta_sys.pid_exists(str(os.getpid())) is True           # a pid read from a lock file's line
    p = child()
    try:
        for _ in range(50):                                          # fifty checks: none of them ends the child
            assert cmeta_sys.pid_exists(p.pid) is True
        time.sleep(0.3)
        assert p.poll() is None, 'the check ended the child (os.kill(pid, 0) on Windows would)'
    finally:
        end(p)


def test_an_exited_child_is_gone_even_while_a_handle_keeps_its_process_object():
    p = child('pass')
    p.wait(30)
    time.sleep(0.2)
    # the Popen object still holds the process handle on Windows (the pid stays reserved for it): the process has
    # ended all the same - what psutil answers too
    assert cmeta_sys.pid_exists(p.pid) is False
    pid = p.pid
    del p
    assert cmeta_sys.pid_exists(pid) is False


def test_a_pid_that_no_process_has_and_values_that_are_not_pids():
    assert cmeta_sys.pid_exists(GONE) is False
    # 3.5 is not the pid 3 (a kernel thread on Linux, found by the VMs of the matrix), True is not the pid 1, ' 7 ' is
    # not read as 7... a pid is an int or the digits of a line
    for bad in (-1, -GONE, 2 ** 40, 2 ** 63, 'abc', None, '', 3.5, 1.0, float(os.getpid()), True, False, '12x', '-1', ' 7 ', '٣', [os.getpid()]):
        assert cmeta_sys.pid_exists(bad) is False, bad
    if WIN:
        assert cmeta_sys.pid_exists(GONE - 1) is False                # a pid is a multiple of 4 on Windows: never one
        assert cmeta_sys.pid_exists(0xFFFFFFFF + 4) is False


def test_pid_zero_as_psutil_answers_it():
    expected = not LINUX                                             # Windows: the System Idle Process; macOS: kernel_task
    assert cmeta_sys.pid_exists(0) is expected
    if psutil is not None:
        assert psutil.pid_exists(0) is expected


def test_a_process_we_may_not_look_at_exists():
    # init / launchd (kill(1, 0) is EPERM for a user, allowed for root), Windows' System process (OpenProcess: access
    # denied) - a process that exists, whatever the answer to our look
    pid = 4 if WIN else 1
    assert cmeta_sys.pid_exists(pid) is True
    if psutil is not None:
        assert psutil.pid_exists(pid) is True


@pytest.mark.skipif(WIN, reason='no zombies on Windows')
def test_a_zombie_exists_until_it_is_reaped():
    p = child('pass')
    for _ in range(100):                                             # the child exits; its parent (we) has not waited yet
        time.sleep(0.05)
        if LINUX:
            try:
                with open('/proc/%d/status' % p.pid) as f:
                    if 'State:\tZ' in f.read():
                        break
            except OSError:
                pass
        else:
            try:
                out = subprocess.run(['/bin/ps', '-o', 'stat=', '-p', str(p.pid)], capture_output=True, text=True).stdout
                if out.strip().startswith('Z'):
                    break
            except OSError:
                break
    assert cmeta_sys.pid_exists(p.pid) is True                       # a zombie is a process (psutil: the same)
    if psutil is not None:
        assert psutil.pid_exists(p.pid) is True
    p.wait(30)
    assert cmeta_sys.pid_exists(p.pid) is False


@pytest.mark.skipif(not LINUX, reason='Linux gives threads ids of the same space as processes')
def test_a_thread_id_is_not_a_process_on_linux():
    p = child('import threading, time, sys\n'
              'e = threading.Event()\n'
              'def run():\n'
              '    print(threading.get_native_id(), flush=True); e.wait(60)\n'
              'threading.Thread(target=run).start(); e.wait(60)')
    try:
        tid = int(p.stdout.readline().strip())
        assert tid != p.pid
        assert os.path.isdir('/proc/%d' % tid)                       # the id leads somewhere: a thread of the child
        assert cmeta_sys.pid_exists(p.pid) is True
        assert cmeta_sys.pid_exists(tid) is False                    # psutil's rule (its issue 687)
        if psutil is not None:
            assert psutil.pid_exists(tid) is False
    finally:
        end(p)
    # a thread of ANOTHER user's process (kill says "not permitted" for it as for the process itself: the WSL
    # distribution of the matrix had rsyslogd's threads): not a process either
    others = []
    for name in os.listdir('/proc'):
        if not name.isdigit() or name == str(os.getpid()):
            continue
        try:
            if os.stat('/proc/' + name).st_uid == os.getuid():
                continue
            tids = [t for t in os.listdir('/proc/%s/task' % name) if t != name]
        except OSError:
            continue
        if tids:
            others.append((int(name), int(tids[0])))
            if len(others) >= 3:
                break
    for ppid, tid in others:
        assert cmeta_sys.pid_exists(ppid) is True, ppid
        assert cmeta_sys.pid_exists(tid) is False, (ppid, tid)
        if psutil is not None:
            assert psutil.pid_exists(tid) is False, (ppid, tid)


@pytest.mark.skipif(psutil is None, reason='psutil is not installed here: nothing to compare with (the engine runs without it)')
def test_the_same_answers_as_psutil_for_the_process_table_and_random_pids():
    pids = set(psutil.pids())
    high = max(pids) if pids else 65536
    rnd = random.Random(12345)
    sample = sorted(pids) + [rnd.randrange(0, high + 5000) for _ in range(400)] + [GONE, high + 4, 1, 2, 3, 4, 0]
    if WIN:
        # a Windows pid is a multiple of 4; for a number that is not one psutil 7.2.2 answers what OpenProcess says of
        # the process whose id has the same high bits (True for 37921 while 37920 runs: a process nobody has) - the
        # kernel ignores the two low bits. This code says False there (test below); the real pids are compared
        sample = [p for p in sample if p % 4 == 0]
    disagree = []
    for pid in sample:
        if cmeta_sys.pid_exists(pid) != psutil.pid_exists(pid):
            time.sleep(0.05)                                         # a process may have ended between the two looks
            a, b = cmeta_sys.pid_exists(pid), psutil.pid_exists(pid)
            if a != b:
                disagree.append((pid, a, b))
    assert not disagree, disagree


@pytest.mark.skipif(not WIN, reason='Windows pids are multiples of 4')
def test_a_number_that_names_a_live_process_by_its_high_bits_is_not_a_pid_on_windows():
    """The kernel ignores the two low bits of a process id: OpenProcess(37921) opens the process 37920. No process has
    the id 37921 (the process table never lists such a number) - not a pid, whatever OpenProcess opens."""
    p = child()
    try:
        assert cmeta_sys.pid_exists(p.pid) is True
        for alias in (p.pid + 1, p.pid + 2, p.pid + 3):
            assert cmeta_sys.pid_exists(alias) is False, alias
        if psutil is not None:
            assert all(x % 4 == 0 for x in psutil.pids())             # what the process table says: multiples of 4 only
    finally:
        end(p)


def test_the_soft_lock_asks_pid_exists_and_treats_the_unknown_as_alive(monkeypatch):
    assert files._lock_pid_alive(os.getpid()) is True
    assert files._lock_pid_alive(GONE) is False
    p = child('pass')
    p.wait(30)
    time.sleep(0.2)
    assert files._lock_pid_alive(p.pid) is False

    def boom(pid):
        raise OSError('the system does not say')
    monkeypatch.setattr(cmeta_sys, 'pid_exists', boom)
    assert files._lock_pid_alive(GONE) is True                       # unknown: never treated as dead


def test_a_stale_soft_lock_of_a_dead_pid_is_taken_over_for_real(tmp_path):
    """The whole chain on this system: a lock file left by a process that is gone (its line names a dead pid, this
    system, a time long enough ago) is taken over by a waiter within the dead-pid rule, not after the silence."""
    lock_file = str(tmp_path / 'x.lock')
    p = child('pass')
    p.wait(30)
    time.sleep(0.2)
    files._lock_soft_paths.add(lock_file)
    try:
        with open(lock_file, 'w', encoding='utf-8') as f:
            f.write('%d %s %.3f %s\n' % (p.pid, files._lock_host_name(), time.time() - 5, files._lock_system_id()))
        t0 = time.monotonic()
        lock = files.PathLock(lock_file).acquire(timeout=30)
        taken = time.monotonic() - t0
        try:
            assert lock.mode == 'soft'
            assert taken < files.LOCK_SOFT_SILENT_SECONDS / 2, taken  # by the pid, not by the silence
            with open(lock_file, encoding='utf-8') as f:
                assert f.read().split()[0] == str(os.getpid())
        finally:
            lock.release()
    finally:
        files._lock_soft_paths.discard(lock_file)


def test_a_live_holders_soft_lock_is_not_taken_by_its_pid(tmp_path):
    """A live process holds the lock (no heartbeat while it is checked: the lines does not change): the waiter must not
    take it by the pid - only the silence rule may, after LOCK_SOFT_SILENT_SECONDS, which the waiter here never
    reaches."""
    lock_file = str(tmp_path / 'x.lock')
    p = child()
    files._lock_soft_paths.add(lock_file)
    try:
        with open(lock_file, 'w', encoding='utf-8') as f:
            f.write('%d %s %.3f %s\n' % (p.pid, files._lock_host_name(), time.time() - 5, files._lock_system_id()))
        t0 = time.monotonic()
        with pytest.raises(Exception):
            files.PathLock(lock_file).acquire(timeout=3)
        assert time.monotonic() - t0 >= 2.5
        with open(lock_file, encoding='utf-8') as f:
            assert f.read().split()[0] == str(p.pid)                 # still the live holder's line
    finally:
        files._lock_soft_paths.discard(lock_file)
        end(p)


def test_pid_exists_is_fast_enough_for_a_waiter():
    pids = [os.getpid(), GONE, 1 if not WIN else 4]
    t0 = time.monotonic()
    for i in range(1500):
        cmeta_sys.pid_exists(pids[i % 3])
    secs = time.monotonic() - t0
    assert secs < 5.0, '1500 checks took %.2f s' % secs


def test_the_host_numbers_are_plausible_and_the_process_memory_grows():
    r = cmeta_sys.get_min_raw_host_info()
    assert r['return'] == 0
    total, avail, logical, physical, rss = (r[k] for k in ('total_memory', 'free_memory', 'logical_cores', 'physical_cores', 'memory_used'))
    assert isinstance(total, int) and total > 256 * 1024 * 1024, total
    assert isinstance(avail, int) and 0 <= avail <= total, (avail, total)
    assert logical == os.cpu_count() and logical >= 1
    assert physical is None or 1 <= physical <= logical, (physical, logical)
    if WIN or MAC or (LINUX and os.path.isdir('/sys/devices/system/cpu/cpu0/topology')):
        assert physical is not None                                  # these systems always say
    assert isinstance(rss, int) and rss > 4 * 1024 * 1024, rss
    block = bytearray(96 * 1024 * 1024)                              # allocated and touched: resident
    for i in range(0, len(block), 4096):
        block[i] = 1
    grown = cmeta_sys.get_min_raw_host_info()['memory_used']
    assert grown - rss > 48 * 1024 * 1024, (rss, grown)
    del block


@pytest.mark.skipif(psutil is None, reason='psutil is not installed here: nothing to compare with (the engine runs without it)')
def test_the_host_numbers_are_psutils():
    r = cmeta_sys.get_min_raw_host_info()
    vm = psutil.virtual_memory()
    assert r['total_memory'] == vm.total
    assert r['logical_cores'] == psutil.cpu_count(logical=True)
    assert r['physical_cores'] == psutil.cpu_count(logical=False)
    # what moves between two looks: the available memory (other processes), this process's own (the allocator)
    assert abs(r['free_memory'] - vm.available) <= max(vm.total // 10, 256 * 1024 * 1024), (r['free_memory'], vm.available)
    rss = psutil.Process().memory_info().rss
    assert abs(r['memory_used'] - rss) <= max(rss // 5, 32 * 1024 * 1024), (r['memory_used'], rss)


def test_the_formatted_info_names_every_number(capsys):
    r = cmeta_sys.get_min_host_info(con=True)
    out = capsys.readouterr().out
    assert r['return'] == 0
    for key in ('Host physical cores:', 'Host logical cores:', 'Host total memory:', 'Host free memory:', 'Memory used by current process:'):
        assert key in out, out
    if WIN or MAC or LINUX:
        assert 'unknown' not in out, out
    assert re.search(r'Host total memory: \d', out), out


def test_no_module_of_the_engine_imports_psutil():
    import cmeta
    root = os.path.dirname(os.path.abspath(cmeta.__file__))
    hits = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in ('__pycache__', 'node_modules')]
        for fn in fns:
            if fn.endswith('.py'):
                with open(os.path.join(dp, fn), encoding='utf-8', errors='replace') as f:
                    for n, line in enumerate(f, 1):
                        if re.match(r'\s*(import psutil|from psutil)', line):
                            hits.append('%s:%d' % (os.path.relpath(os.path.join(dp, fn), root), n))
    assert hits == [], hits


def test_pid_exists_from_several_threads_at_once():
    """A server's workers ask from threads: the ctypes calls and the /proc reads are independent."""
    p = child()
    bad = []

    def run():
        for _ in range(200):
            if cmeta_sys.pid_exists(p.pid) is not True or cmeta_sys.pid_exists(GONE) is not False:
                bad.append(1)
    try:
        threads = [threading.Thread(target=run) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
        assert not bad
        assert p.poll() is None
    finally:
        end(p)
