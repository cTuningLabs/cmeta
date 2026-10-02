"""
Integration tests for indexing an artifact folder that already has its meta
(`cx <category> index <repo>:<name>`, for artifacts made or copied by hand):
the index takes the UID of the meta, so `alias,UID` and UID references resolve.

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import pytest

from cmeta import CMeta

UID = '0123456789abcdef'


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX',
                'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    return CMeta(home=str(tmp_path))


def hand_made(cm, tmp_path, name, artifact):
    # The index exists first (the first access builds it), then the folder is made by hand
    cm.access({'category': 'log', 'command': 'find', 'arg1': 'nothing-yet', 'con': False})
    folder = tmp_path / 'repos' / 'local' / 'log' / name
    folder.mkdir(parents=True)
    (folder / '_cmeta.yaml').write_text(f'artifact: {artifact}\ntags:\n- hand-made\n', encoding='utf-8')
    return folder


def uids(r):
    return [a['cmeta_ref_parts']['artifact_uid'] for a in r.get('artifacts', [])]


def test_index_keeps_the_uid_of_the_meta(cm, tmp_path):
    hand_made(cm, tmp_path, 'hand-made', UID)
    r = cm.access({'category': 'log', 'command': 'index', 'arg1': 'local:hand-made', 'con': False})
    assert r['return'] == 0, r.get('error')
    assert r['meta']['artifact'] == UID

    for ref in ('hand-made', f'hand-made,{UID}', UID):
        r = cm.access({'category': 'log', 'command': 'find', 'arg1': ref, 'con': False})
        assert r['return'] == 0, (ref, r.get('error'))
        assert uids(r) == [UID], ref


def test_index_takes_the_uid_of_an_alias_uid_meta(cm, tmp_path):
    hand_made(cm, tmp_path, 'with-alias', f'with-alias,{UID}')
    r = cm.access({'category': 'log', 'command': 'index', 'arg1': 'local:with-alias', 'con': False})
    assert r['return'] == 0, r.get('error')
    r = cm.access({'category': 'log', 'command': 'find', 'arg1': UID, 'con': False})
    assert r['return'] == 0 and uids(r) == [UID]


def test_index_ignores_an_artifact_value_that_is_no_uid(cm, tmp_path):
    # A hand-written "artifact: <alias>" is no UID: the index gives the artifact a new one
    hand_made(cm, tmp_path, 'no-uid', 'no-uid')
    r = cm.access({'category': 'log', 'command': 'index', 'arg1': 'local:no-uid', 'con': False})
    assert r['return'] == 0, r.get('error')
    r = cm.access({'category': 'log', 'command': 'find', 'arg1': 'no-uid', 'con': False})
    assert r['return'] == 0, r.get('error')
    found = uids(r)
    assert len(found) == 1 and found[0] != 'no-uid' and len(found[0]) == 16
