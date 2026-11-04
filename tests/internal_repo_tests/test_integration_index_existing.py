"""
Integration tests for indexing an artifact folder that already has its meta
(`cx <category> index <repo>:<name>`, for artifacts made or copied by hand):
the index takes the UID of the meta, so `alias,UID` and UID references resolve.
A category folder keeps the API code it came with.

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import pytest

from cmeta import CMeta

UID = '0123456789abcdef'

# The meta of a category as "cx category add" writes it, and a category's own API code with one command
CATEGORY_META = (f'artifact: {UID}\ncategory: category,dd9ea50e7f76467f\nlast_api_version: 1\n'
                 "base_category_default_api_versions:\n  '1': 1\n")
CATEGORY_API = ('from cmeta.category import InitCategory\n\n\n'
                'class Category(InitCategory):\n'
                '    def __init__(self, *args, **kwargs):\n'
                '        super().__init__(*args, module_file_path=__file__, **kwargs)\n\n'
                '    def hello_(self, ctx, **kwargs):\n'
                "        return {'return': 0, 'hello': 'its own code'}\n")


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


def category_folder(cm, tmp_path, name, meta=True, api=True):
    # The folder of a category as a sync or a hand brings it: its meta and its API code, or one of them
    cm.access({'category': 'category', 'command': 'find', 'arg1': 'nothing-yet', 'con': False})
    folder = tmp_path / 'repos' / 'local' / 'category' / name
    folder.mkdir(parents=True)
    if meta:
        (folder / '_cmeta.yaml').write_text(CATEGORY_META, encoding='utf-8')
    if api:
        (folder / 'api').mkdir()
        (folder / 'api' / 'v1.py').write_text(CATEGORY_API, encoding='utf-8')
    return folder


def test_index_of_a_category_keeps_its_api(cm, tmp_path):
    # Indexed under the UID of its meta, its own code kept and run, and no error: before, the record was
    # written and the call then failed with 'API file "..." already exists'
    folder = category_folder(cm, tmp_path, 'demo.synced')
    r = cm.access({'category': 'category', 'command': 'index', 'arg1': 'local:demo.synced', 'con': False})
    assert r['return'] == 0, r.get('error')
    assert r['meta']['artifact'] == UID
    assert (folder / 'api' / 'v1.py').read_text(encoding='utf-8') == CATEGORY_API

    r = cm.access({'category': 'category', 'command': 'find', 'arg1': 'demo.synced', 'con': False})
    assert r['return'] == 0 and uids(r) == [UID]

    r = cm.access({'category': 'demo.synced', 'command': 'hello', 'con': False})
    assert r['return'] == 0 and r['hello'] == 'its own code', r.get('error')

    # indexed already: refused as before
    r = cm.access({'category': 'category', 'command': 'index', 'arg1': 'local:demo.synced', 'con': False})
    assert r['return'] == 8


def test_index_of_a_category_without_api_makes_it(cm, tmp_path):
    # A meta alone: the API code is made from the template, as before
    folder = category_folder(cm, tmp_path, 'demo.bare', api=False)
    r = cm.access({'category': 'category', 'command': 'index', 'arg1': 'local:demo.bare', 'con': False})
    assert r['return'] == 0, r.get('error')
    assert 'class Category(InitCategory)' in (folder / 'api' / 'v1.py').read_text(encoding='utf-8')


def test_create_of_a_category_keeps_the_api_written_first(cm, tmp_path):
    # The code written before "cx category add": the meta is made, the code kept and run
    folder = category_folder(cm, tmp_path, 'demo.code-first', meta=False)
    r = cm.access({'category': 'category', 'command': 'create', 'arg1': 'local:demo.code-first', 'con': False})
    assert r['return'] == 0, r.get('error')
    assert (folder / '_cmeta.yaml').is_file()
    assert (folder / 'api' / 'v1.py').read_text(encoding='utf-8') == CATEGORY_API

    r = cm.access({'category': 'demo.code-first', 'command': 'hello', 'con': False})
    assert r['return'] == 0 and r['hello'] == 'its own code', r.get('error')
