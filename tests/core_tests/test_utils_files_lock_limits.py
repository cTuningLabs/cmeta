"""
Tests of the limits of a lock wait: the values the engine takes for a timeout (CMETA_LOCK_TIMEOUT and the
other variables read by `lock_timeout`, or a timeout given to the API) and what a waiter does with each one
while another process holds the lock.

Python's own thread locks refuse a timeout that is not a number (nan), an infinite one, and one longer than
`threading.TIMEOUT_MAX` (4,294,967 s on Windows, about 49.7 days). A waiter hands its limit to such a lock
only after its first LOCK_NOTICE_SECONDS, so a value like that worked while nobody held the lock and failed
under contention. An infinite or very long limit means "wait until the lock is free"; nan is no number of
seconds and the default is used instead. A limit is the whole wait, the wait for another thread of the same
process included.

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import json
import math
import os
import subprocess
import sys
import threading
import time

import pytest

from cmeta.utils import files

# A process that holds a lock for a while and says when it has it
HOLDER = r'''
import sys, time
from cmeta.utils import files
lock = files.PathLock(sys.argv[1]).acquire(timeout=60)
print('LOCKED', flush=True)
time.sleep(float(sys.argv[2]))
lock.release()
print('RELEASED', flush=True)
'''


def hold(lock_file, seconds):
    """Start a process that holds `lock_file` for `seconds`; return it once it holds the lock."""
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'

    p = subprocess.Popen([sys.executable, '-c', HOLDER, lock_file, str(seconds)],
                         stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)

    line = p.stdout.readline().decode('utf-8', 'replace')
    assert line.startswith('LOCKED'), line
    return p


def stop(p):
    if p.poll() is None:
        p.kill()
    p.communicate(timeout=30)


##########################################################################################
# The values a timeout can take

def test_the_values_of_the_timeout_variable(monkeypatch, caplog):
    for value, expected in (('', 30.0), ('   ', 30.0), ('0', 0.0), ('-5', 0.0), ('2.5', 2.5), (' 7 ', 7.0),
                            ('1e7', 1e7)):
        monkeypatch.setenv(files.LOCK_TIMEOUT_ENV, value)
        assert files.lock_timeout() == expected, value

    # No limit: the waiter waits until the lock is free
    for value in ('inf', 'Infinity', '+inf'):
        monkeypatch.setenv(files.LOCK_TIMEOUT_ENV, value)
        assert math.isinf(files.lock_timeout()), value

    # nan is no number of seconds: the default, with the same warning as for words
    for value in ('nan', 'NaN', '-nan'):
        caplog.clear()
        monkeypatch.setenv(files.LOCK_TIMEOUT_ENV, value)
        assert files.lock_timeout() == 30.0, value
        assert 'is not a number of seconds' in caplog.text, value

    # Another variable with its own default (the index lock, the cache wait of the task engine)
    monkeypatch.setenv('CMETA_OTHER_TIMEOUT_FOR_THIS_TEST', 'nan')
    assert files.lock_timeout(600, 'CMETA_OTHER_TIMEOUT_FOR_THIS_TEST') == 600.0


def test_a_lock_without_a_limit_is_taken_at_once_when_it_is_free(tmp_path):
    for value in (float('inf'), threading.TIMEOUT_MAX * 2, 1e12):
        lock = files.PathLock(str(tmp_path / 'free.lock')).acquire(timeout=value)
        assert lock.is_locked
        lock.release()


def test_a_timeout_that_is_not_a_number_is_refused_by_name(tmp_path):
    lock_file = str(tmp_path / 'nan.lock')
    with pytest.raises(ValueError) as e:
        files.PathLock(lock_file).acquire(timeout=float('nan'))
    assert lock_file in str(e.value) and 'not a number' in str(e.value), str(e.value)
    assert not os.path.exists(lock_file)

    # ... and nothing of the lock is left held: the next acquire of this process takes it
    lock = files.PathLock(lock_file).acquire(timeout=1)
    lock.release()


##########################################################################################
# The wall clock is set while a wait runs

def test_an_unlocked_read_is_tried_when_the_wall_clock_jumps_forward(tmp_path, monkeypatch):
    """The retries of a read without a lock run on the monotonic clock. On the wall clock, a forward step of
    more than the retry time (NTP, a virtual machine's clock sync: WSL2 was seen stepping it by 6 s every 30 s)
    between the start and the first check meant no read at all - and a success with no data."""
    target = str(tmp_path / 'data.json')
    assert files.safe_write_file(target, {'a': 1})['return'] == 0

    real = time.time
    calls = {'n': 0}

    def jumping():
        calls['n'] += 1
        return real() + (0 if calls['n'] == 1 else 10.0)    # 10 s later from the second look on

    monkeypatch.setattr(time, 'time', jumping)
    r = files.safe_read_file(target)
    monkeypatch.setattr(time, 'time', real)

    assert r['return'] == 0 and r['data'] == {'a': 1}, r


##########################################################################################
# A waiter under contention

@pytest.mark.parametrize('how', ['inf', 'over-timeout-max', 'env-inf'])
def test_a_waiter_without_a_limit_waits_for_the_holder(tmp_path, monkeypatch, capfd, how):
    target = str(tmp_path / 'shared.json')
    assert files.safe_write_file(target, {'n': 0})['return'] == 0

    if how == 'env-inf':
        monkeypatch.setenv(files.LOCK_TIMEOUT_ENV, 'inf')
        timeout = None
    else:
        timeout = float('inf') if how == 'inf' else threading.TIMEOUT_MAX * 2

    # The holder keeps the lock past the first LOCK_NOTICE_SECONDS of the waiter: the waiter says so and
    # then waits with the rest of its limit - the step that failed
    seconds = files.LOCK_NOTICE_SECONDS + 1.5
    holder = hold(target + '.lock', seconds)
    try:
        t0 = time.monotonic()
        r = files.safe_write_file(target, {'n': 1}, timeout=timeout)
        elapsed = time.monotonic() - t0
    finally:
        stop(holder)

    assert r['return'] == 0, r.get('error')
    assert json.load(open(target)) == {'n': 1}
    assert files.LOCK_NOTICE_SECONDS <= elapsed < seconds + 20, elapsed

    out = capfd.readouterr().out
    assert 'cMeta warning: ' in out and 'is locked by another process' in out, out


def test_a_timeout_is_the_whole_wait_with_the_wait_for_another_thread(tmp_path):
    lock_file = str(tmp_path / 'both.lock')

    # Another process holds the lock all along
    holder = hold(lock_file, 60)
    try:
        # A thread of this process waits for it 1 s and gives up; while it waits it holds this process's
        # turn on the path, so the second waiter first waits for that thread
        def first():
            try:
                files.PathLock(lock_file).acquire(timeout=1.0)
            except TimeoutError:
                pass

        thread = threading.Thread(target=first)
        thread.start()
        time.sleep(0.2)

        t0 = time.monotonic()
        with pytest.raises(TimeoutError):
            files.PathLock(lock_file).acquire(timeout=1.5)
        elapsed = time.monotonic() - t0
        thread.join(30)
    finally:
        stop(holder)

    # 1.5 s in all - not the ~0.8 s of the thread plus 1.5 s more for the process
    assert 1.4 <= elapsed < 2.1, elapsed
