"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

Tests for utils.sys.prefer_speed (2026-11-04): on Windows the process opts out of the power throttling that made
a server's worker answer ~3x slower after a pause; nothing happens elsewhere, nor when CMETA_POWER_THROTTLING=yes
asks to keep the OS policy; the async core's workers and loop process call it.
"""

import os

from cmeta.utils import sys as sys_utils


def test_prefer_speed_applies_on_windows_only(monkeypatch):
    monkeypatch.delenv('CMETA_POWER_THROTTLING', raising=False)
    applied = sys_utils.prefer_speed()
    assert applied is (os.name == 'nt')
    # again: idempotent, the same answer
    assert sys_utils.prefer_speed() is applied


def test_the_os_policy_is_kept_on_request(monkeypatch):
    monkeypatch.setenv('CMETA_POWER_THROTTLING', 'yes')
    assert sys_utils.prefer_speed() is False


def test_the_async_core_asks_for_speed(monkeypatch, tmp_path):
    import cmeta.core_async as core_async

    calls = []
    monkeypatch.setattr(core_async.sys_utils, 'prefer_speed', lambda: calls.append('called') or True)
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))

    # a worker process: at its first request (the module keeps one CMeta per process)
    monkeypatch.setattr(core_async, '_cmeta_instance', None)
    core_async._get_cmeta(home=str(tmp_path))
    assert calls == ['called']
    core_async._get_cmeta(home=str(tmp_path))
    assert calls == ['called']              # once per process

    # the process of the event loop: when the pool is made
    cm = core_async.CMetaAsync(max_workers=1, home=str(tmp_path))
    try:
        assert calls == ['called', 'called']
    finally:
        cm.shutdown()
