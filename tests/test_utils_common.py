"""
Tests for cmeta.utils.common helpers.

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import pytest

from cmeta.utils.common import (
    deep_merge, deep_remove,
    normalize_tags,
    compare_versions, sort_versions,
    flatten_dict, smart_get, smart_set, smart_merge,
    split_clean, split, first_digit_pos,
    check_params,
    _error,
)


# ---------------------------------------------------------------------------
# _error
# ---------------------------------------------------------------------------

def test_error_returns_dict_with_return_and_error():
    r = _error("boom", 3)
    assert r == {'return': 3, 'error': 'boom'}


def test_error_appends_exception_string():
    r = _error("boom", 1, exception=ValueError("bad"))
    assert r['return'] == 1
    assert 'boom' in r['error'] and 'bad' in r['error']


def test_error_extra_is_merged_into_return_dict():
    r = _error("boom", 2, extra={'context': {'a': 1}})
    assert r['context'] == {'a': 1}


def test_error_fail_on_error_raises():
    with pytest.raises(RuntimeError):
        _error("boom", 1, fail_on_error=True)


def test_error_16_is_soft_even_with_fail_on_error():
    r = _error("not found", 16, fail_on_error=True)
    assert r['return'] == 16


def test_error_16_becomes_hard_when_fail_on_16():
    with pytest.raises(RuntimeError):
        _error("not found", 16, fail_on_error=True, fail_on_16=True)


# ---------------------------------------------------------------------------
# check_params
# ---------------------------------------------------------------------------

def test_check_params_accepts_known_keys():
    r = check_params({'a': 1, 'b': 2}, ['a', 'b', 'c'])
    assert r == {'return': 0}


def test_check_params_rejects_unknown_key():
    r = check_params({'a': 1, 'x': 2}, ['a', 'b'])
    assert r['return'] == 1
    assert 'unknown input parameter "x"' in r['error']


# ---------------------------------------------------------------------------
# deep_merge
# ---------------------------------------------------------------------------

def test_deep_merge_scalar_overwrites():
    target = {'a': 1, 'b': 2}
    out = deep_merge(target, {'a': 99})
    assert out == {'a': 99, 'b': 2}


def test_deep_merge_recurses_into_dicts():
    target = {'a': {'x': 1, 'y': 2}}
    out = deep_merge(target, {'a': {'y': 20, 'z': 30}})
    assert out == {'a': {'x': 1, 'y': 20, 'z': 30}}


def test_deep_merge_replaces_lists_by_default():
    target = {'tags': ['a', 'b']}
    out = deep_merge(target, {'tags': ['c']})
    assert out == {'tags': ['c']}


def test_deep_merge_append_lists():
    target = {'tags': ['a', 'b']}
    out = deep_merge(target, {'tags': ['c']}, append_lists=True)
    assert out['tags'] == ['a', 'b', 'c']


def test_deep_merge_append_lists_dedup_by_default():
    target = {'tags': ['a', 'b']}
    out = deep_merge(target, {'tags': ['b', 'c']}, append_lists=True)
    assert out['tags'] == ['a', 'b', 'c']


def test_deep_merge_prepend_lists():
    target = {'tags': ['a', 'b']}
    out = deep_merge(target, {'tags': ['x', 'y']}, append_lists=True, prepend_lists=True)
    # x, y prepended in order
    assert out['tags'] == ['x', 'y', 'a', 'b']


def test_deep_merge_ignore_root_keys():
    out = deep_merge({'artifact': 'orig', 'a': 1}, {'artifact': 'new', 'a': 2},
                     ignore_root_keys=['artifact'])
    assert out == {'artifact': 'orig', 'a': 2}


def test_deep_merge_remove_if_none():
    out = deep_merge({'a': 1, 'b': 2, 'c': 3},
                     {'a': None, 'b': [], 'd': 4},
                     remove_if_none=True)
    assert 'a' not in out and 'b' not in out
    assert out == {'c': 3, 'd': 4}


# ---------------------------------------------------------------------------
# deep_remove
# ---------------------------------------------------------------------------

def test_deep_remove_scalar_key():
    out = deep_remove({'a': 1, 'b': 2}, {'a': None})
    assert out == {'b': 2}


def test_deep_remove_nested_key():
    out = deep_remove({'a': {'x': 1, 'y': 2}, 'b': 3}, {'a': {'x': None}})
    assert out == {'a': {'y': 2}, 'b': 3}


def test_deep_remove_list_items():
    out = deep_remove({'tags': ['a', 'b', 'c']}, {'tags': ['b']})
    assert out == {'tags': ['a', 'c']}


def test_deep_remove_prunes_empty_dict():
    out = deep_remove({'a': {'x': 1}, 'b': 2}, {'a': {'x': None}})
    assert 'a' not in out
    assert out == {'b': 2}


def test_deep_remove_ignores_missing_keys():
    out = deep_remove({'a': 1}, {'b': None, 'c': {'x': None}})
    assert out == {'a': 1}


# ---------------------------------------------------------------------------
# normalize_tags
# ---------------------------------------------------------------------------

def test_normalize_tags_from_string():
    r = normalize_tags('  a , b,c ')
    assert r == {'return': 0, 'tags': ['a', 'b', 'c']}


def test_normalize_tags_from_list():
    r = normalize_tags([' a ', 'b'])
    assert r == {'return': 0, 'tags': ['a', 'b']}


def test_normalize_tags_bad_type():
    r = normalize_tags(123)
    assert r['return'] == 1
    assert 'tags should be string or list' in r['error']


# ---------------------------------------------------------------------------
# compare_versions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("a,b,expected", [
    ("1.0.0",   "1.0.0",   '='),
    ("1.0.1",   "1.0.0",   '>'),
    ("1.0.0",   "1.0.1",   '<'),
    ("1.2",     "1.2.0",   '='),
    ("1.10",    "1.2",     '>'),
    ("1.0.0",   "1.0.0-dev", '>'),  # bare > suffixed
    ("1.0.0-a", "1.0.0-b", '<'),
])
def test_compare_versions(a, b, expected):
    r = compare_versions(a, b)
    assert r == {'return': 0, 'comparison': expected}


def test_compare_versions_invalid():
    r = compare_versions("not-a-version", "1.0")
    assert r['return'] == 1
    assert 'Error comparing versions' in r['error']


# ---------------------------------------------------------------------------
# sort_versions
# ---------------------------------------------------------------------------

def test_sort_versions_asc():
    assert sort_versions(['1.10', '1.2', '1.9']) == ['1.2', '1.9', '1.10']


def test_sort_versions_desc():
    assert sort_versions(['1.2', '1.9', '1.10'], reverse=True) == ['1.10', '1.9', '1.2']


def test_sort_versions_strips_leading_v():
    # 'v1.2' should sort like '1.2'
    out = sort_versions(['v1.2', '1.9', 'v1.10'])
    assert out == ['v1.2', '1.9', 'v1.10']


# ---------------------------------------------------------------------------
# flatten_dict
# ---------------------------------------------------------------------------

def test_flatten_dict_default_sep():
    d = {'a': {'b': {'c': 1}, 'd': 2}, 'e': 3}
    assert flatten_dict(d) == {'a.b.c': 1, 'a.d': 2, 'e': 3}


def test_flatten_dict_custom_sep():
    assert flatten_dict({'a': {'b': 1}}, sep='/') == {'a/b': 1}


# ---------------------------------------------------------------------------
# smart_get / smart_set / smart_merge
# ---------------------------------------------------------------------------

def test_smart_get_deep():
    assert smart_get({'a': {'b': {'c': 42}}}, 'a.b.c') == 42


def test_smart_get_missing_returns_default():
    assert smart_get({'a': 1}, 'a.b.c', default='DEFAULT') == 'DEFAULT'


def test_smart_get_shallow():
    assert smart_get({'a': {'b': 1}}, 'a') == {'b': 1}


def test_smart_set_creates_missing_dicts():
    d = {}
    smart_set(d, 'a.b.c', 5)
    assert d == {'a': {'b': {'c': 5}}}


def test_smart_set_raises_on_non_dict():
    d = {'a': 1}
    with pytest.raises(TypeError):
        smart_set(d, 'a.b', 2)


def test_smart_merge_basic_dict_recursion():
    out = smart_merge({'a': {'x': 1}}, {'a': {'y': 2}})
    assert out == {'a': {'x': 1, 'y': 2}}


def test_smart_merge_appends_to_list_by_default():
    out = smart_merge({'tags': ['a']}, {'tags': 'b'})
    assert out['tags'] == ['a', 'b']


def test_smart_merge_replace_prefix():
    out = smart_merge({'a': {'x': 1, 'y': 2}}, {'=a': {'x': 9}})
    assert out == {'a': {'x': 9}}


# ---------------------------------------------------------------------------
# split_clean / split / first_digit_pos
# ---------------------------------------------------------------------------

def test_split_clean_strips_and_dedups_empty():
    assert split_clean(' a , , b ,c') == ['a', 'b', 'c']


def test_split_clean_empty_string():
    assert split_clean('') == []


def test_split_lowercases():
    assert split(' A , B ') == ['a', 'b']


def test_first_digit_pos_found():
    assert first_digit_pos('abc42') == 3


def test_first_digit_pos_not_found():
    assert first_digit_pos('abcdef') == -1
