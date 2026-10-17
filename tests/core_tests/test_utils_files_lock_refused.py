"""
Tests of a lock file that cannot be created: a folder that is read-only for this process (a read-only mount, a
folder of another user, a repository mounted into a container under another uid). Nobody holds such a lock and
waiting does not help, so the lock is refused at once (LockFileRefused): a read goes on without it, a write
fails at once and says why. Before 0.37.2 both waited the whole lock timeout (30 s) and were told that the file
was "locked by another process" (seen 2026-10-15 inside a container on a bind mount).

A lock file refused for an instant is still a lock being released (Windows refuses to create a file that is
being deleted): that stays a busy lock, tried again.

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import errno
import os
import subprocess
import sys
import time

import pytest

from cmeta import CMeta
from cmeta.utils import files

WINDOWS = sys.platform == 'win32'


def _sid():
    out = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'], stdin=subprocess.DEVNULL,
                         capture_output=True, timeout=30).stdout.decode('utf-8', 'replace')
    return out.strip().split(',')[-1].strip().strip('"')


@pytest.fixture()
def read_only(tmp_path):
    """A folder with a file in it that this process can read but where it cannot create a file."""
    folder = tmp_path / 'ro'
    folder.mkdir()
    (folder / 'data.json').write_text('{"x": 1}', encoding='utf-8')

    if WINDOWS:
        sid = _sid()
        subprocess.run(['icacls', str(folder), '/deny', f'*{sid}:(WD,AD)'], stdin=subprocess.DEVNULL,
                       capture_output=True, check=True, timeout=60)
        try:
            open(folder / 'probe', 'w').close()
            pytest.skip('the deny entry did not take (an administrator token?)')
        except PermissionError:
            pass
        yield folder
        subprocess.run(['icacls', str(folder), '/remove:d', f'*{sid}'], stdin=subprocess.DEVNULL,
                       capture_output=True, timeout=60)
    else:
        if os.geteuid() == 0:
            pytest.skip('root writes into a folder whatever its mode')
        folder.chmod(0o555)
        yield folder
        folder.chmod(0o755)


def test_the_lock_is_refused_at_once_not_waited_for(read_only):
    lock = files.PathLock(str(read_only / 'data.json.lock'))
    t0 = time.monotonic()
    with pytest.raises(files.LockFileRefused) as e:
        lock.acquire(timeout=20)
    assert time.monotonic() - t0 < 2
    assert 'read-only for this process' in str(e.value)
    assert not lock.is_locked

    # the thread lock of the path was given back: the next attempt is refused the same way, not "held by a thread"
    with pytest.raises(files.LockFileRefused):
        lock.acquire(timeout=0)


def test_a_read_goes_on_without_the_lock(read_only):
    t0 = time.monotonic()
    r = files.safe_read_file(str(read_only / 'data.json'), lock=True)
    assert r['return'] == 0, r
    assert r['data'] == {'x': 1}

    r = files.safe_read_file(str(read_only / 'data.json'), lock=True, keep_locked=True)
    assert r['return'] == 0, r
    assert r['data'] == {'x': 1} and r['file_lock'] is None
    assert files.unlock_path(str(read_only / 'data.json'), r['file_lock'])['return'] == 0
    assert time.monotonic() - t0 < 4

    r = files.safe_read_yaml_or_json(str(read_only / 'data'), lock=True)
    assert r['return'] == 0 and r['data'] == {'x': 1}


def test_a_write_fails_at_once_and_says_why(read_only):
    t0 = time.monotonic()
    r = files.safe_write_file(str(read_only / 'new.json'), {'y': 2})
    assert r['return'] > 0
    assert time.monotonic() - t0 < 4
    assert 'read-only for this process' in r['error']
    assert 'locked by another process' not in r['error']


def test_a_read_only_soft_lock_folder_is_refused_too(read_only, monkeypatch):
    monkeypatch.setattr(files, '_lock_soft_dirs', [str(read_only)])
    with pytest.raises(files.LockFileRefused):
        files.PathLock(str(read_only / 'data.json.lock')).acquire(timeout=10)
    r = files.safe_read_file(str(read_only / 'data.json'), lock=True)
    assert r['return'] == 0 and r['data'] == {'x': 1}


def test_a_read_only_file_system_is_refused_at_once(tmp_path, monkeypatch):
    real_open = os.open

    def erofs(path, *args, **kwargs):
        if str(path).endswith('.lock'):
            raise OSError(errno.EROFS, 'Read-only file system', path)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(files.os, 'open', erofs)
    t0 = time.monotonic()
    with pytest.raises(files.LockFileRefused):
        files.PathLock(str(tmp_path / 'x.lock')).acquire(timeout=10)
    assert time.monotonic() - t0 < 1


def test_a_refusal_for_an_instant_is_a_busy_lock(tmp_path, monkeypatch):
    """Windows refuses a file being deleted for an instant (the holder that just released it): tried again."""
    real_open = os.open
    refused = {'n': 0}

    def flaky(path, *args, **kwargs):
        if str(path).endswith('.lock') and refused['n'] < 3:
            refused['n'] += 1
            raise PermissionError(errno.EACCES, 'Permission denied', path)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(files.os, 'open', flaky)
    lock = files.PathLock(str(tmp_path / 'x.lock')).acquire(timeout=10)
    assert lock.is_locked and refused['n'] == 3
    lock.release()


def test_a_read_only_repository_is_plugged_and_found(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_SOFT_LOCK_PATHS'):
        monkeypatch.delenv(var, raising=False)
    home = tmp_path / 'home'
    monkeypatch.setenv('CMETA_HOME', str(home))

    repo = tmp_path / 'data-repo'
    (repo / 'log' / 'note-a').mkdir(parents=True)
    (repo / '_cmr.yaml').write_text('artifact: data-repo,d1b2c3d4e5f60718\ncategory: repo,f4f792ab40c7498f\n',
                                    encoding='utf-8')
    (repo / 'log' / 'note-a' / '_cmeta.yaml').write_text('artifact: e1b2c3d4e5f60718\ncategory: log,f1b42d8e3e1a4b50\n',
                                                          encoding='utf-8')

    # read-only: the repository folder, the category folder and the artifact folder
    if WINDOWS:
        sid = _sid()
        for p in (repo, repo / 'log', repo / 'log' / 'note-a'):
            subprocess.run(['icacls', str(p), '/deny', f'*{sid}:(WD,AD)'], stdin=subprocess.DEVNULL,
                           capture_output=True, check=True, timeout=60)
        try:
            open(repo / 'probe', 'w').close()
            pytest.skip('the deny entry did not take (an administrator token?)')
        except PermissionError:
            pass
    else:
        if os.geteuid() == 0:
            pytest.skip('root writes into a folder whatever its mode')
        for p in (repo / 'log' / 'note-a', repo / 'log', repo):
            p.chmod(0o555)

    try:
        cm = CMeta(home=str(home))
        t0 = time.monotonic()
        r = cm.access({'category': 'repo', 'command': 'plug', 'arg1': str(repo), 'con': False})
        assert r['return'] == 0, r.get('error')
        r = cm.access({'category': 'log', 'command': 'find', 'arg1': 'data-repo:note-a', 'con': False})
        assert r['return'] == 0 and len(r['artifacts']) == 1, r
        r = cm.access({'category': 'log', 'command': 'read', 'arg1': 'data-repo:note-a', 'con': False})
        assert r['return'] == 0, r.get('error')
        assert time.monotonic() - t0 < 20

        # a change of the artifact fails and says why, at once
        t0 = time.monotonic()
        r = cm.access({'category': 'log', 'command': 'update', 'arg1': 'data-repo:note-a', 'meta': {'y': 1}, 'con': False})
        assert r['return'] > 0
        assert 'read-only' in r['error'] or 'ermission' in r['error'], r['error']
        assert time.monotonic() - t0 < 10
    finally:
        if WINDOWS:
            for p in (repo, repo / 'log', repo / 'log' / 'note-a'):
                subprocess.run(['icacls', str(p), '/remove:d', f'*{sid}'], stdin=subprocess.DEVNULL,
                               capture_output=True, timeout=60)
        else:
            for p in (repo, repo / 'log', repo / 'log' / 'note-a'):
                p.chmod(0o755)
