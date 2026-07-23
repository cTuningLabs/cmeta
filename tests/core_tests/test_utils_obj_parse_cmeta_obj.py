"""
cMeta tests

cMeta author and developer: (C) 2025 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import pytest

from cmeta.utils.names import parse_cmeta_obj, restore_cmeta_obj

def test_parse_cmeta_obj_basic():
    r = parse_cmeta_obj("myartifact")
    assert r['return'] == 0
    obj = r['obj_parts']
    assert obj.get("repo_alias") is None
    assert obj.get("repo_uid") is None
    assert obj.get("alias") == "myartifact"
    assert obj.get("uid") is None

def test_parse_cmeta_obj_with_repo():
    r = parse_cmeta_obj("myrepo:myartifact")
    assert r['return'] == 0
    obj = r['obj_parts']
    assert obj.get("repo_alias") == "myrepo"
    assert obj.get("repo_uid") is None
    assert obj.get("alias") == "myartifact"
    assert obj.get("uid") is None

def test_parse_cmeta_obj_with_repo_uid():
    r = parse_cmeta_obj("abcd1234abcd1234:myartifact")
    assert r['return'] == 0
    obj = r['obj_parts']
    assert obj.get("repo_alias") is None
    assert obj.get("repo_uid") == "abcd1234abcd1234"
    assert obj.get("alias") == "myartifact"
    assert obj.get("uid") is None

def test_parse_cmeta_obj_with_alias_uid():
    r = parse_cmeta_obj("myrepo:myartifact,abcd1234abcd1234")
    assert r['return'] == 0
    obj = r['obj_parts']
    assert obj.get("repo_alias") == "myrepo"
    assert obj.get("repo_uid") is None
    assert obj.get("alias") == "myartifact"
    assert obj.get("uid") == "abcd1234abcd1234"

def test_parse_cmeta_obj_none():
    r = parse_cmeta_obj(None)
    assert r['return'] == 0 or r['return'] == 1  # Accept error return for None input

def test_restore_cmeta_obj_basic():
    obj = {
        "repo_alias": "myrepo",
        "repo_uid": None,
        "alias": "myartifact",
        "uid": None
    }
    r = restore_cmeta_obj(obj)
    assert r['return'] == 0
    assert r['obj'] == "myrepo:myartifact"

def test_restore_cmeta_obj_with_uid():
    obj = {
        "repo_alias": None,
        "repo_uid": "abcd1234abcd1234",
        "alias": None,
        "uid": "abcd1234abcd1234"
    }
    r = restore_cmeta_obj(obj)
    assert r['return'] == 0
    assert r['obj'] == "abcd1234abcd1234:abcd1234abcd1234"

def test_restore_cmeta_obj_only_artifact():
    obj = {
        "repo_alias": None,
        "repo_uid": None,
        "alias": "myartifact",
        "uid": None
    }
    r = restore_cmeta_obj(obj)
    assert r['return'] == 0
    assert r['obj'] == "myartifact"

def test_round_trip():
    original = "myrepo:myartifact,abcd1234abcd1234"
    r = parse_cmeta_obj(original)
    assert r['return'] == 0
    restored = restore_cmeta_obj(r['obj_parts'])
    assert restored['return'] == 0
    assert restored['obj'] == original

def test_parse_cmeta_obj_with_key():
    r = parse_cmeta_obj("myrepo:myartifact", key="artifact")
    assert r['return'] == 0
    obj = r['obj_parts']
    assert obj.get("artifact_repo_alias") == "myrepo"
    assert obj.get("artifact_repo_uid") is None
    assert obj.get("artifact_alias") == "myartifact"
    assert obj.get("artifact_uid") is None

def test_restore_cmeta_obj_with_key():
    obj = {
        "artifact_repo_alias": "myrepo",
        "artifact_repo_uid": None,
        "artifact_alias": "myartifact",
        "artifact_uid": None
    }
    r = restore_cmeta_obj(obj, key="artifact")
    assert r['return'] == 0
    assert r['obj'] == "myrepo:myartifact"
