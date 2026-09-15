"""
Integration tests for filtering a search by repository (`<category>::<repo>:<artifact>`).

Regression guard: a repo-filtered search over a wildcard category also visits the
built-in `repo` category, whose index entries have no `repo_uid` (repositories are
not themselves inside a repository). That used to raise KeyError in
`Repos.find_in_index`.

Each test runs against a fresh <CMETA_HOME> in tmp_path so it does not touch
the user's real cMeta state.

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import pytest

from cmeta import CMeta


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    """A fresh CMeta bound to a temp CMETA_HOME."""
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX',
                'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    return CMeta(home=str(tmp_path))


def _repo_uid(cm, alias):
    r = cm.access({'category': 'repo', 'command': 'find',
                   'arg1': alias, 'con': False})
    assert r['return'] == 0
    return r['artifacts'][0]['cmeta_ref_parts']['artifact_uid']


# ---------------------------------------------------------------------------
# The `repo` category itself under a repo filter
# ---------------------------------------------------------------------------

def test_find_in_index_repo_category_with_repo_filter(cm):
    """Repo artifacts have no `repo_uid` - filtering by repo must prune them,
    not raise KeyError."""
    internal_uid = _repo_uid(cm, 'internal')

    r = cm.repos.find_in_index('repo', cm.repos.cfg['category_repo_uid'],
                               '*', None, repos=[internal_uid])
    assert r['return'] == 0
    assert r['artifacts'] == []


# ---------------------------------------------------------------------------
# Wildcard category + repo filter, end to end
# ---------------------------------------------------------------------------

def test_wildcard_category_with_repo_filter_finds_artifacts(cm):
    r = cm.access({'category': 'utils', 'command': 'find_by_cid',
                   'arg1': '*::internal:*', 'con': False})
    assert r['return'] == 0
    assert len(r['artifacts']) > 0

    # Repositories are never inside a repository, so none may leak into the result.
    assert all(a['cmeta_ref_parts']['category_alias'] != 'repo'
               for a in r['artifacts'])


def test_repo_filter_actually_prunes(cm):
    """The filter must select artifacts, not merely be ignored."""
    internal_uid = _repo_uid(cm, 'internal')

    r = cm.access({'category': 'utils', 'command': 'find_by_cid',
                   'arg1': '*::internal:*', 'con': False})
    assert r['return'] == 0
    assert all(a['cmeta_ref_parts'].get('repo_uid') == internal_uid
               for a in r['artifacts'])

    # The empty local scratch repo holds no artifacts - "not found" (16), no crash.
    r = cm.access({'category': 'utils', 'command': 'find_by_cid',
                   'arg1': '*::local:*', 'con': False})
    assert r['return'] in (0, 16)
    if r['return'] == 0:
        assert r['artifacts'] == []
