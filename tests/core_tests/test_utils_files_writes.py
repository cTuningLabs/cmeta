"""
Tests of the engine's writes and reads of shared files (cmeta.utils.files): the lock timeout and its
environment variable, the notice of a waiter, atomic writes by default for JSON, YAML and pickle (a reader
never sees a half-written file, a failed write leaves the previous file and no temporary), the mode of the
target kept, a symbolic link written through, a read-only target refused, the retries of a replace while a
reader holds the target, the reader cache keyed by time, size and inode, the cache under threads, the
pickle protocol of the index.

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import errno
import json
import os
import pickletools
import stat
import subprocess
import sys
import threading
import time

import pytest

from cmeta.utils import files

POSIX = sys.platform != 'win32'
ROOT = POSIX and os.geteuid() == 0

HOLDER = r'''
import sys, time
from cmeta.utils import files
lock = files.PathLock(sys.argv[1]).acquire(timeout=60, note=sys.argv[2])
print('LOCKED', flush=True)
time.sleep(float(sys.argv[3]))
lock.release()
print('RELEASED', flush=True)
'''


def hold(lock_file, note, seconds):
    """Another process holds `lock_file` with `note` for `seconds`; returns once it holds it."""
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    p = subprocess.Popen([sys.executable, '-c', HOLDER, lock_file, note, str(seconds)], env=env,
                         stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    line = p.stdout.readline().decode('utf-8', 'replace')
    assert 'LOCKED' in line, line
    return p


def stop(p):
    p.kill()
    p.communicate()


@pytest.fixture(autouse=True)
def no_lock_timeout_env(monkeypatch):
    monkeypatch.delenv(files.LOCK_TIMEOUT_ENV, raising=False)


def test_the_lock_timeout_comes_from_the_environment(monkeypatch, caplog):
    assert files.lock_timeout() == 30.0
    monkeypatch.setenv(files.LOCK_TIMEOUT_ENV, '7.5')
    assert files.lock_timeout() == 7.5
    monkeypatch.setenv(files.LOCK_TIMEOUT_ENV, 'soon')
    assert files.lock_timeout() == 30.0
    assert 'is not a number of seconds' in caplog.text
    monkeypatch.delenv(files.LOCK_TIMEOUT_ENV)
    assert files.lock_timeout(600, 'CMETA_OTHER_TIMEOUT_FOR_THIS_TEST') == 600.0


def test_a_writer_waiting_for_a_file_lock_says_so_and_gives_up_after_the_limit(tmp_path, capfd):
    target = str(tmp_path / 'shared.json')
    assert files.safe_write_file(target, {'n': 0})['return'] == 0
    holder = hold(target + '.lock', 'a test holding the file', 60)
    try:
        t0 = time.time()
        r = files.safe_write_file(target, {'n': 1}, timeout=5)
        elapsed = time.time() - t0
    finally:
        stop(holder)

    assert r['return'] > 0
    assert 'stayed locked by another process (a test holding the file)' in r['error'], r['error']
    assert files.LOCK_TIMEOUT_ENV in r['error'], r['error']
    assert 4.5 <= elapsed < 60, elapsed
    err = capfd.readouterr().err
    assert 'is locked by another process (a test holding the file)' in err and 'the write of' in err, err
    assert json.load(open(target)) == {'n': 0}
    assert not os.path.exists(target + '.tmp')


def test_structured_files_are_written_atomically_by_default(tmp_path):
    for name, data in (('a.json', {'a': 1}), ('a.yaml', {'a': 1}), ('a.pkl', {'a': 1})):
        target = str(tmp_path / name)
        r = files.safe_write_file(target, data)
        assert r['return'] == 0, r
        assert files.safe_read_file(target)['data'] == data
        assert not os.path.exists(target + '.tmp')
        assert not os.path.exists(target + '.lock')

    # A write that fails leaves the previous file and no temporary
    target = str(tmp_path / 'a.json')
    r = files.safe_write_file(target, {'a': object()})
    assert r['return'] > 0
    assert files.safe_read_file(target)['data'] == {'a': 1}
    assert not os.path.exists(target + '.tmp')

    # Text is written in place, without a temporary
    target = str(tmp_path / 'a.txt')
    assert files.safe_write_file(target, 'hello')['return'] == 0
    assert open(target).read() == 'hello'
    assert not os.path.exists(target + '.tmp')


def test_the_mode_of_the_target_is_kept_and_a_read_only_target_is_refused(tmp_path):
    target = str(tmp_path / 'm.json')
    assert files.safe_write_file(target, {'a': 1})['return'] == 0
    expected = {'a': 1}

    if POSIX:
        os.chmod(target, 0o640)
        if stat.S_IMODE(os.stat(target).st_mode) != 0o640:
            pytest.skip('the file system keeps no mode (a 9p or FAT mount)')
        assert files.safe_write_file(target, {'a': 2})['return'] == 0
        assert stat.S_IMODE(os.stat(target).st_mode) == 0o640
        expected = {'a': 2}
        assert files.safe_read_file(target)['data'] == expected

    if ROOT:
        return   # root writes read-only files, as it always did

    os.chmod(target, stat.S_IREAD)
    try:
        if os.access(target, os.W_OK):
            pytest.skip('the file system keeps no read-only mode (a 9p or FAT mount)')
        r = files.safe_write_file(target, {'a': 3})
        assert r['return'] > 0, r
        assert files.safe_read_file(target)['data'] == expected
        assert not os.path.exists(target + '.tmp')
    finally:
        os.chmod(target, stat.S_IWRITE | stat.S_IREAD)


@pytest.mark.skipif(not POSIX, reason='symbolic links need a privilege on Windows')
def test_a_symbolic_link_is_written_through(tmp_path):
    real = str(tmp_path / 'real.json')
    link = str(tmp_path / 'link.json')
    assert files.safe_write_file(real, {'a': 1})['return'] == 0
    os.symlink(real, link)
    assert files.safe_write_file(link, {'a': 2})['return'] == 0
    assert os.path.islink(link)
    assert json.load(open(real)) == {'a': 2}
    assert not os.path.exists(link + '.tmp')


def test_a_replace_waits_for_a_target_that_is_busy_and_gives_up_after_the_lock_timeout(tmp_path, monkeypatch):
    target = str(tmp_path / 'held.json')
    temp = target + '.tmp'
    with open(target, 'w') as f:
        f.write('{"a": 0}')
    with open(temp, 'w') as f:
        f.write('{"a": 1}')

    if not POSIX:
        # Windows: a reader holding the target open makes the replace fail until it closes it
        def read_for_a_while(seconds):
            with open(target):
                time.sleep(seconds)
        t = threading.Thread(target=read_for_a_while, args=(2.0,))
        t.start()
        time.sleep(0.2)
        t0 = time.time()
        files._replace_file(temp, target)
        elapsed = time.time() - t0
        t.join()
    else:
        # POSIX: os.replace itself never waits for a reader; a busy target is shown with a hook
        real = os.replace
        until = time.monotonic() + 1.5

        def busy(a, b):
            if time.monotonic() < until:
                raise PermissionError(errno.EACCES, 'busy for the test')
            return real(a, b)

        monkeypatch.setattr(os, 'replace', busy)
        t0 = time.time()
        files._replace_file(temp, target)
        elapsed = time.time() - t0
        monkeypatch.setattr(os, 'replace', real)

    assert 1.0 < elapsed < 20, elapsed
    assert json.load(open(target)) == {'a': 1}

    # The wait is bounded by the lock timeout
    with open(temp, 'w') as f:
        f.write('{"a": 2}')
    monkeypatch.setenv(files.LOCK_TIMEOUT_ENV, '1')

    if not POSIX:
        t = threading.Thread(target=read_for_a_while, args=(4.0,))
        t.start()
        time.sleep(0.2)
        t0 = time.time()
        with pytest.raises(PermissionError):
            files._replace_file(temp, target)
        elapsed = time.time() - t0
        t.join()
    else:
        def always_busy(a, b):
            raise PermissionError(errno.EACCES, 'busy for the test')
        monkeypatch.setattr(os, 'replace', always_busy)
        t0 = time.time()
        with pytest.raises(PermissionError):
            files._replace_file(temp, target)
        elapsed = time.time() - t0
        monkeypatch.setattr(os, 'replace', real)

    assert 0.9 <= elapsed < 10, elapsed
    assert json.load(open(target)) == {'a': 1}
    os.remove(temp)


def test_the_cache_sees_a_change_that_keeps_the_timestamp(tmp_path):
    target = str(tmp_path / 'c.json')
    cache = {}
    assert files.safe_write_file(target, {'a': 1})['return'] == 0
    st = os.stat(target)
    assert files.safe_read_file_via_cache(target, cache)['data'] == {'a': 1}
    assert cache[target]['stamp'] == (st.st_mtime_ns, st.st_size, st.st_ino)

    # A change of size within the same timestamp
    assert files.safe_write_file(target, {'a': 22})['return'] == 0
    os.utime(target, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert files.safe_read_file_via_cache(target, cache)['data'] == {'a': 22}

    # A change of the same size within the same timestamp: the replaced file has another inode (where
    # the file system reports inodes)
    assert files.safe_write_file(target, {'a': 33})['return'] == 0
    os.utime(target, ns=(st.st_atime_ns, st.st_mtime_ns))
    if os.stat(target).st_ino:
        assert files.safe_read_file_via_cache(target, cache)['data'] == {'a': 33}

    # Unchanged: served from the cache (the same object)
    first = files.safe_read_file_via_cache(target, cache)['data']
    assert files.safe_read_file_via_cache(target, cache)['data'] is first

    # A missing file never seen: the not-found code at once; a file read before that is missing is
    # retried for a moment (a replace in progress, the swap of a reindex) and found again
    t0 = time.time()
    r = files.safe_read_file_via_cache(str(tmp_path / 'absent.json'), cache)
    assert r['return'] == files.ERROR_CODE_FILE_NOT_FOUND
    assert time.time() - t0 < 0.5
    r = files.safe_read_file_via_cache(str(tmp_path), cache)
    assert r['return'] == 1 and 'is a directory' in r['error']

    gone = target + '.away'
    os.replace(target, gone)
    threading.Timer(0.03, lambda: os.replace(gone, target)).start()
    r = files.safe_read_file_via_cache(target, cache)
    assert r['return'] == 0 and r['data'] == {'a': 33}, r
    os.replace(target, gone)
    t0 = time.time()
    r = files.safe_read_file_via_cache(target, cache)
    assert r['return'] == files.ERROR_CODE_FILE_NOT_FOUND
    assert 0.05 < time.time() - t0 < 2, time.time() - t0
    os.replace(gone, target)


def test_the_cache_is_safe_for_threads(tmp_path):
    target = str(tmp_path / 't.json')
    assert files.safe_write_file(target, {'n': 0})['return'] == 0
    cache = {}
    errors = []

    def reader():
        try:
            for i in range(100):
                r = files.safe_read_file_via_cache(target, cache)
                assert r['return'] == 0 and 'n' in r['data'], r
                time.sleep(0.001)
        except Exception as e:
            errors.append(e)

    def writer():
        for i in range(1, 11):
            r = files.safe_write_file(target, {'n': i})
            assert r['return'] == 0, r
            time.sleep(0.01)

    threads = [threading.Thread(target=reader) for _ in range(4)] + [threading.Thread(target=writer)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert files.safe_read_file_via_cache(target, cache)['data'] == {'n': 10}


def test_a_pickle_is_written_with_protocol_4(tmp_path):
    target = str(tmp_path / 'p.pkl')
    assert files.safe_write_file(target, {'a': [1, 2]})['return'] == 0
    with open(target, 'rb') as f:
        ops = list(pickletools.genops(f))
    assert ops[0][0].name == 'PROTO' and ops[0][1] == files.PICKLE_PROTOCOL == 4
    assert files.safe_read_file(target)['data'] == {'a': [1, 2]}
