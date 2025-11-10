"""
cMeta tests

cMeta author and developer: (C) 2025 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import pytest

from cmeta.utils.names import parse_cmeta_ref, restore_cmeta_ref

def test_parse_cmeta_ref_basic():
    r = parse_cmeta_ref("catrepo:catname::artrepo:artname")
    assert r['return'] == 0
    ref = r['ref_parts']
    assert ref.get("category_repo_alias") == "catrepo"
    assert ref.get("category_alias") == "catname"
    assert ref.get("artifact_repo_alias") == "artrepo"
    assert ref.get("artifact_alias") == "artname"

def test_parse_cmeta_ref_with_uids():
    r = parse_cmeta_ref("catrepo:catname,abcd1234abcd1234::artrepo:artname,1234567890abcdef")
    assert r['return'] == 0
    ref = r['ref_parts']
    assert ref.get("category_repo_alias") == "catrepo"
    assert ref.get("category_alias") == "catname"
    assert ref.get("category_uid") == "abcd1234abcd1234"
    assert ref.get("artifact_repo_alias") == "artrepo"
    assert ref.get("artifact_alias") == "artname"
    assert ref.get("artifact_uid") == "1234567890abcdef"

def test_parse_cmeta_ref_only_artifact():
    r = parse_cmeta_ref("artrepo:artname")
    assert r['return'] == 1 or r['return'] == 0  # Accept error or empty ref

def test_parse_cmeta_ref_none():
    r = parse_cmeta_ref(None)
    assert r['return'] == 0 or r['return'] == 1  # Accept error or empty ref

def test_restore_cmeta_ref_basic():
    ref_parts = {
        "category_repo_alias": "catrepo",
        "category_alias": "catname",
        "artifact_repo_alias": "artrepo",
        "artifact_alias": "artname"
    }
    r = restore_cmeta_ref(ref_parts)
    assert r['return'] == 0
    assert r['ref'] == "catrepo:catname::artrepo:artname"

def test_restore_cmeta_ref_with_uid():
    ref_parts = {
        "category_repo_alias": "catrepo",
        "category_alias": "catname",
        "category_uid": "abcd1234abcd1234",
        "artifact_repo_alias": "artrepo",
        "artifact_alias": "artname",
        "artifact_uid": "1234567890abcdef"
    }
    r = restore_cmeta_ref(ref_parts)
    assert r['return'] == 0
    assert r['ref'] == "catrepo:catname,abcd1234abcd1234::artrepo:artname,1234567890abcdef"

def test_restore_cmeta_ref_only_artifact():
    ref_parts = {
        "artifact_repo_alias": "artrepo",
        "artifact_alias": "artname"
    }
    r = restore_cmeta_ref(ref_parts)
    assert r['return'] == 1 or r['return'] == 0  # Accept error or empty ref

def test_round_trip():
    original = "catrepo:catname,abcd1234abcd1234::artrepo:artname,1234567890abcdef"
    r = parse_cmeta_ref(original)
    assert r['return'] == 0
    restored = restore_cmeta_ref(r['ref_parts'])
    assert restored['return'] == 0
    assert restored['ref'] == original
    parsed = parse_cmeta_ref(original)
    restored = restore_cmeta_ref(parsed['ref_parts'])
    assert restored['ref'] == original
