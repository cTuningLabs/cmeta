"""
Integration tests that spin up CMeta in a temporary CMETA_HOME.

Each test runs against a fresh <CMETA_HOME> in tmp_path so it does not touch
the user's real cMeta state.

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import json
import os
from pathlib import Path

import pytest

from cmeta import CMeta


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    """A fresh CMeta bound to a temp CMETA_HOME."""
    # Isolate from ambient env vars so home resolution is deterministic.
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX',
                'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    return CMeta(home=str(tmp_path))


# ---------------------------------------------------------------------------
# Bootstrap: default layout
# ---------------------------------------------------------------------------

def test_first_launch_creates_layout(cm, tmp_path):
    # Trigger init by any access() call.
    r = cm.access({'category': 'repo', 'command': 'list', 'con': False})
    assert r['return'] == 0

    home = Path(tmp_path)
    assert (home / 'repos.json').is_file()
    assert (home / 'repos' / 'local' / '_cmr.yaml').is_file()
    assert (home / 'index').is_dir()


def test_repos_json_lists_local_and_internal(cm, tmp_path):
    cm.access({'category': 'repo', 'command': 'list', 'con': False})

    with open(tmp_path / 'repos.json') as f:
        registry = json.load(f)

    paths = list(registry.keys())
    # Insertion order: local first, then internal.
    assert any(p.endswith('local') or p.endswith('local' + os.sep) for p in paths)
    assert any('internal-repo' in p for p in paths)


def test_local_repo_cmr_yaml_has_expected_fields(cm, tmp_path):
    cm.access({'category': 'repo', 'command': 'list', 'con': False})

    import yaml
    with open(tmp_path / 'repos' / 'local' / '_cmr.yaml') as f:
        cmr = yaml.safe_load(f)

    assert 'artifact' in cmr
    assert cmr.get('category', '').startswith('repo,')


def test_reindex_rebuilds_index(cm, tmp_path):
    cm.access({'category': 'repo', 'command': 'list', 'con': False})
    index_dir = tmp_path / 'index'
    for f in index_dir.iterdir():
        f.unlink()

    r = cm.access({'reindex': True, 'con': False})
    assert r['return'] == 0
    assert any(index_dir.iterdir())


# ---------------------------------------------------------------------------
# Base commands work end-to-end
# ---------------------------------------------------------------------------

def test_category_list_includes_shipped_categories(cm):
    r = cm.access({'category': 'category', 'command': 'find', 'con': False})
    assert r['return'] == 0
    aliases = {a['cmeta_ref_parts']['artifact_alias'] for a in r['artifacts']}
    for expected in ['repo', 'config', 'app', 'utils', 'category', 'cache',
                     'experiment', 'note']:
        assert expected in aliases, f'missing category alias: {expected}'


def test_repo_list_returns_default_local_and_internal(cm):
    r = cm.access({'category': 'repo', 'command': 'find', 'con': False})
    assert r['return'] == 0
    aliases = {a['cmeta_ref_parts'].get('artifact_alias')
               for a in r['artifacts']
               if a['cmeta_ref_parts'].get('artifact_alias')}
    assert 'internal' in aliases
    assert 'local' in aliases


def test_category_uid_lookup_matches_alias_lookup(cm):
    r1 = cm.access({'category': 'category', 'command': 'find',
                    'arg1': 'repo', 'con': False})
    r2 = cm.access({'category': 'category', 'command': 'find',
                    'arg1': 'repo,f4f792ab40c7498f', 'con': False})
    assert r1['return'] == 0 and r2['return'] == 0
    uids1 = {a['cmeta_ref_parts']['artifact_uid'] for a in r1['artifacts']}
    uids2 = {a['cmeta_ref_parts']['artifact_uid'] for a in r2['artifacts']}
    assert 'f4f792ab40c7498f' in uids1
    assert uids2 == {'f4f792ab40c7498f'}


# ---------------------------------------------------------------------------
# Artifact CRUD lifecycle in the default local scratch repo
# ---------------------------------------------------------------------------

def test_artifact_lifecycle_asset(cm):
    # `asset` has no category-level `create` override, so it exercises the
    # base CRUD path unchanged.
    # create
    r = cm.access({'category': 'asset', 'command': 'create',
                   'arg1': 'test-asset', 'yaml': True, 'con': False,
                   'meta': {'description': 'hello'}})
    assert r['return'] == 0

    # find
    r = cm.access({'category': 'asset', 'command': 'find',
                   'arg1': 'test-asset', 'con': False})
    assert r['return'] == 0
    assert len(r['artifacts']) == 1
    artifact = r['artifacts'][0]
    uid = artifact['cmeta_ref_parts']['artifact_uid']

    # read (also confirms alias,UID roundtrip resolves via UID)
    r = cm.access({'category': 'asset', 'command': 'read',
                   'arg1': f'test-asset,{uid}', 'con': False})
    assert r['return'] == 0
    assert r['cmeta']['description'] == 'hello'

    # update (deep-merge, list-append)
    r = cm.access({'category': 'asset', 'command': 'update',
                   'arg1': 'test-asset',
                   'meta': {'description': 'hello v2',
                            'tags': ['t1']},
                   'new_tags': 't2,t3',
                   'con': False})
    assert r['return'] == 0

    r = cm.access({'category': 'asset', 'command': 'read',
                   'arg1': 'test-asset', 'con': False})
    assert r['cmeta']['description'] == 'hello v2'
    assert set(r['cmeta']['tags']) >= {'t2', 't3'}

    # tags command
    r = cm.access({'category': 'asset', 'command': 'tags',
                   'arg1': 'test-asset', 'con': False})
    assert r['return'] == 0

    # delete
    r = cm.access({'category': 'asset', 'command': 'delete',
                   'arg1': 'test-asset', 'force': True, 'con': False})
    assert r['return'] == 0

    # verify gone
    r = cm.access({'category': 'asset', 'command': 'find',
                   'arg1': 'test-asset', 'con': False})
    assert r['return'] in (0, 16)
    if r['return'] == 0:
        assert r['artifacts'] == []


def test_get_creates_when_missing_and_returns_created_flag(cm):
    r = cm.access({'category': 'asset', 'command': 'get',
                   'arg1': 'auto-created', 'yaml': True, 'con': False})
    assert r['return'] == 0
    assert r.get('created') is True

    r = cm.access({'category': 'asset', 'command': 'get',
                   'arg1': 'auto-created', 'con': False})
    assert r['return'] == 0
    assert r.get('created') is False

    cm.access({'category': 'asset', 'command': 'delete',
               'arg1': 'auto-created', 'force': True, 'con': False})


def test_set_updates_or_creates(cm):
    r = cm.access({'category': 'asset', 'command': 'set',
                   'arg1': 'set-asset', 'yaml': True, 'con': False,
                   'meta': {'k': 'v1'}})
    assert r['return'] == 0

    r = cm.access({'category': 'asset', 'command': 'set',
                   'arg1': 'set-asset', 'con': False,
                   'meta': {'k': 'v2', 'other': 42}})
    assert r['return'] == 0

    r = cm.access({'category': 'asset', 'command': 'read',
                   'arg1': 'set-asset', 'con': False})
    assert r['cmeta']['k'] == 'v2'
    assert r['cmeta']['other'] == 42

    cm.access({'category': 'asset', 'command': 'delete',
               'arg1': 'set-asset', 'force': True, 'con': False})


# ---------------------------------------------------------------------------
# ctx propagation across nested access() calls
# ---------------------------------------------------------------------------

def test_ctx_is_created_and_carries_framework_keys(cm):
    ctx = {}
    r = cm.access({'category': 'repo', 'command': 'list',
                   'con': False, 'ctx': ctx})
    assert r['return'] == 0
    # After the call, the ctx we handed in has been populated by the framework
    # with `origin` and `nested_call`.
    assert 'origin' in ctx
    assert 'pwd' in ctx['origin']
    assert ctx.get('nested_call') == -1   # decremented back after the call


def test_ctx_agent_namespace_survives_nested_calls(cm):
    """Custom ctx keys attached by the caller must survive nested access()."""
    ctx = {'agent': {'session_id': 'sess-42', 'trace': []}}

    # Call a category command that internally re-enters cm.access (repo.find →
    # base.find_). The agent key must still be present after the call.
    r = cm.access({'category': 'repo', 'command': 'find',
                   'arg1': 'internal',
                   'con': False, 'ctx': ctx})
    assert r['return'] == 0
    assert ctx['agent']['session_id'] == 'sess-42'


def test_ctx_origin_preserves_first_params(cm):
    ctx = {}
    request = {'category': 'category', 'command': 'find',
               'arg1': 'repo', 'con': False, 'ctx': ctx}
    r = cm.access(request)
    assert r['return'] == 0
    assert ctx['origin']['params']['category'] == 'category'
    assert ctx['origin']['params']['command'] == 'find'


# ---------------------------------------------------------------------------
# Utility category: uid generation
# ---------------------------------------------------------------------------

def test_utils_uid_generates_valid_uid(cm):
    from cmeta.utils.names import is_valid_cmeta_uid
    r = cm.access({'category': 'utils', 'command': 'uid', 'con': False})
    assert r['return'] == 0
    uid = r.get('uid') or r.get('cmeta_uid')
    if uid is not None:
        assert is_valid_cmeta_uid(uid)


# ---------------------------------------------------------------------------
# Bad inputs return an error dict, not an exception
# ---------------------------------------------------------------------------

def test_missing_category_returns_error(cm):
    r = cm.access({'command': 'find'})
    assert r['return'] > 0
    assert 'category' in r['error'].lower()


def test_unknown_command_returns_error(cm):
    r = cm.access({'category': 'note', 'command': 'no-such-command',
                   'con': False})
    assert r['return'] > 0


def test_unknown_category_returns_not_found(cm):
    r = cm.access({'category': 'no-such-category', 'command': 'find',
                   'con': False})
    assert r['return'] != 0
