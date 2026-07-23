"""
Tests for cmeta.utils.common query-matching helpers (matches_query / value_matches).

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

from cmeta.utils.common import matches_query, value_matches


# ---------------------------------------------------------------------------
# value_matches
# ---------------------------------------------------------------------------

def test_value_matches_scalar_equal():
    assert value_matches("x", "x") is True


def test_value_matches_scalar_not_equal():
    assert value_matches("x", "y") is False


def test_value_matches_list_subset():
    # query list must be a subset of the data list
    assert value_matches(["a", "b", "c"], ["a", "c"]) is True


def test_value_matches_list_not_subset():
    assert value_matches(["a", "b"], ["a", "z"]) is False


def test_value_matches_list_query_against_non_list_data():
    assert value_matches("a", ["a"]) is False


def test_value_matches_nested_dict():
    assert value_matches({"k": {"n": 1}}, {"k": {"n": 1}}) is True


def test_value_matches_dict_query_against_non_dict_data():
    assert value_matches("scalar", {"k": 1}) is False


# ---------------------------------------------------------------------------
# matches_query
# ---------------------------------------------------------------------------

def test_matches_query_all_keys_satisfied():
    assert matches_query({"a": 1, "b": 2}, {"a": 1}) is True


def test_matches_query_value_mismatch():
    assert matches_query({"a": 1}, {"a": 2}) is False


def test_matches_query_missing_key_fails():
    assert matches_query({"a": 1}, {"b": 1}) is False


def test_matches_query_empty_query_matches_anything():
    assert matches_query({"a": 1}, {}) is True


def test_matches_query_negation_absent_key_ok():
    # a '-' suffix negates: an absent key satisfies the negated query
    assert matches_query({"a": 1}, {"b-": 5}) is True


def test_matches_query_negation_present_but_different():
    assert matches_query({"a": 1}, {"a-": 2}) is True


def test_matches_query_negation_present_and_equal_fails():
    assert matches_query({"a": 1}, {"a-": 1}) is False


def test_matches_query_nested_dict():
    data = {"features": {"os": "linux", "arch": "x86"}}
    assert matches_query(data, {"features": {"os": "linux"}}) is True
    assert matches_query(data, {"features": {"os": "windows"}}) is False


def test_matches_query_list_subset():
    assert matches_query({"tags": ["a", "b", "c"]}, {"tags": ["a", "c"]}) is True
    assert matches_query({"tags": ["a", "b"]}, {"tags": ["a", "z"]}) is False


def test_matches_query_version_key_absent_with_match_empty_version():
    # a version key ('@'-prefixed) that is absent is tolerated when
    # match_empty_version is enabled
    assert matches_query({}, {"@version": "1.0"}, match_empty_version=True) is True
    assert matches_query({}, {"@version": "1.0"}, match_empty_version=False) is False
