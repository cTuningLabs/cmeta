"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

The memory note of a console (2026-11-02): get_min_host_info(short=True) prints one stamped line and returns it as
'line' next to the block 'string'; a CMeta made with print_host_info prints that one line per access call.
"""

import re

from cmeta import CMeta
from cmeta.utils import sys as cmeta_sys

LINE = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} memory: \S+ \S+ used, \S+ \S+ free of \S+ \S+ \(\d+\.\d{3} s\)$')


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


def test_an_engine_with_print_host_info_prints_one_line_per_call(tmp_path, monkeypatch, capsys):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    cm = CMeta(home=str(tmp_path), print_host_info=True)
    capsys.readouterr()
    r = cm.access({'category': 'category', 'command': 'find', 'arg1': 'category', 'con': False})
    assert r['return'] == 0
    lines = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
    assert lines and all(LINE.match(l) for l in lines), lines
    assert not any(l.startswith('=' * 20) for l in lines)
