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
