"""
Tests for cmeta.utils.cli.parse_cmd (CLI argument parser).

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import json
import pytest

from cmeta.utils.cli import parse_cmd


def _params(argv):
    r = parse_cmd(argv)
    assert r['return'] == 0, r
    return r['params']


# ---------------------------------------------------------------------------
# Positional args
# ---------------------------------------------------------------------------

def test_positional_args_go_into_args_list():
    p = _params(['category', 'find', 'my-thing'])
    assert p['args'] == ['category', 'find', 'my-thing']


def test_empty_argv_yields_no_args():
    p = _params([])
    assert p == {}


def test_none_argv_yields_no_args():
    r = parse_cmd(None)
    assert r == {'return': 0, 'params': {}}


# ---------------------------------------------------------------------------
# Boolean flags
# ---------------------------------------------------------------------------

def test_double_dash_bool_flag():
    assert _params(['--verbose']) == {'verbose': True}


def test_single_dash_bool_flag():
    assert _params(['-v']) == {'v': True}


def test_trailing_dash_makes_false():
    assert _params(['--verbose-']) == {'verbose': False}


def test_no_prefix_makes_false():
    assert _params(['--no-verbose']) == {'verbose': False}


# ---------------------------------------------------------------------------
# Key=value forms
# ---------------------------------------------------------------------------

def test_double_dash_key_value():
    assert _params(['--log-level=DEBUG']) == {'log_level': 'DEBUG'}


def test_hyphens_in_key_become_underscores():
    # split_flag is called with fix_keys=True from parse_cmd
    assert _params(['--fail-on-error']) == {'fail_on_error': True}


def test_bare_key_value_treated_as_flag():
    assert _params(['category=repo']) == {'category': 'repo'}


def test_positional_before_and_after_flag():
    p = _params(['category', '--verbose', 'find', 'x'])
    assert p['verbose'] is True
    assert p['args'] == ['category', 'find', 'x']


# ---------------------------------------------------------------------------
# Nested keys with dots
# ---------------------------------------------------------------------------

def test_nested_key_creates_nested_dict():
    p = _params(['--meta.description=hi'])
    assert p == {'meta': {'description': 'hi'}}


def test_multiple_nested_keys_merge():
    p = _params(['--meta.a=1', '--meta.b=2', '--meta.c.d=3'])
    assert p == {'meta': {'a': '1', 'b': '2', 'c': {'d': '3'}}}


# ---------------------------------------------------------------------------
# Repeated flags → list
# ---------------------------------------------------------------------------

def test_repeated_flag_last_wins():
    # Plain `--k=v` repeats overwrite — last value wins.
    p = _params(['--tags=a', '--tags=b', '--tags=c'])
    assert p['tags'] == 'c'


def test_trailing_comma_key_creates_list_from_csv_value():
    # `--key,=v1,v2,v3` — trailing comma on the key requests list-splitting.
    p = _params(['--tags,=a,b,c'])
    assert p['tags'] == ['a', 'b', 'c']


def test_trailing_comma_key_bareword_wraps_true_in_list():
    # `--tags,` with no `=` is a bool flag first, then wrapped as a single-item list.
    p = _params(['--tags,'])
    assert p['tags'] == [True]


def test_trailing_comma_key_empty_value_yields_empty_list():
    p = _params(['--tags,='])
    assert p['tags'] == []


# ---------------------------------------------------------------------------
# `--` separator
# ---------------------------------------------------------------------------

def test_double_dash_separator_captures_unparsed():
    p = _params(['run', '--verbose', '--', '--not-a-flag', 'passthrough'])
    assert p['verbose'] is True
    assert p['args'] == ['run']
    assert p['unparsed'] == ['--not-a-flag', 'passthrough']


# ---------------------------------------------------------------------------
# Triple-dash prefix is rejected
# ---------------------------------------------------------------------------

def test_triple_dash_rejected():
    r = parse_cmd(['---bogus'])
    assert r['return'] == 1
    assert 'unknown prefix "---"' in r['error']


# ---------------------------------------------------------------------------
# @file inclusion
# ---------------------------------------------------------------------------

def test_at_file_inclusion_merges_json(tmp_path):
    p = tmp_path / "params.json"
    p.write_text(json.dumps({'category': 'repo', 'command': 'list', 'verbose': True}))
    parsed = _params(['@' + str(p)])
    assert parsed['category'] == 'repo'
    assert parsed['command'] == 'list'
    assert parsed['verbose'] is True


def test_at_file_inclusion_merges_yaml(tmp_path):
    p = tmp_path / "params.yaml"
    p.write_text("meta:\n  a: 1\n  b: 2\n")
    parsed = _params(['@' + str(p)])
    assert parsed == {'meta': {'a': 1, 'b': 2}}


def test_at_at_file_inclusion_deletes_file_after_read(tmp_path):
    p = tmp_path / "once.json"
    p.write_text('{"x": 1}')
    parsed = _params(['@@' + str(p)])
    assert parsed == {'x': 1}
    assert not p.exists()


def test_at_file_missing_returns_error(tmp_path):
    r = parse_cmd(['@' + str(tmp_path / 'nope.json')])
    assert r['return'] > 0


# ---------------------------------------------------------------------------
# String vs list argv
# ---------------------------------------------------------------------------

def test_string_argv_is_shlex_split():
    r = parse_cmd('category find --verbose')
    assert r['return'] == 0
    assert r['params']['args'] == ['category', 'find']
    assert r['params']['verbose'] is True


# ---------------------------------------------------------------------------
# ctx-through-CLI (design intent — parse-only check)
# ---------------------------------------------------------------------------

def test_ctx_nested_flags_land_under_ctx_dict():
    p = _params(['--ctx.agent.session=sess-42',
                 '--ctx.agent.budget_tokens=20000'])
    assert p == {'ctx': {'agent': {'session': 'sess-42',
                                   'budget_tokens': '20000'}}}
