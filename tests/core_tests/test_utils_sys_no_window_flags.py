"""
Tests for the creation flag that keeps a captured child from opening a console window on Windows when this process
has no console of its own: 0 elsewhere, 0 with a console, CREATE_NO_WINDOW without one.

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import subprocess
import sys

import pytest

from cmeta.utils import sys as usys


def test_zero_off_windows(monkeypatch):
    monkeypatch.setattr(os, 'name', 'posix')
    assert usys.no_window_flags() == 0


@pytest.mark.skipif(os.name != 'nt', reason='Windows only')
def test_follows_the_console_of_this_process(monkeypatch):
    import ctypes
    monkeypatch.setattr(ctypes.windll.kernel32, 'GetConsoleWindow', lambda: 1234)
    assert usys.no_window_flags() == 0
    monkeypatch.setattr(ctypes.windll.kernel32, 'GetConsoleWindow', lambda: 0)
    assert usys.no_window_flags() == subprocess.CREATE_NO_WINDOW


@pytest.mark.skipif(os.name != 'nt', reason='Windows only')
def test_a_captured_child_keeps_its_output_under_the_flag():
    r = subprocess.run([sys.executable, '-c', 'print("captured")'], capture_output=True, text=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    assert r.stdout.strip() == 'captured'
