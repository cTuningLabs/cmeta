"""
Tests of a command run with a timeout (`cmeta.utils.sys.run(timeout=...)`): a command that runs past it is
stopped together with every process it started - its process group on Linux and macOS (SIGTERM, then SIGKILL
for whatever is still there after a short grace), its Job Object on Windows - and the call returns soon after
the timeout, whether its output is captured or not. A child that ignores SIGTERM is stopped as well: before,
it went on running after the call had returned (and kept a captured call waiting for it to end).

The commands are small Python scripts: a parent that starts a child, and the child that writes a file when it
was not stopped in time. The cases run at once, each from its own thread (as commands are run from the
threads of a server), so that the wait for the children's end is paid once.

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import sys
import threading
import time

from cmeta.utils import sys as usys

PY = f'"{sys.executable}"'

CHILD_SECONDS = 12

# Well before the children's own end - and room for a system that stops for a few seconds now and then (WSL2
# on a USB drive: ~3 s pauses seen): normally the timeout and the grace, 3 s
RETURN_WITHIN = 9

CHILD = '''import os, signal, time
if {ignore}:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
open(r'{started}', 'w').write(str(os.getpid()))
time.sleep({seconds})
open(r'{marker}', 'w').write('x')
'''


def command(folder, ignore):
    """A parent that starts a child and waits for it; returns (the command, the started file, the marker)."""
    started = folder / 'child-started.txt'
    marker = folder / 'child-survived.txt'

    child = folder / 'child.py'
    child.write_text(CHILD.format(ignore=ignore, started=started, seconds=CHILD_SECONDS, marker=marker))

    parent = folder / 'parent.py'
    parent.write_text(f"import subprocess, sys\nsubprocess.run([sys.executable, r'{child}'])\n")

    return f'{PY} "{parent}"', started, marker


def test_a_timed_out_command_is_stopped_with_its_children(tmp_path, monkeypatch):
    monkeypatch.setattr(usys, 'RUN_STOP_GRACE_SECONDS', 1, raising=False)    # (not there before the grace existed)

    # A plain child and, on Linux and macOS, one that ignores SIGTERM - each with its output captured or not
    cases = [(capture, ignore) for capture in (False, True) for ignore in (False, True) if not (ignore and os.name == 'nt')]
    results = {}

    def one(capture, ignore):
        folder = tmp_path / f'{"captured" if capture else "console"}-{"ignoring-sigterm" if ignore else "plain"}'
        folder.mkdir()
        cmd, started, marker = command(folder, ignore)

        t0 = time.monotonic()
        r = usys.run(cmd, timeout=2, capture_output=capture)
        results[(capture, ignore)] = (r, time.monotonic() - t0, started, marker)

    t0 = time.monotonic()
    threads = [threading.Thread(target=one, args=case) for case in cases]
    for t in threads:
        t.start()
    for t in threads:
        t.join(120)

    assert set(results) == set(cases), results

    for case, (r, elapsed, started, marker) in results.items():
        assert r['return'] == 0 and r['returncode'] == -1 and r.get('timed_out') is True, (case, r)
        assert started.exists(), (case, 'the child had not started')
        assert elapsed < RETURN_WITHIN, (case, elapsed)

    # The children would have written their markers CHILD_SECONDS after they started: wait past that
    time.sleep(max(0.0, CHILD_SECONDS + 2 - (time.monotonic() - t0)))
    for case, (r, elapsed, started, marker) in results.items():
        assert not marker.exists(), (case, 'a child of the timed-out command was not stopped')


def test_timed_out_is_said_only_for_a_timeout(tmp_path):
    """'timed_out' tells a timeout from the other ways to get the return code -1 (a command that cannot be
    started; SIGHUP on Linux and macOS): False for a command that ends in time, absent without a timeout."""
    quick = f'{PY} -c "print(1)"'

    r = usys.run(quick, timeout=30, capture_output=True)
    assert r['return'] == 0 and r['returncode'] == 0 and r['timed_out'] is False, r

    r = usys.run(quick, capture_output=True)
    assert r['return'] == 0 and r['returncode'] == 0 and 'timed_out' not in r, r

    failing = f'{PY} -c "import sys; sys.exit(3)"'
    r = usys.run(failing, timeout=30, capture_output=True)
    assert r['returncode'] == 3 and r['timed_out'] is False, r
