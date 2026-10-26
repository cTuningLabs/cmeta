"""
A guard for a rule of the engine: a duration, a timeout, a deadline or a retry is measured on the monotonic
clock (`time.monotonic()`, `time.perf_counter()`), never on the wall clock (`time.time()`). The wall clock is
set while code runs - by NTP, by a virtual machine's sync with its host: on one machine WSL2 was seen stepping
its clock by -3.3 s and +6.2 s every 30 s - and a wait measured on it ends too early, too late, or not at all
(a read that was never tried returned success with no data; a timed-out command was reported as failed).

The test parses every Python file of the package, the categories of the internal repository included, and
lists each `time.time()` that is subtracted from, added to or compared with something. The only such uses that
are right compare the wall clock with a time WRITTEN somewhere - the time in a soft lock's line, the time of a
file - and those are named here; everything else is a duration on the wrong clock.

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import ast
import pathlib

import cmeta

PACKAGE = pathlib.Path(cmeta.__file__).parent

# (the file under the package, a piece of the source line): the wall clock against a written time
ALLOWED = (
    ('utils/files.py', 'age = time.time() - float(words[2])'),   # a soft lock line: the time its holder wrote
    ('utils/files.py', 'time.time() - mtime'),                   # the time the file system gave a lock file
    ('internal-repo/app/cserver/src/app.py', 'return time.time() > float(written or 0) + plus'),   # a login's end, a code's expiry: written in the cookie or the codes file, read by another worker
    ('internal-repo/app/cserver/src/app.py', 'return time.time() + float(seconds)'),               # the time written down for that
)


def is_wall_clock_call(node):
    """`time.time()` or a bare `time()` imported from the time module."""
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    if isinstance(f, ast.Attribute):
        return f.attr == 'time' and isinstance(f.value, ast.Name) and f.value.id == 'time'
    return isinstance(f, ast.Name) and f.id == 'time'


def wall_clock_arithmetic():
    """(file, line number, source line) of every subtraction, addition or comparison with the wall clock."""
    found = {}
    for path in sorted(PACKAGE.rglob('*.py')):
        if 'tests' in path.parts:
            continue
        source = path.read_text(encoding='utf-8', errors='replace')
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        lines = source.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.BinOp, ast.Compare)):
                continue
            if isinstance(node, ast.BinOp) and not isinstance(node.op, (ast.Sub, ast.Add)):
                continue
            if any(is_wall_clock_call(n) for n in ast.walk(node)):
                key = (path.relative_to(PACKAGE).as_posix(), node.lineno)
                found[key] = lines[node.lineno - 1].strip()
    return found


def test_durations_are_measured_on_the_monotonic_clock():
    found = wall_clock_arithmetic()

    wrong = []
    seen_allowed = set()
    for (file, lineno), line in sorted(found.items()):
        ok = False
        for allowed_file, piece in ALLOWED:
            if file == allowed_file and piece in line:
                ok = True
                seen_allowed.add((allowed_file, piece))
        if not ok:
            wrong.append(f'{file}:{lineno}: {line}')

    assert not wrong, ('a duration, deadline or retry measured on the wall clock (use time.monotonic() or '
                       'time.perf_counter(); a timestamp that is written down may stay):\n  ' + '\n  '.join(wrong))

    # The list above must not go stale: every allowed place is still there
    stale = [f'{f}: {p}' for f, p in ALLOWED if (f, p) not in seen_allowed]
    assert not stale, 'ALLOWED names a place that is gone - remove it:\n  ' + '\n  '.join(stale)
