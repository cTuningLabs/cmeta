"""
The cserver app, started as uvicorn starts it, killed outright: its worker processes end with it and its port is free
at once (2026-11-05). Before, the workers of a dead server stayed - and on Linux (Python up to 3.13, the workers
forked) they kept the listening socket, so the next start of the server failed with "address already in use" until
someone killed them by hand.

The server runs on a free loopback port with a home of the test (CMETA_HOME under tmp_path) and two workers; its
startup makes the first pool call, so the workers exist before the request. Needs the server extra (uvicorn, fastapi).
"""

import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

pytest.importorskip('uvicorn')
pytest.importorskip('fastapi')

import cmeta  # noqa: E402

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(cmeta.__file__)), 'internal-repo', 'app', 'cserver')
HOME_VARS = ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX')


def free_port():
    s = socket.socket()
    try:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]
    finally:
        s.close()


def port_bindable(port):
    """A plain bind on Windows, with SO_REUSEADDR elsewhere (as utils.net.port_free decides): True when no process
    listens on the port."""
    s = socket.socket()
    try:
        if sys.platform != 'win32':
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('127.0.0.1', port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def descendants(pid):
    """The pids under a process (children, their children ...): Linux through /proc, macOS and the BSDs through ps;
    an empty set on Windows (the port check decides there)."""
    if sys.platform == 'win32':
        return set()
    parents = {}
    if sys.platform.startswith('linux'):
        for name in os.listdir('/proc'):
            if name.isdigit():
                try:
                    with open('/proc/%s/stat' % name) as f:
                        fields = f.read().rsplit(')', 1)[1].split()
                    parents[int(name)] = int(fields[1])
                except (OSError, IndexError, ValueError):
                    continue
    else:
        out = subprocess.run(['ps', '-axo', 'pid=,ppid='], capture_output=True, text=True).stdout
        for line in out.splitlines():
            try:
                child, parent = (int(x) for x in line.split()[:2])
                parents[child] = parent
            except ValueError:
                continue
    found, todo = set(), [pid]
    while todo:
        p = todo.pop()
        for child, parent in parents.items():
            if parent == p and child not in found:
                found.add(child)
                todo.append(child)
    return found


def alive(pids):
    live = set()
    for p in pids:
        try:
            os.kill(p, 0)
        except ProcessLookupError:
            continue
        except PermissionError:
            live.add(p)
            continue
        if sys.platform.startswith('linux'):
            try:
                with open('/proc/%d/status' % p) as f:
                    if 'State:\tZ' in f.read():
                        continue
            except OSError:
                continue
        live.add(p)
    return live


def test_the_cserver_workers_die_with_the_server(tmp_path, monkeypatch):
    env = dict(os.environ)
    for var in HOME_VARS + ('CMETA_DEBUG', 'CMETA_VERBOSE', 'CMETA_LOG', 'CMETA_LOG_FILE', 'CSERVER_WORKERS',
                            'CMETA_ASYNC_START_METHOD', 'CMETA_ASYNC_PARENT_WATCH'):
        env.pop(var, None)
    env['CMETA_HOME'] = str(tmp_path / 'home')
    env['HOME'] = env['USERPROFILE'] = str(tmp_path / 'user')
    (tmp_path / 'user').mkdir()
    env['CSERVER_WORKERS'] = '2'
    env['CSERVER_SESSION_SECRET'] = 'test-' * 8

    port = free_port()
    log = open(str(tmp_path / 'server.log'), 'wb')
    proc = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'src.app:app', '--host', '127.0.0.1', '--port', str(port),
                             '--no-use-colors'], cwd=APP_DIR, env=env, stdin=subprocess.DEVNULL, stdout=log,
                            stderr=subprocess.STDOUT)
    try:
        # the server answers (its startup made the first pool call: the workers are there)
        end = time.monotonic() + 120
        status = None
        while time.monotonic() < end and proc.poll() is None:
            try:
                with urllib.request.urlopen('http://127.0.0.1:%d/' % port, timeout=5) as r:
                    status = r.status
                break
            except Exception:
                time.sleep(0.5)
        if status is None:
            log.close()
            pytest.fail('the cserver did not answer: %s' % open(str(tmp_path / 'server.log'), errors='replace').read()[-2000:])
        assert not port_bindable(port)

        workers = descendants(proc.pid)
        if sys.platform != 'win32':
            assert workers, 'no worker process under the server'

        proc.kill()                                   # outright: no shutdown, no signal handler
        proc.wait(timeout=60)

        end = time.monotonic() + 20
        while time.monotonic() < end and (alive(workers) or not port_bindable(port)):
            time.sleep(0.25)
        assert not alive(workers), 'workers outlived the server: %s' % sorted(alive(workers))
        assert port_bindable(port), 'the port %d is still taken after the server died' % port
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=60)
        log.close()
