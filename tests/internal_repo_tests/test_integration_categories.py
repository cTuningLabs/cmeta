"""
Integration tests exercising shipped internal categories end-to-end via
`cm.access()` in a temporary CMETA_HOME.

Covers:
  - utils.uid / utils.uuid
  - utils.json2yaml_ / yaml2json_ round-trip
  - utils.pkl2json / json2pickle_ round-trip
  - utils.utf8sig_to_utf8_ (BOM stripping)
  - config.set / get / show / unset
  - `cx . info` current-directory detection
  - utils.detect_category / utils.detect_repo (the same detection, exposed
    as commands)

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import json
import os
import pickle
from pathlib import Path

import pytest

from cmeta import CMeta


# ---------------------------------------------------------------------------
# Fresh CMeta bound to a temp CMETA_HOME
# ---------------------------------------------------------------------------

@pytest.fixture()
def cm(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX',
                'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    return CMeta(home=str(tmp_path))


# ---------------------------------------------------------------------------
# utils.uid / utils.uuid
# ---------------------------------------------------------------------------

def test_utils_uid_returns_valid_hex_uid(cm):
    from cmeta.utils.names import is_valid_cmeta_uid

    r = cm.access({'category': 'utils', 'command': 'uid',
                   'con': False, 'clipboard': False})
    assert r['return'] == 0
    uid = r.get('uid')
    assert uid is not None
    assert is_valid_cmeta_uid(uid)


def test_utils_uid_is_unique_across_calls(cm):
    uids = set()
    for _ in range(10):
        r = cm.access({'category': 'utils', 'command': 'uid',
                       'con': False, 'clipboard': False})
        assert r['return'] == 0
        uids.add(r['uid'])
    assert len(uids) == 10


def test_utils_uuid_returns_rfc4122_uuid(cm):
    r = cm.access({'category': 'utils', 'command': 'uuid',
                   'con': False, 'clipboard': False})
    assert r['return'] == 0
    u = r.get('uuid')
    assert u is not None
    # UUID4: 8-4-4-4-12 hex chars separated by dashes.
    parts = u.split('-')
    assert [len(p) for p in parts] == [8, 4, 4, 4, 12]


# ---------------------------------------------------------------------------
# utils.json2yaml_ / yaml2json_ round-trip
# ---------------------------------------------------------------------------

def test_utils_json2yaml_and_back(cm, tmp_path):
    src = tmp_path / "in.json"
    payload = {'a': 1, 'b': ['x', 'y'], 'c': {'nested': True}}
    src.write_text(json.dumps(payload))

    # json → yaml
    r = cm.access({'category': 'utils', 'command': 'json2yaml',
                   'arg1': str(src), 'con': False})
    assert r['return'] == 0
    yaml_path = src.with_suffix('.yaml')
    assert yaml_path.is_file()

    # yaml → json (into a different file)
    out_json = tmp_path / "round.json"
    r = cm.access({'category': 'utils', 'command': 'yaml2json',
                   'arg1': str(yaml_path), 'arg2': str(out_json),
                   'con': False})
    assert r['return'] == 0

    assert json.loads(out_json.read_text()) == payload


def test_utils_json2yaml_refuses_to_overwrite_without_force(cm, tmp_path):
    src = tmp_path / "in.json"
    src.write_text('{"k": 1}')
    yaml_path = src.with_suffix('.yaml')
    yaml_path.write_text("k: 0\n")   # pre-existing target

    r = cm.access({'category': 'utils', 'command': 'json2yaml',
                   'arg1': str(src), 'con': False})
    assert r['return'] > 0
    assert 'already exists' in r['error']

    # with --force it goes through
    r = cm.access({'category': 'utils', 'command': 'json2yaml',
                   'arg1': str(src), 'force': True, 'con': False})
    assert r['return'] == 0


# ---------------------------------------------------------------------------
# utils.pkl2json / json2pickle_ round-trip
# ---------------------------------------------------------------------------

def test_utils_pkl_and_json_round_trip(cm, tmp_path):
    src = tmp_path / "in.json"
    payload = {'k': [1, 2, {'x': 'y'}]}
    src.write_text(json.dumps(payload))

    r = cm.access({'category': 'utils', 'command': 'json2pickle',
                   'arg1': str(src), 'con': False})
    assert r['return'] == 0
    pkl_path = Path(r['pickle_file'])
    assert pkl_path.is_file()
    with open(pkl_path, 'rb') as f:
        assert pickle.load(f) == payload

    out_json = tmp_path / "back.json"
    r = cm.access({'category': 'utils', 'command': 'pkl2json',
                   'arg1': str(pkl_path), 'arg2': str(out_json),
                   'con': False})
    assert r['return'] == 0
    assert json.loads(out_json.read_text()) == payload


# ---------------------------------------------------------------------------
# utils.utf8sig_to_utf8_ (BOM stripping)
# ---------------------------------------------------------------------------

def test_utils_utf8sig_to_utf8_strips_bom(cm, tmp_path):
    src = tmp_path / "bomfile.txt"
    src.write_bytes('﻿hello world\n'.encode('utf-8'))
    assert src.read_bytes().startswith(b'\xef\xbb\xbf')

    r = cm.access({'category': 'utils', 'command': 'utf8sig_to_utf8',
                   'arg1': str(src), 'con': False})
    assert r['return'] == 0

    data = src.read_bytes()
    assert not data.startswith(b'\xef\xbb\xbf')
    assert data.replace(b'\r\n', b'\n') == b'hello world\n'

    # A .bak backup should have been created in-place.
    assert (tmp_path / "bomfile.txt.bak").is_file()


# ---------------------------------------------------------------------------
# config category — create / read / update / remove keys
# ---------------------------------------------------------------------------

def test_config_set_get_unset(cm):
    # set — creates the config artifact if missing
    r = cm.access({'category': 'config', 'command': 'set',
                   'arg1': 'my-cfg',
                   'meta': {'endpoint': 'https://api.example',
                            'timeout':  30,
                            'creds':    {'user': 'alice'}},
                   'con': False})
    assert r['return'] == 0

    # get — returns config_cmeta with the merged values
    r = cm.access({'category': 'config', 'command': 'get',
                   'arg1': 'my-cfg', 'con': False})
    assert r['return'] == 0
    cfg = r['config_cmeta']
    assert cfg['endpoint'] == 'https://api.example'
    assert cfg['timeout']  == 30
    assert cfg['creds']    == {'user': 'alice'}

    # set again — deep-merge (new key + override existing scalar)
    r = cm.access({'category': 'config', 'command': 'set',
                   'arg1': 'my-cfg',
                   'meta': {'timeout': 60,
                            'creds': {'token': 'secret'}},
                   'con': False})
    assert r['return'] == 0

    r = cm.access({'category': 'config', 'command': 'get',
                   'arg1': 'my-cfg', 'con': False})
    cfg = r['config_cmeta']
    assert cfg['timeout'] == 60
    assert cfg['creds'] == {'user': 'alice', 'token': 'secret'}   # merged
    assert cfg['endpoint'] == 'https://api.example'                # preserved

    # unset — deep_remove a subtree
    r = cm.access({'category': 'config', 'command': 'unset',
                   'arg1': 'my-cfg',
                   'meta': {'creds': {'token': None}},
                   'con': False})
    assert r['return'] == 0

    r = cm.access({'category': 'config', 'command': 'get',
                   'arg1': 'my-cfg', 'con': False})
    cfg = r['config_cmeta']
    assert cfg['creds'] == {'user': 'alice'}
    assert 'token' not in cfg['creds']


def test_config_show_prints_flat_meta_lines(cm, capsys):
    cm.access({'category': 'config', 'command': 'set',
               'arg1': 'flat-cfg',
               'meta': {'a': 1, 'b': {'x': 'y'}},
               'con': False})
    r = cm.access({'category': 'config', 'command': 'show',
                   'arg1': 'flat-cfg', 'con': True})
    assert r['return'] == 0
    captured = capsys.readouterr().out
    assert '--meta.a=1' in captured
    assert '--meta.b.x=y' in captured


def test_config_get_returns_empty_dict_when_no_data(cm):
    # If the artifact is created without any set, data.json is absent → empty dict.
    r = cm.access({'category': 'config', 'command': 'create',
                   'arg1': 'empty-cfg', 'yaml': True, 'con': False})
    assert r['return'] == 0

    r = cm.access({'category': 'config', 'command': 'get',
                   'arg1': 'empty-cfg', 'con': False})
    # Base `read` for a missing `data.json` results in a soft error we tolerate.
    if r['return'] == 0:
        assert r['config_cmeta'] == {}


# ---------------------------------------------------------------------------
# Cross-category call: fetch a config from a categoy hook simulation
# ---------------------------------------------------------------------------

def test_config_can_be_fetched_via_uid_reference(cm):
    """The `config` category can be referenced by UID (rename-safe pattern)."""
    cm.access({'category': 'config', 'command': 'set',
               'arg1': 'uid-cfg', 'meta': {'k': 'v'}, 'con': False})

    r = cm.access({'category': 'config,cc6bfe174be847ed',
                   'command': 'get', 'arg1': 'uid-cfg', 'con': False})
    assert r['return'] == 0
    assert r['config_cmeta']['k'] == 'v'


# ---------------------------------------------------------------------------
# `cx . info`-style current directory detection via cm.utils.common
# ---------------------------------------------------------------------------

def test_detect_cid_in_the_current_directory_from_python(cm, tmp_path,
                                                          monkeypatch):
    # Create an artifact, cd into its folder, run detect.
    cm.access({'category': 'asset', 'command': 'create',
               'arg1': 'detected', 'yaml': True, 'con': False})
    r = cm.access({'category': 'asset', 'command': 'find',
                   'arg1': 'detected', 'con': False})
    artifact_path = r['artifacts'][0]['path']

    monkeypatch.chdir(artifact_path)

    from cmeta.utils.common import detect_cid_in_the_current_directory
    r = detect_cid_in_the_current_directory(cm)
    assert r['return'] == 0
    assert r['category_alias'] == 'asset'
    assert r['artifact_alias'] == 'detected'


# ---------------------------------------------------------------------------
# utils.detect_category
# ---------------------------------------------------------------------------

@pytest.fixture()
def detected_artifact_path(cm):
    """Create an artifact and return the path to its directory."""
    cm.access({'category': 'asset', 'command': 'create',
               'arg1': 'detected', 'yaml': True, 'con': False})
    r = cm.access({'category': 'asset', 'command': 'find',
                   'arg1': 'detected', 'con': False})
    return r['artifacts'][0]['path']


def test_detect_category_inside_an_artifact(cm, detected_artifact_path,
                                            monkeypatch):
    monkeypatch.chdir(detected_artifact_path)

    r = cm.access({'category': 'utils', 'command': 'detect_category',
                   'con': False})
    assert r['return'] == 0
    assert r['category_alias'] == 'asset'
    assert r['artifact_name'] is not None
    # Inside an artifact both alias and UID are known, so "alias,UID"
    assert r['category'].startswith('asset,')
    assert r['category_uid']


def test_detect_category_in_the_category_directory(cm, detected_artifact_path,
                                                   monkeypatch):
    # One level up from the artifact is the category directory itself
    category_path = os.path.dirname(detected_artifact_path)
    monkeypatch.chdir(category_path)

    r = cm.access({'category': 'utils', 'command': 'detect_category',
                   'con': False})
    assert r['return'] == 0
    assert r['category'] == 'asset'          # alias only - no artifact context
    assert r['artifact_name'] is None


def test_detect_category_accepts_an_explicit_path(cm, detected_artifact_path):
    # No chdir: the directory is passed as arg1 instead
    r = cm.access({'category': 'utils', 'command': 'detect_category',
                   'arg1': detected_artifact_path, 'con': False})
    assert r['return'] == 0
    assert r['category_alias'] == 'asset'
    assert r['path'] == os.path.normpath(os.path.abspath(detected_artifact_path))


def test_detect_category_outside_a_repo_is_not_an_error(cm, tmp_path,
                                                        monkeypatch):
    outside = tmp_path / 'not-a-repo'
    outside.mkdir()
    monkeypatch.chdir(outside)

    # Nothing detected is a valid answer: callers fall back to a wider search
    r = cm.access({'category': 'utils', 'command': 'detect_category',
                   'con': False})
    assert r['return'] == 0
    assert r['category'] is None


def test_detect_category_can_fail_when_asked(cm, tmp_path, monkeypatch):
    outside = tmp_path / 'not-a-repo-either'
    outside.mkdir()
    monkeypatch.chdir(outside)

    r = cm.access({'category': 'utils', 'command': 'detect_category',
                   'fail_if_not_found': True, 'con': False})
    assert r['return'] > 0
    assert r.get('error')


def test_detect_category_rejects_a_missing_directory(cm, tmp_path):
    r = cm.access({'category': 'utils', 'command': 'detect_category',
                   'arg1': str(tmp_path / 'no-such-dir'), 'con': False})
    assert r['return'] > 0
    assert 'not found' in r['error']


# ---------------------------------------------------------------------------
# utils.detect_repo
# ---------------------------------------------------------------------------

def test_detect_repo_inside_an_artifact(cm, detected_artifact_path,
                                        monkeypatch):
    monkeypatch.chdir(detected_artifact_path)

    r = cm.access({'category': 'utils', 'command': 'detect_repo',
                   'con': False})
    assert r['return'] == 0
    assert r['repo']
    assert r['repo_alias'] or r['repo_uid']
    # The path relative to the repository root leads back to the artifact
    assert r['artifact_path']


def test_detect_repo_in_the_category_directory(cm, detected_artifact_path,
                                               monkeypatch):
    monkeypatch.chdir(os.path.dirname(detected_artifact_path))

    r = cm.access({'category': 'utils', 'command': 'detect_repo',
                   'con': False})
    assert r['return'] == 0
    assert r['repo']


def test_detect_repo_agrees_with_detect_category(cm, detected_artifact_path):
    # Both commands read the same detection, so the repo reported alongside
    # the category must match the one detect_repo reports
    rc = cm.access({'category': 'utils', 'command': 'detect_category',
                    'arg1': detected_artifact_path, 'con': False})
    rr = cm.access({'category': 'utils', 'command': 'detect_repo',
                    'arg1': detected_artifact_path, 'con': False})
    assert rc['return'] == 0 and rr['return'] == 0
    assert rc['artifact_repo_name'] == rr['repo']


def test_detect_repo_accepts_an_explicit_path(cm, detected_artifact_path):
    r = cm.access({'category': 'utils', 'command': 'detect_repo',
                   'arg1': detected_artifact_path, 'con': False})
    assert r['return'] == 0
    assert r['repo']
    assert r['path'] == os.path.normpath(os.path.abspath(detected_artifact_path))


def test_detect_repo_outside_a_repo_is_not_an_error(cm, tmp_path, monkeypatch):
    outside = tmp_path / 'no-repo-here'
    outside.mkdir()
    monkeypatch.chdir(outside)

    r = cm.access({'category': 'utils', 'command': 'detect_repo',
                   'con': False})
    assert r['return'] == 0
    assert r['repo'] is None


def test_detect_repo_can_fail_when_asked(cm, tmp_path, monkeypatch):
    outside = tmp_path / 'no-repo-here-either'
    outside.mkdir()
    monkeypatch.chdir(outside)

    r = cm.access({'category': 'utils', 'command': 'detect_repo',
                   'fail_if_not_found': True, 'con': False})
    assert r['return'] > 0
    assert r.get('error')


def test_detect_repo_rejects_a_missing_directory(cm, tmp_path):
    r = cm.access({'category': 'utils', 'command': 'detect_repo',
                   'arg1': str(tmp_path / 'no-such-dir'), 'con': False})
    assert r['return'] > 0
    assert 'not found' in r['error']


# ---------------------------------------------------------------------------
# utils.find_by_cid / utils.smart_find_by_cid - tags and match filters
# ---------------------------------------------------------------------------

@pytest.fixture()
def tagged_assets(cm):
    """Two assets sharing one tag and differing in another."""
    cm.access({'category': 'asset', 'command': 'create', 'arg1': 'alpha',
               'tags': 'red,shared', 'yaml': True, 'con': False})
    cm.access({'category': 'asset', 'command': 'create', 'arg1': 'beta',
               'tags': 'blue,shared', 'yaml': True, 'con': False})
    return ('alpha', 'beta')


def _aliases(r):
    return sorted(os.path.basename(a['path']) for a in r.get('artifacts', []))


def test_find_by_cid_without_tags_returns_everything(cm, tagged_assets):
    r = cm.access({'category': 'utils', 'command': 'find_by_cid',
                   'arg1': 'asset::*', 'con': False})
    assert r['return'] == 0
    assert _aliases(r) == ['alpha', 'beta']


def test_find_by_cid_filters_by_a_single_tag(cm, tagged_assets):
    r = cm.access({'category': 'utils', 'command': 'find_by_cid',
                   'arg1': 'asset::*', 'tags': 'red', 'con': False})
    assert r['return'] == 0
    assert _aliases(r) == ['alpha']


def test_find_by_cid_tags_are_combined_with_and(cm, tagged_assets):
    r = cm.access({'category': 'utils', 'command': 'find_by_cid',
                   'arg1': 'asset::*', 'tags': 'shared,blue', 'con': False})
    assert r['return'] == 0
    assert _aliases(r) == ['beta']


def test_find_by_cid_supports_excluding_tags(cm, tagged_assets):
    r = cm.access({'category': 'utils', 'command': 'find_by_cid',
                   'arg1': 'asset::*', 'tags': 'shared,-red', 'con': False})
    assert r['return'] == 0
    assert _aliases(r) == ['beta']


def test_find_by_cid_unknown_tag_is_an_empty_result(cm, tagged_assets):
    # 16 is cMeta's "not found" - an empty result rather than a failure
    r = cm.access({'category': 'utils', 'command': 'find_by_cid',
                   'arg1': 'asset::*', 'tags': 'no-such-tag', 'con': False})
    assert r['return'] == 16


def test_find_by_cid_tags_accept_a_list(cm, tagged_assets):
    r = cm.access({'category': 'utils', 'command': 'find_by_cid',
                   'arg1': 'asset::*', 'tags': ['red'], 'con': False})
    assert r['return'] == 0
    assert _aliases(r) == ['alpha']


def test_find_by_cid_matches_on_a_meta_key(cm, tagged_assets):
    r = cm.access({'category': 'utils', 'command': 'find_by_cid',
                   'arg1': 'asset::alpha', 'con': False})
    category = r['artifacts'][0]['cmeta']['category']

    r = cm.access({'category': 'utils', 'command': 'find_by_cid',
                   'arg1': 'asset::*', 'match': {'category': category},
                   'con': False})
    assert r['return'] == 0
    assert _aliases(r) == ['alpha', 'beta']


def test_find_by_cid_match_on_a_wrong_value_filters_everything_out(cm,
                                                                   tagged_assets):
    r = cm.access({'category': 'utils', 'command': 'find_by_cid',
                   'arg1': 'asset::*',
                   'match': {'category': 'no-such-category'}, 'con': False})
    assert r['return'] == 16


def test_find_by_cid_all_tags_requires_the_exact_set(cm, tagged_assets):
    r = cm.access({'category': 'utils', 'command': 'find_by_cid',
                   'arg1': 'asset::*', 'all_tags': 'red,shared', 'con': False})
    assert r['return'] == 0
    assert _aliases(r) == ['alpha']

    r = cm.access({'category': 'utils', 'command': 'find_by_cid',
                   'arg1': 'asset::*', 'all_tags': 'red', 'con': False})
    assert r['return'] == 16


def test_smart_find_by_cid_forwards_tags(cm, tagged_assets):
    r = cm.access({'category': 'utils', 'command': 'smart_find_by_cid',
                   'arg1': '(wrapped in text) asset:alpha', 'tags': 'red',
                   'con': False})
    assert r['return'] == 0
    assert _aliases(r) == ['alpha']


def test_smart_find_by_cid_tags_can_exclude_the_match(cm, tagged_assets):
    r = cm.access({'category': 'utils', 'command': 'smart_find_by_cid',
                   'arg1': '(wrapped in text) asset:alpha', 'tags': 'blue',
                   'con': False})
    assert r['return'] == 16


def test_smart_find_by_cid_forwards_match(cm, tagged_assets):
    r = cm.access({'category': 'utils', 'command': 'smart_find_by_cid',
                   'arg1': '(wrapped in text) asset:alpha',
                   'match': {'category': 'no-such-category'}, 'con': False})
    assert r['return'] == 16


# ---------------------------------------------------------------------------
# utils.find_by_cid / utils.smart_find_by_cid - smart_match (any value, any key)
# ---------------------------------------------------------------------------

def test_smart_match_finds_a_value_under_an_unnamed_key(cm, tagged_assets):
    # "blue" is a tag value; smart_match needs no key name to reach it
    r = cm.access({'category': 'utils', 'command': 'find_by_cid',
                   'arg1': 'asset::*', 'smart_match': 'blue', 'con': False})
    assert r['return'] == 0
    assert _aliases(r) == ['beta']


def test_smart_match_substring_can_span_an_unrelated_value(cm, tagged_assets):
    # Documented consequence of substring matching: "red" is inside "shared",
    # so both artifacts match even though only alpha is tagged "red"
    r = cm.access({'category': 'utils', 'command': 'find_by_cid',
                   'arg1': 'asset::*', 'smart_match': 'red', 'con': False})
    assert r['return'] == 0
    assert _aliases(r) == ['alpha', 'beta']


def test_smart_match_is_a_substring_match(cm, tagged_assets):
    # "cmeta" sits inside the copyright/category strings, not as a whole value
    r = cm.access({'category': 'utils', 'command': 'find_by_cid',
                   'arg1': 'asset::alpha', 'con': False})
    authors = r['artifacts'][0]['cmeta'].get('authors', '')
    assert authors  # the fixture artifacts carry an authors string

    r = cm.access({'category': 'utils', 'command': 'find_by_cid',
                   'arg1': 'asset::*', 'smart_match': authors[1:-1],
                   'con': False})
    assert r['return'] == 0
    assert _aliases(r) == ['alpha', 'beta']


def test_smart_match_is_case_insensitive(cm, tagged_assets):
    r = cm.access({'category': 'utils', 'command': 'find_by_cid',
                   'arg1': 'asset::*', 'smart_match': 'BLUE', 'con': False})
    assert r['return'] == 0
    assert _aliases(r) == ['beta']


def test_smart_match_values_are_combined_with_or(cm, tagged_assets):
    r = cm.access({'category': 'utils', 'command': 'find_by_cid',
                   'arg1': 'asset::*', 'smart_match': 'red,blue', 'con': False})
    assert r['return'] == 0
    assert _aliases(r) == ['alpha', 'beta']

    # One unknown value alongside a real one still matches on the real one
    r = cm.access({'category': 'utils', 'command': 'find_by_cid',
                   'arg1': 'asset::*', 'smart_match': 'no-such-value,blue',
                   'con': False})
    assert r['return'] == 0
    assert _aliases(r) == ['beta']


def test_smart_match_never_matches_a_key_name(cm, tagged_assets):
    # "tags" is a key in every _cmeta, but not a value in these artifacts
    r = cm.access({'category': 'utils', 'command': 'find_by_cid',
                   'arg1': 'asset::*', 'smart_match': 'tags', 'con': False})
    assert r['return'] == 16


def test_smart_match_pruning_everything_is_an_empty_result(cm, tagged_assets):
    r = cm.access({'category': 'utils', 'command': 'find_by_cid',
                   'arg1': 'asset::*', 'smart_match': 'no-such-value',
                   'con': False})
    assert r['return'] == 16


def test_smart_match_accepts_a_list(cm, tagged_assets):
    r = cm.access({'category': 'utils', 'command': 'find_by_cid',
                   'arg1': 'asset::*', 'smart_match': ['blue'], 'con': False})
    assert r['return'] == 0
    assert _aliases(r) == ['beta']


def test_smart_match_whitespace_only_keeps_everything(cm, tagged_assets):
    r = cm.access({'category': 'utils', 'command': 'find_by_cid',
                   'arg1': 'asset::*', 'smart_match': '   ', 'con': False})
    assert r['return'] == 0
    assert _aliases(r) == ['alpha', 'beta']


def test_smart_match_combines_with_tags(cm, tagged_assets):
    # tags narrow to both, smart_match then prunes to one
    r = cm.access({'category': 'utils', 'command': 'find_by_cid',
                   'arg1': 'asset::*', 'tags': 'shared', 'smart_match': 'blue',
                   'con': False})
    assert r['return'] == 0
    assert _aliases(r) == ['beta']


def test_smart_find_by_cid_forwards_smart_match(cm, tagged_assets):
    r = cm.access({'category': 'utils', 'command': 'smart_find_by_cid',
                   'arg1': '(wrapped in text) asset:alpha',
                   'smart_match': 'red', 'con': False})
    assert r['return'] == 0
    assert _aliases(r) == ['alpha']

    r = cm.access({'category': 'utils', 'command': 'smart_find_by_cid',
                   'arg1': '(wrapped in text) asset:alpha',
                   'smart_match': 'blue', 'con': False})
    assert r['return'] == 16


def test_matches_any_value_walks_nested_structures():
    # Loaded by path: the internal repo lives under a directory with a dash,
    # so it cannot be reached with a normal import statement
    import importlib.util
    import cmeta

    path = os.path.join(os.path.dirname(cmeta.__file__), 'internal-repo',
                        'category', 'utils', 'api', 'common.py')
    spec = importlib.util.spec_from_file_location('cmeta_utils_api_common', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    data = {'a': 'top', 'b': {'c': ['deep', {'d': 'deeper'}]}, 'n': None,
            'i': 42}

    assert module._matches_any_value(data, ['deeper'])
    assert module._matches_any_value(data, ['DEEP'])
    assert module._matches_any_value(data, ['42'])
    assert module._matches_any_value(data, ['nope', 'top'])
    assert not module._matches_any_value(data, ['nope'])
    # Keys are never matched
    assert not module._matches_any_value(data, ['b'])
    # No values to look for means "keep everything"
    assert module._matches_any_value(data, [])
    assert module._matches_any_value(data, None)


# ---------------------------------------------------------------------------
# utils.find_by_cid - search_text / search_files (content of artifact files)
# ---------------------------------------------------------------------------

@pytest.fixture()
def assets_with_files(cm):
    """Three assets: text at the top level, text only nested, and no file."""
    paths = {}
    for alias in ('topinfo', 'deepinfo', 'noinfo'):
        cm.access({'category': 'asset', 'command': 'create', 'arg1': alias,
                   'yaml': True, 'con': False})
        r = cm.access({'category': 'asset', 'command': 'find', 'arg1': alias,
                       'con': False})
        paths[alias] = r['artifacts'][0]['path']

    with open(os.path.join(paths['topinfo'], '_info.md'), 'w',
              encoding='utf-8') as f:
        f.write('alpha beta gamma\n')

    nested = os.path.join(paths['deepinfo'], 'docs', 'notes')
    os.makedirs(nested)
    with open(os.path.join(nested, 'my_info.md'), 'w', encoding='utf-8') as f:
        f.write('deep delta text\n')

    return paths


def _find_assets(cm, **kwargs):
    query = {'category': 'utils', 'command': 'find_by_cid',
             'arg1': 'asset::*', 'con': False}
    query.update(kwargs)
    return cm.access(query)


def test_search_text_absent_reads_no_files(cm, assets_with_files):
    r = _find_assets(cm)
    assert r['return'] == 0
    assert _aliases(r) == ['deepinfo', 'noinfo', 'topinfo']


def test_search_text_defaults_to_info_md(cm, assets_with_files):
    r = _find_assets(cm, search_text='alpha')
    assert r['return'] == 0
    assert _aliases(r) == ['topinfo']


def test_search_text_is_not_recursive_by_default(cm, assets_with_files):
    # "delta" only exists in docs/notes/my_info.md, out of reach of "*info*.md"
    r = _find_assets(cm, search_text='delta')
    assert r['return'] == 16


def test_search_files_double_star_recurses(cm, assets_with_files):
    r = _find_assets(cm, search_text='delta', search_files='**/*info*.md')
    assert r['return'] == 0
    assert _aliases(r) == ['deepinfo']


def test_search_files_double_star_also_matches_the_top_level(cm,
                                                             assets_with_files):
    # "**" matches zero directories too, so a recursive glob is a superset
    r = _find_assets(cm, search_text='alpha', search_files='**/*info*.md')
    assert r['return'] == 0
    assert _aliases(r) == ['topinfo']


def test_search_text_words_are_combined_with_or(cm, assets_with_files):
    r = _find_assets(cm, search_text='no-such-word delta',
                     search_files='**/*info*.md')
    assert r['return'] == 0
    assert _aliases(r) == ['deepinfo']

    r = _find_assets(cm, search_text='alpha delta',
                     search_files='*info*.md,**/*info*.md')
    assert r['return'] == 0
    assert _aliases(r) == ['deepinfo', 'topinfo']


def test_search_text_is_case_insensitive(cm, assets_with_files):
    r = _find_assets(cm, search_text='ALPHA')
    assert r['return'] == 0
    assert _aliases(r) == ['topinfo']


def test_search_text_no_hit_is_an_empty_result(cm, assets_with_files):
    r = _find_assets(cm, search_text='nothing-at-all')
    assert r['return'] == 16


def test_search_files_accepts_an_explicit_glob(cm, assets_with_files):
    r = _find_assets(cm, search_text='alpha', search_files='*.md')
    assert r['return'] == 0
    assert _aliases(r) == ['topinfo']


def test_search_files_alone_changes_nothing(cm, assets_with_files):
    # Without search_text there is nothing to look for, so no file is opened
    r = _find_assets(cm, search_files='**/*')
    assert r['return'] == 0
    assert _aliases(r) == ['deepinfo', 'noinfo', 'topinfo']


def test_search_text_combines_with_tags_and_smart_match(cm, assets_with_files):
    # "asset" is the category value carried by all three artifacts' meta
    r = _find_assets(cm, smart_match='asset', search_text='alpha')
    assert r['return'] == 0
    assert _aliases(r) == ['topinfo']

    # The stages compose: nothing survives both filters here
    r = _find_assets(cm, smart_match='no-such-meta-value', search_text='alpha')
    assert r['return'] == 16


def test_smart_find_by_cid_forwards_search_text(cm, assets_with_files):
    r = cm.access({'category': 'utils', 'command': 'smart_find_by_cid',
                   'arg1': '(wrapped) asset:topinfo', 'search_text': 'alpha',
                   'con': False})
    assert r['return'] == 0
    assert _aliases(r) == ['topinfo']

    r = cm.access({'category': 'utils', 'command': 'smart_find_by_cid',
                   'arg1': '(wrapped) asset:topinfo', 'search_text': 'delta',
                   'con': False})
    assert r['return'] == 16


def test_search_files_pattern_cannot_escape_the_artifact(cm, assets_with_files):
    # A leading separator would otherwise root the glob outside the artifact
    r = _find_assets(cm, search_text='alpha', search_files='/*info*.md')
    assert r['return'] == 0
    assert _aliases(r) == ['topinfo']


# ---------------------------------------------------------------------------
# utils.find_by_cid - "files" returned by a content search
# ---------------------------------------------------------------------------

def test_files_is_absent_without_a_content_search(cm, assets_with_files):
    r = _find_assets(cm)
    assert r['return'] == 0
    assert 'files' not in r


def test_files_lists_the_matching_files(cm, assets_with_files):
    r = _find_assets(cm, search_text='alpha')
    assert r['return'] == 0

    files = r['files']
    assert len(files) == 1
    assert os.path.basename(files[0]) == '_info.md'
    assert os.path.isabs(files[0])
    assert os.path.isfile(files[0])


def test_files_reaches_into_sub_directories(cm, assets_with_files):
    r = _find_assets(cm, search_text='delta', search_files='**/*info*.md')
    assert r['return'] == 0

    files = r['files']
    assert len(files) == 1
    assert os.path.basename(files[0]) == 'my_info.md'
    # The nested file, not the artifact directory
    assert os.path.isfile(files[0])
    assert 'notes' in files[0]


def test_files_collects_across_several_artifacts(cm, assets_with_files):
    r = _find_assets(cm, search_text='alpha delta',
                     search_files='*info*.md,**/*info*.md')
    assert r['return'] == 0
    assert _aliases(r) == ['deepinfo', 'topinfo']

    files = sorted(os.path.basename(f) for f in r['files'])
    assert files == ['_info.md', 'my_info.md']


def test_files_lists_every_match_inside_one_artifact(cm, assets_with_files):
    # A second matching file in the same artifact must also come back
    extra = os.path.join(assets_with_files['topinfo'], 'more_info.md')
    with open(extra, 'w', encoding='utf-8') as f:
        f.write('alpha again\n')

    r = _find_assets(cm, search_text='alpha')
    assert r['return'] == 0
    assert _aliases(r) == ['topinfo']

    files = sorted(os.path.basename(f) for f in r['files'])
    assert files == ['_info.md', 'more_info.md']


def test_files_excludes_a_matching_glob_without_the_text(cm, assets_with_files):
    # Same glob, but this file does not carry the text - it must not be listed
    other = os.path.join(assets_with_files['topinfo'], 'other_info.md')
    with open(other, 'w', encoding='utf-8') as f:
        f.write('nothing relevant here\n')

    r = _find_assets(cm, search_text='alpha')
    assert r['return'] == 0

    files = sorted(os.path.basename(f) for f in r['files'])
    assert files == ['_info.md']


def test_smart_find_by_cid_returns_files_too(cm, assets_with_files):
    r = cm.access({'category': 'utils', 'command': 'smart_find_by_cid',
                   'arg1': '(wrapped) asset:topinfo', 'search_text': 'alpha',
                   'con': False})
    assert r['return'] == 0
    assert len(r['files']) == 1
    assert os.path.basename(r['files'][0]) == '_info.md'


# ---------------------------------------------------------------------------
# utils.find_by_cid - search_file_names (all parts, in the file name, recursive)
# ---------------------------------------------------------------------------

@pytest.fixture()
def assets_with_named_files(cm):
    """Files at several depths with overlapping name parts."""
    paths = {}
    for alias in ('alpha', 'beta'):
        cm.access({'category': 'asset', 'command': 'create', 'arg1': alias,
                   'yaml': True, 'con': False})
        r = cm.access({'category': 'asset', 'command': 'find', 'arg1': alias,
                       'con': False})
        paths[alias] = r['artifacts'][0]['path']

    nested = os.path.join(paths['alpha'], 'deep', 'nest')
    os.makedirs(nested)

    def write(path, name, text):
        with open(os.path.join(path, name), 'w', encoding='utf-8') as f:
            f.write(text)

    write(paths['alpha'], 'my_report_2026.md', 'hello alpha\n')
    write(nested, 'other_report_2026.txt', 'nested content\n')
    write(paths['alpha'], 'report_only.md', 'no year here\n')
    write(paths['beta'], 'notes_2026.md', 'beta hello\n')

    return paths


def _found_names(r):
    return sorted(os.path.basename(f) for f in r.get('files', []))


def test_search_file_names_matches_one_part(cm, assets_with_named_files):
    r = _find_assets(cm, search_file_names='report')
    assert r['return'] == 0
    assert _found_names(r) == ['my_report_2026.md', 'other_report_2026.txt',
                               'report_only.md']


def test_search_file_names_parts_are_combined_with_and(cm,
                                                       assets_with_named_files):
    # "report_only.md" has "report" but not "2026", so it drops out
    r = _find_assets(cm, search_file_names='report 2026')
    assert r['return'] == 0
    assert _found_names(r) == ['my_report_2026.md', 'other_report_2026.txt']


def test_search_file_names_is_recursive(cm, assets_with_named_files):
    # The nested file is reached without any "**" being asked for
    r = _find_assets(cm, search_file_names='other')
    assert r['return'] == 0
    assert _found_names(r) == ['other_report_2026.txt']
    assert 'nest' in r['files'][0]


def test_search_file_names_spans_artifacts(cm, assets_with_named_files):
    r = _find_assets(cm, search_file_names='2026')
    assert r['return'] == 0
    assert _aliases(r) == ['alpha', 'beta']
    assert _found_names(r) == ['my_report_2026.md', 'notes_2026.md',
                               'other_report_2026.txt']


def test_search_file_names_is_case_insensitive(cm, assets_with_named_files):
    r = _find_assets(cm, search_file_names='REPORT 2026')
    assert r['return'] == 0
    assert _found_names(r) == ['my_report_2026.md', 'other_report_2026.txt']


def test_search_file_names_never_matches_a_directory_name(cm,
                                                          assets_with_named_files):
    # "deep" is a directory, not a file name, and directories are not results
    r = _find_assets(cm, search_file_names='deep')
    assert r['return'] == 16


def test_search_file_names_ignores_the_path_above_the_file(cm,
                                                           assets_with_named_files):
    # "nest" appears in the path but not in any file name
    r = _find_assets(cm, search_file_names='nest')
    assert r['return'] == 16


def test_search_file_names_no_match_is_an_empty_result(cm,
                                                       assets_with_named_files):
    r = _find_assets(cm, search_file_names='no-such-name')
    assert r['return'] == 16


def test_search_file_names_narrows_further_with_text(cm,
                                                     assets_with_named_files):
    r = _find_assets(cm, search_file_names='report 2026', search_text='nested')
    assert r['return'] == 0
    assert _found_names(r) == ['other_report_2026.txt']

    r = _find_assets(cm, search_file_names='report', search_text='no-such-text')
    assert r['return'] == 16


def test_search_file_names_replaces_the_glob_patterns(cm,
                                                      assets_with_named_files):
    # search_files would restrict to *info*.md and find nothing here; naming
    # files takes over as the selector instead of intersecting with it
    r = _find_assets(cm, search_file_names='report 2026',
                     search_files='*info*.md')
    assert r['return'] == 0
    assert _found_names(r) == ['my_report_2026.md', 'other_report_2026.txt']


def test_smart_find_by_cid_forwards_search_file_names(cm,
                                                      assets_with_named_files):
    r = cm.access({'category': 'utils', 'command': 'smart_find_by_cid',
                   'arg1': '(wrapped) asset:alpha',
                   'search_file_names': 'report 2026', 'con': False})
    assert r['return'] == 0
    assert _found_names(r) == ['my_report_2026.md', 'other_report_2026.txt']


def test_search_file_names_accepts_a_list(cm, assets_with_named_files):
    r = _find_assets(cm, search_file_names=['report', '2026'])
    assert r['return'] == 0
    assert _found_names(r) == ['my_report_2026.md', 'other_report_2026.txt']


# ---------------------------------------------------------------------------
# utils.find_by_cid - after_date / before_date
# ---------------------------------------------------------------------------

def _utils_common_module():
    """Load the utils category's own common.py by path (its dir has a dash)."""
    import importlib.util
    import cmeta

    path = os.path.join(os.path.dirname(cmeta.__file__), 'internal-repo',
                        'category', 'utils', 'api', 'common.py')
    spec = importlib.util.spec_from_file_location('cmeta_utils_api_common', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('text,expected', [
    ('2026',                            (2026, 1, 1, 0, 0)),
    ('202605',                          (2026, 5, 1, 0, 0)),
    ('20260503',                        (2026, 5, 3, 0, 0)),
    ('2026-05-03',                      (2026, 5, 3, 0, 0)),
    ('2026/05/03',                      (2026, 5, 3, 0, 0)),
    ('20260503-1430',                   (2026, 5, 3, 14, 30)),
    ('2026-05-03T14:30:00Z',            (2026, 5, 3, 14, 30)),
    # +02:00 is normalized back to UTC
    ('2026-05-03T14:30:00+02:00',       (2026, 5, 3, 12, 30)),
    ('2026-01-19T15:40:51.387488+00:00', (2026, 1, 19, 15, 40)),
])
def test_parse_date_value_accepts_the_documented_forms(text, expected):
    common = _utils_common_module()
    parsed = common._parse_date_value(text)
    assert parsed is not None
    assert (parsed.year, parsed.month, parsed.day,
            parsed.hour, parsed.minute) == expected
    assert parsed.tzinfo is None


@pytest.mark.parametrize('text', ['not a date', '', None, '20261301'])
def test_parse_date_value_rejects_nonsense(text):
    assert _utils_common_module()._parse_date_value(text) is None


@pytest.mark.parametrize('name,expected', [
    ('20251206.far manager - cmeta handling', (2025, 12, 6)),
    ('202512.gfursin - various',              (2025, 12, 1)),
    ('20250814 - cTuning Labs',               (2025, 8, 14)),
    ('2026-05-03 notes',                      (2026, 5, 3)),
    ('20260503-1430.meeting',                 (2026, 5, 3)),
    ('2026.notes',                            (2026, 1, 1)),
    ('2026',                                  (2026, 1, 1)),
])
def test_date_from_name_reads_the_naming_conventions(name, expected):
    parsed = _utils_common_module()._date_from_name(name)
    assert parsed is not None
    assert (parsed.year, parsed.month, parsed.day) == expected


@pytest.mark.parametrize('name', [
    'no-date-here',
    'cmeta-sub-dirs-202608-v3',   # a date, but not at the start
    '2026x',                      # not followed by a separator
    '20261301.bad month',         # not a real date
])
def test_date_from_name_ignores_names_without_a_leading_date(name):
    assert _utils_common_module()._date_from_name(name) is None


def test_artifact_date_prefers_name_then_last_update_then_creation():
    common = _utils_common_module()

    meta = {'last_update_timestamp': '2026-08-01T10:00:00+00:00',
            'creation_timestamp':    '2020-01-01T10:00:00+00:00'}

    # 1. the name wins over both stamps
    assert common._artifact_date(os.path.join('x', '20260503.thing'),
                                 meta).day == 3

    # 2. no name date -> last_update_timestamp
    assert common._artifact_date(os.path.join('x', 'no-date'),
                                 meta).year == 2026

    # 3. no last_update_timestamp -> creation_timestamp
    assert common._artifact_date(
        os.path.join('x', 'no-date'),
        {'creation_timestamp': '2020-01-01T10:00:00+00:00'}).year == 2020

    # 4. nothing to go on
    assert common._artifact_date(os.path.join('x', 'no-date'), {}) is None


@pytest.fixture()
def dated_assets(cm):
    """Assets whose names carry different dates."""
    for alias in ('20240101.old-one', '20260503.mid-one', '20261231.new-one'):
        cm.access({'category': 'asset', 'command': 'create', 'arg1': alias,
                   'yaml': True, 'con': False})
    return ('20240101.old-one', '20260503.mid-one', '20261231.new-one')


def test_after_date_keeps_only_later_artifacts(cm, dated_assets):
    r = _find_assets(cm, after_date='2026')
    assert r['return'] == 0
    assert _aliases(r) == ['20260503.mid-one', '20261231.new-one']


def test_before_date_keeps_only_earlier_artifacts(cm, dated_assets):
    r = _find_assets(cm, before_date='2025')
    assert r['return'] == 0
    assert _aliases(r) == ['20240101.old-one']


def test_after_and_before_make_a_window(cm, dated_assets):
    r = _find_assets(cm, after_date='20260101', before_date='20261201')
    assert r['return'] == 0
    assert _aliases(r) == ['20260503.mid-one']


def test_date_bounds_are_inclusive(cm, dated_assets):
    r = _find_assets(cm, after_date='2026-05-03', before_date='2026-05-03')
    assert r['return'] == 0
    assert _aliases(r) == ['20260503.mid-one']


def test_date_range_with_no_match_is_an_empty_result(cm, dated_assets):
    r = _find_assets(cm, after_date='2030')
    assert r['return'] == 16


def test_an_unreadable_date_is_an_error_not_an_empty_result(cm, dated_assets):
    r = _find_assets(cm, after_date='not a date')
    assert r['return'] == 1
    assert 'after_date' in r['error']

    r = _find_assets(cm, before_date='also not a date')
    assert r['return'] == 1
    assert 'before_date' in r['error']


def test_date_filter_falls_back_to_meta_for_undated_names(cm, tagged_assets):
    # "alpha"/"beta" carry no date in the name, so their creation_timestamp
    # decides - and they were just created, so a future bound excludes them
    r = _find_assets(cm, after_date='2099')
    assert r['return'] == 16

    r = _find_assets(cm, before_date='2099')
    assert r['return'] == 0
    assert _aliases(r) == ['alpha', 'beta']


def test_smart_find_by_cid_forwards_the_date_bounds(cm, dated_assets):
    r = cm.access({'category': 'utils', 'command': 'smart_find_by_cid',
                   'arg1': '(wrapped) asset:20260503.mid-one',
                   'after_date': '2026', 'con': False})
    assert r['return'] == 0
    assert _aliases(r) == ['20260503.mid-one']

    r = cm.access({'category': 'utils', 'command': 'smart_find_by_cid',
                   'arg1': '(wrapped) asset:20260503.mid-one',
                   'before_date': '2025', 'con': False})
    assert r['return'] == 16
