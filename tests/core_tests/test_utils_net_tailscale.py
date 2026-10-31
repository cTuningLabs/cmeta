"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

cMeta core tests - utils.net.tailscale_ipv4 (`cx app run cserver --param.host=tailscale`): Tailscale's own answer
to "tailscale ip -4", an address of its range or an error - never another address - and the launcher's entry
"python -m cmeta.utils.net tailscale_ipv4". Tailscale is not needed: the command is replaced.
"""

import runpy
import shutil
import subprocess
import sys

import pytest

import cmeta.utils.net as net


def answer(stdout=b'', stderr=b'', returncode=0, raises=None, calls=None):
    """A stand-in for subprocess.run that answers like the Tailscale command."""
    def run(cmd, **kwargs):
        if calls is not None:
            calls.append(cmd)
        if raises is not None:
            raise raises
        return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)
    return run


@pytest.fixture()
def cli(monkeypatch):
    """The Tailscale command found on PATH."""
    monkeypatch.setattr(shutil, 'which', lambda name: '/fake/bin/tailscale' if name == 'tailscale' else None)


def test_the_address_tailscale_gives(cli, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, 'run', answer(b'100.126.12.65\n', calls=calls))
    assert net.tailscale_ipv4() == {'return': 0, 'ip': '100.126.12.65', 'cli': '/fake/bin/tailscale'}
    assert calls == [['/fake/bin/tailscale', 'ip', '-4']]


@pytest.mark.parametrize('stdout, stderr, said', [
    (b'', b'Tailscale is stopped.\n', 'Tailscale is stopped.'),
    (b'', b'', 'no answer'),
    (b'192.168.1.67\n', b'', '192.168.1.67'),          # a LAN address is never taken
    (b'fd7a:115c:a1e0::4f3a:c41\n', b'', 'fd7a'),        # nor an IPv6 one
])
def test_no_address_of_its_own_is_an_error(cli, monkeypatch, stdout, stderr, said):
    monkeypatch.setattr(subprocess, 'run', answer(stdout, stderr, returncode=1 if stderr else 0))
    r = net.tailscale_ipv4()
    assert r['return'] == 1 and 'ip' not in r
    assert said in r['error'] and 'running and logged in' in r['error']


def test_the_first_address_of_its_range_among_other_lines(cli, monkeypatch):
    monkeypatch.setattr(subprocess, 'run', answer(b'warning: something\n10.0.0.2\n100.102.205.109\n'))
    assert net.tailscale_ipv4()['ip'] == '100.102.205.109'


def test_a_command_that_hangs_or_cannot_run(cli, monkeypatch):
    monkeypatch.setattr(subprocess, 'run', answer(raises=subprocess.TimeoutExpired('tailscale', 3)))
    assert 'did not answer within 3 s' in net.tailscale_ipv4(timeout=3)['error']
    monkeypatch.setattr(subprocess, 'run', answer(raises=PermissionError('denied')))
    assert 'could not run: denied' in net.tailscale_ipv4()['error']


def test_not_on_path_then_where_the_installers_put_it(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, 'which', lambda name: None)
    platform = 'linux' if sys.platform.startswith('linux') else sys.platform
    monkeypatch.setitem(net.TAILSCALE_CLI_PLACES, platform, [str(tmp_path / 'none'), str(tmp_path / 'tailscale')])
    r = net.tailscale_ipv4()
    assert r['return'] == 1 and 'not installed' in r['error']

    (tmp_path / 'tailscale').write_text('')
    monkeypatch.setattr(subprocess, 'run', answer(b'100.95.21.23\n'))
    assert net.tailscale_ipv4() == {'return': 0, 'ip': '100.95.21.23', 'cli': str(tmp_path / 'tailscale')}


def test_the_utils_package_keeps_its_own_sys_module():
    """2026-10-31: an "import sys" at the top of net.py, which cmeta.utils star-imports last, put Python's sys over
    cmeta.utils.sys - every call through CMetaAsync then failed ("module 'sys' has no attribute 'get_min_host_info'")
    and the cserver stopped at its start."""
    import cmeta.utils as utils
    import cmeta.utils.sys as engine_sys
    assert utils.sys is engine_sys and hasattr(utils.sys, 'get_min_host_info')


def test_the_launchers_entry(cli, monkeypatch, capsys):
    """python -m cmeta.utils.net tailscale_ipv4: the address alone on stdout, or the reason and exit code 1."""
    monkeypatch.setattr(sys, 'argv', ['net.py', 'tailscale_ipv4'])
    monkeypatch.setattr(subprocess, 'run', answer(b'100.94.236.2\n'))
    runpy.run_module('cmeta.utils.net', run_name='__main__')
    assert capsys.readouterr().out == '100.94.236.2\n'

    monkeypatch.setattr(subprocess, 'run', answer(b'', b'Tailscale is stopped.\n', returncode=1))
    with pytest.raises(SystemExit) as stop:
        runpy.run_module('cmeta.utils.net', run_name='__main__')
    assert str(stop.value).startswith('cMeta notice: Tailscale gave no address') and str(stop.value).endswith('!')

    monkeypatch.setattr(sys, 'argv', ['net.py'])
    with pytest.raises(SystemExit) as stop:
        runpy.run_module('cmeta.utils.net', run_name='__main__')
    assert 'usage' in str(stop.value)
