"""
Tests for the command that installs a package into this Python: pip when it is importable, else uv for this
interpreter, else pip after ensurepip - a cMeta installed as a uv tool runs on a Python without pip.

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import importlib.util
import sys

import pytest

from cmeta.packages import Packages


def test_pip_when_importable(monkeypatch):
    monkeypatch.setattr(importlib.util, 'find_spec', lambda name: object())
    cmd = Packages().install_command('numpy', '--quiet')
    assert cmd == [sys.executable, '-m', 'pip', 'install', 'numpy', '--quiet']


def test_uv_for_this_python_when_pip_is_missing(monkeypatch):
    import shutil
    monkeypatch.setattr(importlib.util, 'find_spec', lambda name: None)
    monkeypatch.setattr(shutil, 'which', lambda name: '/usr/local/bin/uv' if name == 'uv' else None)
    cmd = Packages().install_command('pytz')
    assert cmd == ['/usr/local/bin/uv', 'pip', 'install', '--python', sys.executable, 'pytz']


def test_ensurepip_last_and_a_clear_error(monkeypatch):
    import shutil
    import subprocess

    class R:
        returncode = 1
    monkeypatch.setattr(importlib.util, 'find_spec', lambda name: None)
    monkeypatch.setattr(shutil, 'which', lambda name: None)
    calls = []
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: calls.append(a[0]) or R())
    with pytest.raises(RuntimeError) as e:
        Packages().install_command('pytz')
    assert calls and calls[0][1:3] == ['-m', 'ensurepip']
    assert 'no pip' in str(e.value) and 'uv is not on the PATH' in str(e.value)
