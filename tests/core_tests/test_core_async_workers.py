"""
The worker processes of CMetaAsync: how they are started, that they hold nothing of the server, that they die with it.

Why (2026-11-05): Python started the workers by "fork" on Linux up to 3.13 - copies of the server process, taken at
the first call. A copy of a client connection kept it open after the server closed its end: no FIN reached the
client, a proxy reused the dead connection and its next request hung (a site behind a proxy, once per start); a copy
of the listening socket kept the port taken after the server died (orphans holding the port, 2026-10-27). The engine
never forks a server now (forkserver on Linux, spawn on Windows and macOS, an override for those who insist), every
worker watches its parent and ends with it, and `warm()` starts the workers before a server accepts anyone.

Every home is under tmp_path: nothing of the user's cMeta is touched. The tests start small pools (one to three
workers) and one short-lived server process; the whole file takes about half a minute.
"""

import asyncio
import json
import logging
import multiprocessing
import os
import signal
import socket
import subprocess
import sys
import textwrap
import time

import pytest

from cmeta.core_async import (CMetaAsync, default_start_method, start_method_context, PARENT_WATCH_ENV,
                              START_METHOD_ENV)

HOME_VARS = ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX')

SIMPLE = {'category': 'category', 'command': 'find', 'arg1': 'config', 'con': False}

# a warm-up of this test: the calls are held long enough for every worker to start and take one of them, on a
# Windows machine that starts an interpreter in a second too
HOLD = 2.0

FORK_HERE = 'fork' in multiprocessing.get_all_start_methods()


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """A cMeta home of the test, chosen by CMETA_HOME; the user's folder is a folder of the test too; no override
    of the start method or the parent watch from the environment."""
    for var in HOME_VARS + ('CMETA_DEBUG', 'CMETA_VERBOSE', 'CMETA_LOG', 'CMETA_LOG_FILE', START_METHOD_ENV,
                            PARENT_WATCH_ENV):
        monkeypatch.delenv(var, raising=False)

    user = tmp_path / 'user'
    user.mkdir()
    monkeypatch.setenv('HOME', str(user))
    monkeypatch.setenv('USERPROFILE', str(user))

    folder = tmp_path / 'home'
    monkeypatch.setenv('CMETA_HOME', str(folder))
    return folder


def connection_pair():
    """A listening socket of the test, a client connected to it and the server's end of that connection. The
    listener carries SO_REUSEADDR as uvicorn's does: on Linux the sockets of its connections inherit the option, and
    only then may the port be bound again while one of them is still closing (FIN-WAIT-2, TIME-WAIT) - BSD, macOS
    and Windows allow that bind anyway."""
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('127.0.0.1', 0))
    srv.listen(1)
    cli = socket.create_connection(srv.getsockname())
    conn, _ = srv.accept()
    return srv, cli, conn


def port_bindable(address):
    """Whether the address can be bound now - as utils.net.port_free decides: a plain bind on Windows, with
    SO_REUSEADDR elsewhere (a connection that is closing is no listener; a copy of the listening socket is)."""
    s = socket.socket()
    try:
        if sys.platform != 'win32':
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(address)
        return True
    except OSError:
        return False
    finally:
        s.close()


def pid_alive(pid):
    """Whether a process is still there (a zombie counts as gone), on every platform."""
    if sys.platform == 'win32':
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259                                # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    if sys.platform.startswith('linux'):
        try:
            with open('/proc/%d/status' % pid) as f:
                return 'State:\tZ' not in f.read()
        except OSError:
            return False
    out = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)], capture_output=True, text=True).stdout.strip()
    return bool(out) and not out.startswith('Z')


def wait_until(condition, seconds):
    """True as soon as condition() holds, False after the seconds."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.1)
    return condition()


# ------------------------------------------------------------------------------------------------ the start method
def test_the_default_never_forks(home):
    """The engine's choice: spawn on Windows and macOS, forkserver elsewhere (spawn where it is missing) - never fork."""
    method = default_start_method()
    assert method != 'fork'
    if sys.platform in ('win32', 'darwin'):
        assert method == 'spawn'
    else:
        assert method == ('forkserver' if 'forkserver' in multiprocessing.get_all_start_methods() else 'spawn')
    assert start_method_context().get_start_method() == method

    cm = CMetaAsync(max_workers=1)
    try:
        assert cm.start_method == method
        assert cm.watch_parent is True
        assert cm.max_workers == 1
        r = asyncio.run(cm.access(dict(SIMPLE)))
        assert r['return'] == 0, r.get('error')
    finally:
        cm.shutdown()


def test_the_argument_and_the_environment_choose(home, monkeypatch):
    """CMETA_ASYNC_START_METHOD names the method, the constructor argument wins over it, an unknown one is refused."""
    monkeypatch.setenv(START_METHOD_ENV, 'spawn')
    cm = CMetaAsync(max_workers=1)
    try:
        assert cm.start_method == 'spawn'
    finally:
        cm.shutdown()

    monkeypatch.setenv(START_METHOD_ENV, 'no-such-method')
    with pytest.raises(ValueError) as e:
        CMetaAsync(max_workers=1)
    assert 'no-such-method' in str(e.value) and START_METHOD_ENV in str(e.value)

    cm = CMetaAsync(max_workers=1, start_method='spawn')          # the argument, whatever the environment says
    try:
        assert cm.start_method == 'spawn'
        r = asyncio.run(cm.access(dict(SIMPLE)))
        assert r['return'] == 0, r.get('error')
    finally:
        cm.shutdown()


@pytest.mark.skipif(not FORK_HERE, reason='this platform has no fork')
def test_fork_is_allowed_with_a_warning(home):
    """Whoever asks for fork gets it - and a warning on the logger of the object."""
    logger = logging.getLogger('test-core-async-fork')
    seen = []

    class Catch(logging.Handler):
        def emit(self, record):
            seen.append(record.getMessage())

    handler = Catch()
    logger.addHandler(handler)
    try:
        cm = CMetaAsync(max_workers=1, start_method='fork', logger=logger)
        try:
            assert cm.start_method == 'fork'
            assert any('fork' in m and 'forkserver or spawn' in m for m in seen)
            r = asyncio.run(cm.access(dict(SIMPLE)))
            assert r['return'] == 0, r.get('error')
        finally:
            cm.shutdown()
    finally:
        logger.removeHandler(handler)


# ------------------------------------------------------------------------------- the workers hold nothing of the server
@pytest.mark.parametrize('start_method', [None, 'spawn'])
def test_the_workers_keep_no_copy_of_the_connections(home, start_method):
    """The trap of 2026-11-05, with plain sockets: the workers start while a client is connected to the server; when
    the server closes its end the client must see the end at once (no process keeps a copy of the connection), and
    the port must be free as soon as the server closes its listening socket (no process keeps a copy of it)."""
    srv, cli, conn = connection_pair()
    address = srv.getsockname()
    cm = CMetaAsync(max_workers=2, start_method=start_method)
    try:
        pids = cm.warm(hold=0.2)                  # the workers start now, with the connection open
        assert pids

        conn.close()                              # the server's end
        cli.settimeout(5)
        t0 = time.monotonic()
        assert cli.recv(16) == b''                # the end, at once - a copy would keep the client waiting
        assert time.monotonic() - t0 < 2

        srv.close()
        assert port_bindable(address)             # the port is free: no copy of the listening socket either
    finally:
        cli.close()
        srv.close()
        cm.shutdown()


@pytest.mark.skipif(sys.platform == 'win32' or not FORK_HERE, reason='fork is the method of the trap')
def test_the_trap_itself_under_fork_for_the_record(home):
    """What the engine's choice prevents, shown with the method that has it: under fork the forked workers hold copies
    of the connection and of the listening socket - the client waits after the server's close, the port stays taken."""
    srv, cli, conn = connection_pair()
    address = srv.getsockname()
    cm = CMetaAsync(max_workers=2, start_method='fork')
    try:
        cm.warm(hold=0.2)

        conn.close()
        cli.settimeout(1.5)
        with pytest.raises(socket.timeout):       # the copies keep it open: nothing reaches the client
            cli.recv(16)

        srv.close()
        assert not port_bindable(address)         # the copies keep the port
    finally:
        cli.close()
        srv.close()
        cm.shutdown()
        assert wait_until(lambda: port_bindable(address), 5)      # the workers gone, the port is free again


# ------------------------------------------------------------------------------------------- the workers die with the server
# (the guard is what every program that starts workers needs: spawn and forkserver import the main module again in
# the worker, and an unguarded one would start a pool of its own there)
SERVER = textwrap.dedent('''
    import json, os, sys
    from cmeta.core_async import CMetaAsync

    if __name__ == '__main__':
        cm = CMetaAsync(max_workers=1)
        workers = cm.warm(count=1, hold=0)
        print(json.dumps({"pid": os.getpid(), "workers": workers, "watch": cm.watch_parent}), flush=True)
        sys.stdin.read()          # until this process is killed
''')


def start_server(tmp_path, env):
    """A server process of this test (CMetaAsync with one warmed worker), and what it printed about itself."""
    script = tmp_path / 'server.py'
    script.write_text(SERVER, encoding='utf-8')
    proc = subprocess.Popen([sys.executable, str(script)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, env=env, cwd=str(tmp_path))
    line = proc.stdout.readline().decode('utf-8', 'replace').strip()
    assert line.startswith('{'), 'the server did not start: %s%s' % (line, proc.stdout.read().decode('utf-8', 'replace'))
    return proc, json.loads(line)


def test_the_workers_die_with_their_server(home, tmp_path):
    """A server killed outright (no shutdown, no signal handler: a crash, a kill -9, a TerminateProcess) takes its
    workers with it within seconds - they used to stay for days."""
    proc, info = start_server(tmp_path, dict(os.environ))
    worker = info['workers'][0]
    assert info['watch'] is True and pid_alive(worker)

    proc.kill()
    proc.wait(timeout=30)
    assert wait_until(lambda: not pid_alive(worker), 15), 'the worker %d outlived its server' % worker


def test_the_watch_can_be_switched_off(home, tmp_path):
    """CMETA_ASYNC_PARENT_WATCH=0 keeps the old behaviour: the worker outlives the server (and the test ends it)."""
    env = dict(os.environ, **{PARENT_WATCH_ENV: '0'})
    proc, info = start_server(tmp_path, env)
    worker = info['workers'][0]
    assert info['watch'] is False and pid_alive(worker)

    proc.kill()
    proc.wait(timeout=30)
    try:
        time.sleep(3)
        assert pid_alive(worker), 'the worker died although the watch was off'
    finally:
        try:
            os.kill(worker, signal.SIGTERM)
        except OSError:
            pass
    assert wait_until(lambda: not pid_alive(worker), 15)


# ------------------------------------------------------------------------------------------------------- warm()
def test_warm_starts_every_worker(home):
    """warm() starts the whole pool, each worker with its CMeta made, and returns their pids; a second warm-up finds
    the same processes; the pool serves as before."""
    cm = CMetaAsync(max_workers=3)
    try:
        t0 = time.monotonic()
        pids = cm.warm(hold=HOLD)
        assert len(pids) == 3 and len(set(pids)) == 3
        assert os.getpid() not in pids
        assert cm.warm(hold=HOLD) == pids

        t1 = time.monotonic()
        r = asyncio.run(cm.access(dict(SIMPLE)))
        assert r['return'] == 0, r.get('error')
        assert time.monotonic() - t1 < 5                      # a warm worker answers at once
        assert time.monotonic() - t0 < 60
    finally:
        cm.shutdown()


def test_warm_counts_and_warm_async(home):
    """warm(count=1) starts one worker; warm_async does the same from a coroutine, the loop free meanwhile."""
    cm = CMetaAsync(max_workers=2)
    try:
        one = cm.warm(count=1, hold=0)
        assert len(one) == 1

        async def both():
            ticks = []

            async def tick():
                for _ in range(5):
                    ticks.append(time.monotonic())
                    await asyncio.sleep(0.05)

            pids, _ = await asyncio.gather(cm.warm_async(hold=HOLD), tick())
            return pids, ticks

        pids, ticks = asyncio.run(both())
        assert len(pids) == 2 and one[0] in pids
        assert len(ticks) == 5 and ticks[-1] - ticks[0] < HOLD + 1   # the loop ran while the workers started
    finally:
        cm.shutdown()
