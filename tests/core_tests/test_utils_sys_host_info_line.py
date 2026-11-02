"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

The memory note of a console (2026-11-02): get_min_host_info(short=True) prints one stamped line (with the pid) and
returns it as 'line' next to the block 'string'; a CMeta made with print_host_info prints it for top-level access
calls only - the first of the process, then after the interval or when the memory moved - and with 0 for every
top-level call, never for a nested one.
"""

import re

from cmeta import CMeta
from cmeta.utils import sys as cmeta_sys

LINE = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} memory: \S+ \S+ used by pid \d+, \S+ \S+ free of \S+ \S+ \(\d+\.\d{3} s\)$')


def test_short_prints_one_stamped_line_and_the_block_stays_in_the_result(capsys):
    r = cmeta_sys.get_min_host_info(only_memory=True, con=True, short=True)
    assert r['return'] == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1 and LINE.match(out[0]), out
    assert r['line'] == out[0]
    assert 'Host total memory:' in r['string'] and '=' * 10 not in r['string']
    # the block as before when short is not asked
    r = cmeta_sys.get_min_host_info(only_memory=True, con=True, line=80)
    out = capsys.readouterr().out
    assert out.startswith('=' * 80) and 'Host free memory:' in out and 'Memory used by current process:' in out


def _engine(tmp_path, monkeypatch, value):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    return CMeta(home=str(tmp_path), print_host_info=value)


def _lines(capsys):
    return [l for l in capsys.readouterr().out.splitlines() if l.strip()]


def test_an_engine_prints_the_first_top_level_call_then_waits_for_the_interval(tmp_path, monkeypatch, capsys):
    cm = _engine(tmp_path, monkeypatch, True)
    capsys.readouterr()
    for _ in range(3):
        r = cm.access({'category': 'category', 'command': 'find', 'arg1': 'category', 'con': False})
        assert r['return'] == 0
    lines = _lines(capsys)
    assert len(lines) == 1 and LINE.match(lines[0]), lines          # the first call of the process, not the next two
    # the interval passed: one more line
    cm._host_memory_last = (cm._host_memory_last[0] - 61, cm._host_memory_last[1])
    cm.access({'category': 'category', 'command': 'find', 'arg1': 'category', 'con': False})
    assert len(_lines(capsys)) == 1


def test_zero_prints_every_top_level_call_but_never_a_nested_one(tmp_path, monkeypatch, capsys):
    cm = _engine(tmp_path, monkeypatch, 0)
    capsys.readouterr()
    cm.access({'category': 'category', 'command': 'find', 'arg1': 'category', 'con': False})
    # find_by_cid makes nested access calls (the categories, their finds): still one line
    r = cm.access({'category': 'utils', 'command': 'find_by_cid', 'arg1': 'category::category', 'con': False})
    assert r['return'] == 0
    lines = _lines(capsys)
    assert len(lines) == 2 and all(LINE.match(l) for l in lines), lines
