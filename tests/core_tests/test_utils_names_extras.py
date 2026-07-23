"""
Tests for cmeta.utils.names helpers that aren't covered by the existing
parse_cmeta_name / _obj / _ref suites.

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import pytest

from cmeta.utils.names import (
    generate_cmeta_uid,
    is_valid_cmeta_uid,
    is_valid_cmeta_alias,
    is_valid_category_alias,
    parse_cmeta_name,
    parse_cmeta_obj,
    parse_cmeta_ref,
    parse_cmeta_ref_with_path,
    restore_cmeta_ref,
    get_sort_key_cmeta_obj_alias_or_uid,
)


# ---------------------------------------------------------------------------
# UID generation / validation
# ---------------------------------------------------------------------------

def test_generate_cmeta_uid_is_16_hex_chars():
    uid = generate_cmeta_uid()
    assert len(uid) == 16
    assert all(c in '0123456789abcdef' for c in uid)


def test_generate_cmeta_uid_uniqueness_across_batch():
    seen = {generate_cmeta_uid() for _ in range(100)}
    assert len(seen) == 100


@pytest.mark.parametrize("uid,ok", [
    ("f4f792ab40c7498f", True),
    ("F4F792AB40C7498F", True),          # case-insensitive
    ("f4f792ab40c7498",  False),          # 15 chars
    ("f4f792ab40c7498ff", False),         # 17 chars
    ("g4f792ab40c7498f", False),          # non-hex
    ("",                 False),
])
def test_is_valid_cmeta_uid(uid, ok):
    assert is_valid_cmeta_uid(uid) == ok


# ---------------------------------------------------------------------------
# Alias validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("alias", ['ok', 'ok-alias', 'ok_alias', 'ok.alias', 'A-Z-0-9'])
def test_is_valid_cmeta_alias_accepts(alias):
    r = is_valid_cmeta_alias(alias)
    assert r == {'return': 0}


@pytest.mark.parametrize("alias,fragment", [
    ('bad/alias', 'Invalid characters'),
    ('bad\\alias', 'Invalid characters'),
    ('bad*alias', 'Invalid characters'),
    (' padded ', 'leading/trailing spaces'),
])
def test_is_valid_cmeta_alias_rejects(alias, fragment):
    r = is_valid_cmeta_alias(alias)
    assert r['return'] == 1
    assert fragment in r['error']


@pytest.mark.parametrize("alias,ok", [
    ('lowercase', True),
    ('with-dashes', True),
    ('MixedCase', False),
    ('has space', False),
    ('.hidden',   False),
    ('trailing.', False),
    ('con',       False),      # Windows reserved
    ('lpt1',      False),
    ('nul',       False),
    ('con.txt',   False),      # reserved base name
])
def test_is_valid_category_alias(alias, ok):
    r = is_valid_category_alias(alias)
    if ok:
        assert r == {'return': 0}
    else:
        assert r['return'] == 1


# ---------------------------------------------------------------------------
# UID takes precedence when both alias and UID are present
# ---------------------------------------------------------------------------

def test_parse_name_extracts_both_alias_and_uid():
    r = parse_cmeta_name('myalias,f4f792ab40c7498f')
    assert r['return'] == 0
    assert r['name'] == {'alias': 'myalias', 'uid': 'f4f792ab40c7498f'}


def test_parse_name_lowercases_uid():
    r = parse_cmeta_name('myalias,F4F792AB40C7498F')
    assert r['name']['uid'] == 'f4f792ab40c7498f'


def test_alias_that_looks_like_uid_is_rejected():
    r = parse_cmeta_name('f4f792ab40c7498f,f4f792ab40c7498f')
    assert r['return'] == 1
    assert "alias can't be a UID" in r['error']


# ---------------------------------------------------------------------------
# parse_cmeta_obj — edge cases
# ---------------------------------------------------------------------------

def test_parse_cmeta_obj_double_colon_is_error():
    r = parse_cmeta_obj('cat::art')
    assert r['return'] == 1
    assert 'must not have ::' in r['error']


def test_parse_cmeta_obj_pass_through_dict():
    d = {'alias': 'a', 'uid': None}
    r = parse_cmeta_obj(d)
    assert r == {'return': 0, 'obj_parts': d}


# ---------------------------------------------------------------------------
# parse_cmeta_ref
# ---------------------------------------------------------------------------

def test_parse_cmeta_ref_missing_separator_errors_by_default():
    r = parse_cmeta_ref('artname')
    assert r['return'] == 1
    assert 'must have ::' in r['error']


def test_parse_cmeta_ref_do_not_fail_if_no_sep():
    r = parse_cmeta_ref('artname', do_not_fail_if_no_sep=True)
    assert r['return'] == 0
    # No category info, just artifact
    assert r['ref_parts'] == {'artifact_alias': 'artname'}


def test_parse_cmeta_ref_none_yields_empty():
    r = parse_cmeta_ref(None)
    assert r == {'return': 0, 'ref_parts': {}}


def test_restore_cmeta_ref_errors_when_artifact_present_but_no_category():
    r = restore_cmeta_ref({'artifact_alias': 'a'})
    assert r['return'] == 1


def test_restore_cmeta_ref_category_only_produces_trailing_sep():
    r = restore_cmeta_ref({'category_alias': 'cat', 'category_uid': 'f4f792ab40c7498f'})
    assert r['return'] == 0
    assert r['ref'] == 'cat,f4f792ab40c7498f::'


# ---------------------------------------------------------------------------
# parse_cmeta_ref_with_path
# ---------------------------------------------------------------------------

def test_parse_cmeta_ref_with_path_extracts_trailing_path():
    r = parse_cmeta_ref_with_path('category,dd9ea50e7f76467f::repo,f4f792ab40c7498f/sub/file.txt')
    assert r['return'] == 0
    assert r['ref_parts']['category_alias'] == 'category'
    assert r['ref_parts']['artifact_alias'] == 'repo'
    assert r['path'] == 'sub/file.txt'


def test_parse_cmeta_ref_with_path_without_extra_path():
    r = parse_cmeta_ref_with_path('cat::art')
    assert r['return'] == 0
    assert 'path' not in r


def test_parse_cmeta_ref_with_path_missing_sep_errors():
    r = parse_cmeta_ref_with_path('artonly')
    assert r['return'] == 1


# ---------------------------------------------------------------------------
# get_sort_key_cmeta_obj_alias_or_uid
# ---------------------------------------------------------------------------

def test_sort_key_prefers_lowercase_alias():
    item = {'cmeta_ref_parts': {'artifact_alias_lowercase': 'foo',
                                'artifact_alias': 'FOO',
                                'artifact_uid': 'abcd1234abcd1234'}}
    assert get_sort_key_cmeta_obj_alias_or_uid(item) == 'foo'


def test_sort_key_falls_back_to_alias_then_uid():
    a = {'cmeta_ref_parts': {'artifact_alias': 'Foo'}}
    b = {'cmeta_ref_parts': {'artifact_uid': 'abcd1234abcd1234'}}
    assert get_sort_key_cmeta_obj_alias_or_uid(a) == 'Foo'
    assert get_sort_key_cmeta_obj_alias_or_uid(b) == 'abcd1234abcd1234'
