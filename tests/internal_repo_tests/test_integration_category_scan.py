"""
Integration tests of what an incremental index scans for the categories a repository declares. A category can have
artifacts in repositories plugged before it was known, so when a repository that declares a category arrives, every
repository is scanned for that category (since 2026-06-11). Since 2026-10-17 that scan runs only for a category new
to the index or changed (its folder or its meta): an index run of the declaring repository leaves the other
repositories alone otherwise - `cx repo pull cmeta-aops` cost a full reindex before - and a repository whose folders
changed is indexed again on its own, as `cx repo reindex <repository>` promises.

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import pickle

import pytest

from cmeta import CMeta

CATEGORY = 'cat-x'
CATEGORY_UID = 'c1b2c3d4e5f60001'


def make_repo(path, alias, uid, declare_category=False):
    path.mkdir(parents=True, exist_ok=True)
    (path / '_cmr.yaml').write_text(f'artifact: {alias},{uid}\ncategory: repo,f4f792ab40c7498f\n', encoding='utf-8')

    if declare_category:
        folder = path / 'category' / CATEGORY
        folder.mkdir(parents=True)
        (folder / '_cmeta.yaml').write_text(f'artifact: {CATEGORY},{CATEGORY_UID}\ncategory: category,dd9ea50e7f76467f\n', encoding='utf-8')


def make_artifact(repo, alias, uid):
    folder = repo / CATEGORY / alias
    folder.mkdir(parents=True)
    (folder / '_cmeta.yaml').write_text(f'artifact: {alias},{uid}\ncategory: {CATEGORY},{CATEGORY_UID}\n', encoding='utf-8')


def access(cm, **params):
    params.setdefault('con', False)
    return cm.access(params)


def found(cm, alias):
    r = access(cm, category=CATEGORY, command='find', arg1=alias)
    return r['return'] == 0 and len(r['artifacts']) == 1


def records(home):
    """{uid: (repository uid, path, mtime of the record's meta as pickled)} of the category's index file."""
    with open(os.path.join(home, 'index', CATEGORY + '.pkl'), 'rb') as f:
        data = pickle.load(f)
    return {uid: (rec['cmeta_ref_parts'].get('repo_uid'), rec['path'], repr(rec['cmeta'])) for uid, rec in data['uids'].items()}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE',
                'CMETA_INTERNAL_REPO_PATH'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path / 'home'))
    return tmp_path


def test_a_category_that_arrives_later_indexes_the_artifacts_other_repositories_hold(env):
    # b holds artifacts of a category nobody declares yet; a arrives with the declaration: b's artifacts are indexed
    a = env / 'a'
    b = env / 'b'
    make_repo(a, 'a', 'a1b2c3d4e5f60301', declare_category=True)
    make_repo(b, 'b', 'a1b2c3d4e5f60302')
    make_artifact(b, 'b-0', 'b1b2c3d4e5f60302')

    cm = CMeta(home=str(env / 'home'))
    assert access(cm, category='repo', command='plug', arg1=str(b))['return'] == 0
    assert access(cm, category=CATEGORY, command='find', arg1='b-0')['return'] > 0       # the category is unknown
    assert access(cm, category='repo', command='plug', arg1=str(a))['return'] == 0
    assert found(cm, 'b-0')


@pytest.fixture()
def declared(env):
    """a declares the category and holds one artifact of it; b holds two; both indexed."""
    a = env / 'a'
    b = env / 'b'
    make_repo(a, 'a', 'a1b2c3d4e5f60301', declare_category=True)
    make_repo(b, 'b', 'a1b2c3d4e5f60302')
    make_artifact(a, 'a-0', 'b1b2c3d4e5f60301')
    make_artifact(b, 'b-0', 'b1b2c3d4e5f60302')
    make_artifact(b, 'b-1', 'b1b2c3d4e5f60312')

    cm = CMeta(home=str(env / 'home'))
    for repo in (a, b):
        assert access(cm, category='repo', command='plug', arg1=str(repo))['return'] == 0
    assert found(cm, 'a-0') and found(cm, 'b-0') and found(cm, 'b-1')
    return cm, a, b, str(env / 'home')


def test_the_index_run_of_the_declaring_repository_leaves_the_other_repositories_alone(declared):
    cm, a, b, home = declared
    before = records(home)

    # b's folders change outside cMeta: a new artifact, a changed meta. The index run of a does not look there
    # (it scanned every repository for the category before): b is indexed again on its own
    make_artifact(b, 'b-new', 'b1b2c3d4e5f60322')
    (b / CATEGORY / 'b-0' / '_cmeta.yaml').write_text(f'artifact: b-0,b1b2c3d4e5f60302\ncategory: {CATEGORY},{CATEGORY_UID}\ndesc: changed\n', encoding='utf-8')

    assert access(cm, category='repo', command='reindex', arg1='a')['return'] == 0
    assert not found(cm, 'b-new')
    assert records(home) == before                                      # not one record of b changed

    assert access(cm, category='repo', command='reindex', arg1='b')['return'] == 0
    assert found(cm, 'b-new')
    r = access(cm, category=CATEGORY, command='find', arg1='b-0')
    assert r['return'] == 0 and r['artifacts'][0]['cmeta'].get('desc') == 'changed'


def test_a_changed_category_scans_the_other_repositories_again(declared):
    cm, a, b, home = declared

    # the category's meta changes in a (here a new key): the next index run of a scans every repository for it
    (a / 'category' / CATEGORY / '_cmeta.yaml').write_text(f'artifact: {CATEGORY},{CATEGORY_UID}\ncategory: category,dd9ea50e7f76467f\ndesc: changed\n', encoding='utf-8')
    make_artifact(b, 'b-new', 'b1b2c3d4e5f60322')

    assert access(cm, category='repo', command='reindex', arg1='a')['return'] == 0
    assert found(cm, 'b-new') and found(cm, 'b-0') and found(cm, 'a-0')

    # unchanged from now on: the next run of a leaves b alone again
    make_artifact(b, 'b-newer', 'b1b2c3d4e5f60332')
    assert access(cm, category='repo', command='reindex', arg1='a')['return'] == 0
    assert not found(cm, 'b-newer')


def test_a_full_reindex_and_a_plug_still_see_everything(declared):
    cm, a, b, home = declared
    make_artifact(b, 'b-new', 'b1b2c3d4e5f60322')

    # a repository plugged is scanned for every known category, a full rebuild for everything
    c = b.parent / 'c'
    make_repo(c, 'c', 'a1b2c3d4e5f60303')
    make_artifact(c, 'c-0', 'b1b2c3d4e5f60303')
    assert access(cm, category='repo', command='plug', arg1=str(c))['return'] == 0
    assert found(cm, 'c-0') and not found(cm, 'b-new')

    assert cm.repos.reindex()['return'] == 0
    assert found(cm, 'b-new') and found(cm, 'c-0') and found(cm, 'a-0')
