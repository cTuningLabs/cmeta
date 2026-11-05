"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

cMeta core tests - utils.net.port_free (the cserver app's _run.bat / _run.sh ask it before uvicorn starts): a port
another server listens on is refused - on Windows a second server that sets SO_REUSEADDR, as uvicorn does with
--reload or --workers, would bind it all the same and share its connections unseen (two servers started on one port,
by AI sessions working at once) -, the process that holds it named when the system says so, and the launcher's entry
"python -m cmeta.utils.net port_free <host> <port>". Real sockets on 127.0.0.1, no server.
"""

import os
import runpy
import socket
import sys

import pytest

import cmeta.utils.net as net


def a_free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture()
def listener():
    """A socket listening on a free port of 127.0.0.1 with SO_REUSEADDR set, as uvicorn's -> its port."""
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('127.0.0.1', 0))
    s.listen(5)
    yield s.getsockname()[1]
    s.close()


def test_a_port_nobody_listens_on_is_free():
    assert net.port_free('127.0.0.1', a_free_port()) == {'return': 0, 'free': True}


def test_a_port_a_server_listens_on_is_refused_and_its_process_named(listener):
    r = net.port_free('127.0.0.1', listener)
    assert r['return'] == 0 and r['free'] is False and r['in_use'] is True and r['reason']

    # named where the system's tool is there (PowerShell, lsof, ss): this very process
    if r['pid'] is not None:
        assert r['pid'] == os.getpid() and 'python' in (r['name'] + ' ' + r['cmd']).lower()


def test_free_again_once_the_server_is_gone():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    s.listen(5)
    port = s.getsockname()[1]
    assert net.port_free('127.0.0.1', port)['free'] is False
    s.close()
    assert net.port_free('127.0.0.1', port)['free'] is True


def test_what_a_closed_server_leaves_is_no_server():
    """A connection the server closed first leaves TIME_WAIT on its port: no server any more (Linux and macOS need
    SO_REUSEADDR on the probe for that, Windows a plain bind)."""
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('127.0.0.1', 0))
    srv.listen(5)
    port = srv.getsockname()[1]

    client = socket.create_connection(('127.0.0.1', port))
    conn, _ = srv.accept()
    conn.close()
    client.close()
    srv.close()

    assert net.port_free('127.0.0.1', port)['free'] is True


@pytest.mark.parametrize('port', ['x', '', '0', '70000'])
def test_a_port_that_is_no_number(port):
    r = net.port_free('127.0.0.1', port)
    assert r['return'] == 1 and 'port' in r['error']


def test_an_address_of_another_machine_cannot_be_used():
    r = net.port_free('192.0.2.1', a_free_port())             # TEST-NET-1: never an address of this machine
    assert r['return'] == 0 and r['free'] is False and r['in_use'] is False and r['reason']


def test_the_launchers_entry(listener, monkeypatch, capsys):
    """python -m cmeta.utils.net port_free <host> <port>: nothing while the port is free; else the reason, exit code 1."""
    monkeypatch.setattr(sys, 'argv', ['net.py', 'port_free', '127.0.0.1', str(a_free_port())])
    runpy.run_module('cmeta.utils.net', run_name='__main__')
    assert capsys.readouterr() == ('', '')

    monkeypatch.setattr(sys, 'argv', ['net.py', 'port_free', '127.0.0.1', str(listener)])
    with pytest.raises(SystemExit) as stop:
        runpy.run_module('cmeta.utils.net', run_name='__main__')
    said = str(stop.value)
    assert said.startswith(f'cMeta notice: port {listener} of 127.0.0.1 is in use - ') and said.endswith('!')
    assert '--param.port=<port>' in said

    monkeypatch.setattr(sys, 'argv', ['net.py', 'port_free', '192.0.2.1', str(a_free_port())])
    with pytest.raises(SystemExit) as stop:
        runpy.run_module('cmeta.utils.net', run_name='__main__')
    assert 'cannot be used here' in str(stop.value)

    monkeypatch.setattr(sys, 'argv', ['net.py', 'port_free', '127.0.0.1', 'x'])
    with pytest.raises(SystemExit) as stop:
        runpy.run_module('cmeta.utils.net', run_name='__main__')
    assert 'not a port number' in str(stop.value)


def test_the_cserver_scripts_ask_before_uvicorn_starts():
    """Both run scripts of the cserver app ask port_free with the host and the port uvicorn gets, before it starts."""
    app = os.path.join(os.path.dirname(net.__file__), '..', 'internal-repo', 'app', 'cserver')
    for name, ask in (('_run.bat', 'port_free %CSERVER_HOST% %CSERVER_PORT%'),
                      ('_run.sh', 'port_free "${CSERVER_HOST}" "${CSERVER_PORT}"')):
        with open(os.path.join(app, name), encoding = 'utf-8') as f:
            text = f.read()
        assert 0 < text.find(ask) < text.find('-m uvicorn'), name
