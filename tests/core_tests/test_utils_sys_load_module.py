"""
Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.

utils.sys.load_module in a process that lives on (a cserver, a long script) while the files change: a module
loaded again re-reads the helper modules it imports from its folder ("from . import upgrade"), and a changed
helper loads the module again (its helpers are checked at most every HELPER_CHECK_SECONDS, its own file on
every call). Before 0.37.1 the module was re-read with the helpers of before: a cserver failed with "module
'task_c36be4b9314a45e0.setup.upgrade' has no attribute 'newest_allowed'" after a task and its helper were
updated (2026-10-14), and a change to a helper alone was never seen.
"""

import os
import time

from cmeta.utils import sys as cm_sys


def write(path, text, stamp):
    """A file with its text and a modification time of its own (a write in the same tick keeps the time)."""
    with open(path, 'w', encoding = 'utf-8') as f:
        f.write(text)
    os.utime(path, (stamp, stamp))


def task(tmp_path, name):
    """A task folder <tmp>/<name>-cat/<name>/ with api_v1.py and its helper upgrade.py."""
    folder = tmp_path / (name + '-cat') / name
    folder.mkdir(parents = True)
    return str(folder / 'api_v1.py'), str(folder / 'upgrade.py')


def load(path, cache):
    r = cm_sys.load_module(path, cache)
    assert r['return'] == 0, r.get('error')
    return r['cache']['python_module']


def test_a_module_and_its_helper_changed_together(tmp_path):
    """The failure of 2026-10-14: a new function in the helper, used by the new module."""
    api, helper = task(tmp_path, 'reload_together')
    t = time.time() - 100
    write(helper, 'def f(): return 1\n', t)
    write(api, 'from . import upgrade\nf = upgrade.f\n', t)

    cache = {}
    assert load(api, cache).f() == 1

    write(helper, 'def f(): return 1\ndef newest_allowed(): return 2\n', t + 10)
    write(api, 'from . import upgrade\nf = upgrade.f\nnewest_allowed = upgrade.newest_allowed\n', t + 10)

    assert load(api, cache).newest_allowed() == 2


def test_a_changed_helper_loads_the_module_again(tmp_path, monkeypatch):
    monkeypatch.setattr(cm_sys, 'HELPER_CHECK_SECONDS', 0)
    api, helper = task(tmp_path, 'reload_helper_only')
    t = time.time() - 100
    write(helper, 'X = 1\n', t)
    write(api, 'from . import upgrade\nX = upgrade.X\n', t)

    cache = {}
    first = load(api, cache)
    assert first.X == 1
    assert load(api, cache) is first                 # nothing changed: the same module

    write(helper, 'X = 2\n', t + 10)                  # only the helper
    second = load(api, cache)
    assert second is not first and second.X == 2
    assert load(api, cache) is second


def test_a_helper_imported_inside_a_function_is_watched_too(tmp_path, monkeypatch):
    monkeypatch.setattr(cm_sys, 'HELPER_CHECK_SECONDS', 0)
    api, helper = task(tmp_path, 'reload_lazy')
    t = time.time() - 100
    write(helper, 'X = 1\n', t)
    write(api, 'def x():\n    from . import upgrade\n    return upgrade.X\n', t)

    cache = {}
    first = load(api, cache)
    assert first.x() == 1                            # imported now, after the module was loaded
    assert load(api, cache) is first                 # seen as it is: no reload

    write(helper, 'X = 3\n', t + 10)
    second = load(api, cache)
    assert second is not first and second.x() == 3


def test_a_removed_helper_loads_the_module_again(tmp_path, monkeypatch):
    monkeypatch.setattr(cm_sys, 'HELPER_CHECK_SECONDS', 0)
    api, helper = task(tmp_path, 'reload_removed')
    t = time.time() - 100
    write(helper, 'X = 1\n', t)
    write(api, 'from . import upgrade\n', t)

    cache = {}
    load(api, cache)
    os.remove(helper)

    r = cm_sys.load_module(api, cache)               # the module still imports it: an error, not a stale module
    assert r['return'] > 0 and 'upgrade' in str(r.get('error')) + str(r.get('exception', ''))


def test_helpers_are_checked_at_most_every_interval(tmp_path, monkeypatch):
    """Within the interval a changed helper waits; a changed module is loaded at once, with its new helpers."""
    monkeypatch.setattr(cm_sys, 'HELPER_CHECK_SECONDS', 3600)
    api, helper = task(tmp_path, 'reload_interval')
    t = time.time() - 100
    write(helper, 'X = 1\n', t)
    write(api, 'from . import upgrade\nX = upgrade.X\n', t)

    cache = {}
    first = load(api, cache)
    write(helper, 'X = 2\n', t + 10)
    assert load(api, cache) is first                 # not checked yet

    write(api, 'from . import upgrade\nX = upgrade.X\nY = 1\n', t + 10)
    second = load(api, cache)
    assert second is not first and second.X == 2 and second.Y == 1
