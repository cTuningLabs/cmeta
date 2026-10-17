"""
Integration tests of the incremental index with a registered repository nested inside another one - as the engine's
internal repository sits inside the repository that holds the engine's source tree (fgg.project/cMeta/cmeta on the
author's PC). An incremental index (plug, pull, unplug, reindex of one repository, a repository out of reach) removed
every record whose path lay inside the outer repository's folder, also the records of the nested repository, and the
outer repository's scan does not descend into it to bring them back: the cserver app was gone from the index until a
full reindex (2026-10-17). A record is now removed only when its own repository is indexed again or removed, and
"." (the current directory) names the deepest repository that holds it.

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import shutil

import pytest

from cmeta import CMeta

LOG = 'log,f1b42d8e3e1a4b50'


def make_repo(path, alias, uid):
    path.mkdir(parents=True, exist_ok=True)
    (path / '_cmr.yaml').write_text(f'artifact: {alias},{uid}\ncategory: repo,f4f792ab40c7498f\n', encoding='utf-8')


def make_note(repo, alias, uid):
    folder = repo / 'log' / alias
    folder.mkdir(parents=True)
    (folder / '_cmeta.yaml').write_text(f'artifact: {alias},{uid}\ncategory: {LOG}\n', encoding='utf-8')


def access(cm, **params):
    params.setdefault('con', False)
    return cm.access(params)


def found(cm, alias):
    return access(cm, category='log', command='find', arg1=alias)['return'] == 0


@pytest.fixture()
def env(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE',
                'CMETA_INTERNAL_REPO_PATH'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path / 'home'))
    return tmp_path


@pytest.fixture()
def nested(env):
    outer = env / 'outer'
    inner = outer / 'deep' / 'inner'
    other = env / 'other'
    make_repo(outer, 'outer', 'a1b2c3d4e5f60101')
    make_repo(inner, 'inner', 'a1b2c3d4e5f60102')
    make_repo(other, 'other', 'a1b2c3d4e5f60103')
    make_note(outer, 'outer-a', 'b1b2c3d4e5f60101')
    make_note(inner, 'inner-a', 'b1b2c3d4e5f60102')
    make_note(other, 'other-a', 'b1b2c3d4e5f60103')

    cm = CMeta(home=str(env / 'home'))
    for repo in (outer, inner, other):
        r = access(cm, category='repo', command='plug', arg1=str(repo))
        assert r['return'] == 0, r.get('error')
    assert found(cm, 'outer-a') and found(cm, 'inner-a') and found(cm, 'other-a')
    return cm, outer, inner, other


def test_reindex_of_the_outer_repository_keeps_the_inner_records(nested):
    cm, outer, inner, other = nested
    make_note(outer, 'outer-b', 'b1b2c3d4e5f60111')

    assert access(cm, category='repo', command='reindex', arg1='outer')['return'] == 0
    assert found(cm, 'inner-a')                                    # gone before the fix
    assert found(cm, 'outer-a') and found(cm, 'outer-b')           # the outer repository indexed again
    assert found(cm, 'other-a')


def test_reindex_of_the_inner_repository_refreshes_it_alone(nested):
    cm, outer, inner, other = nested
    shutil.rmtree(inner / 'log' / 'inner-a')
    make_note(inner, 'inner-b', 'b1b2c3d4e5f60112')

    assert access(cm, category='repo', command='reindex', arg1='inner')['return'] == 0
    assert not found(cm, 'inner-a') and found(cm, 'inner-b')       # its deleted artifact leaves, the new one comes
    assert found(cm, 'outer-a') and found(cm, 'other-a')


def test_plugging_the_outer_repository_after_the_inner_one(env):
    outer = env / 'outer'
    inner = outer / 'deep' / 'inner'
    make_repo(outer, 'outer', 'a1b2c3d4e5f60101')
    make_repo(inner, 'inner', 'a1b2c3d4e5f60102')
    make_note(outer, 'outer-a', 'b1b2c3d4e5f60101')
    make_note(inner, 'inner-a', 'b1b2c3d4e5f60102')

    cm = CMeta(home=str(env / 'home'))
    assert access(cm, category='repo', command='plug', arg1=str(inner))['return'] == 0
    assert access(cm, category='repo', command='plug', arg1=str(outer))['return'] == 0
    assert found(cm, 'inner-a') and found(cm, 'outer-a')


def test_unplugging_the_outer_repository_keeps_the_inner_one(nested):
    cm, outer, inner, other = nested

    assert access(cm, category='repo', command='unplug', arg1='outer')['return'] == 0
    assert not found(cm, 'outer-a')
    assert found(cm, 'inner-a') and found(cm, 'other-a')

    # and the other way round: the inner repository leaves alone
    assert access(cm, category='repo', command='plug', arg1=str(outer))['return'] == 0
    assert access(cm, category='repo', command='unplug', arg1='inner')['return'] == 0
    assert not found(cm, 'inner-a') and found(cm, 'outer-a')


def test_an_outer_repository_out_of_reach_keeps_the_inner_records(nested):
    cm, outer, inner, other = nested

    # outer's descriptor cannot be read: the next incremental index (here of another repository) takes outer's
    # records out of the index, but not those of the reachable repository nested in its folder
    os.rename(outer / '_cmr.yaml', outer / '_cmr.yaml.away')
    assert access(cm, category='repo', command='reindex', arg1='other')['return'] == 0
    assert not found(cm, 'outer-a')
    assert found(cm, 'inner-a') and found(cm, 'other-a')

    # back again: its records return with the next index run
    os.rename(outer / '_cmr.yaml.away', outer / '_cmr.yaml')
    assert access(cm, category='repo', command='reindex', arg1=str(outer))['return'] == 0
    assert found(cm, 'outer-a') and found(cm, 'inner-a')


def test_the_engine_internal_repository_inside_a_plugged_repository(env, monkeypatch):
    # The author's PC: the engine's source tree (with its internal repository) lies inside a plugged repository
    import cmeta
    source = os.path.join(os.path.dirname(os.path.abspath(cmeta.__file__)), 'internal-repo')
    outer = env / 'outer'
    make_repo(outer, 'outer', 'a1b2c3d4e5f60101')
    make_note(outer, 'outer-a', 'b1b2c3d4e5f60101')
    internal = outer / 'project' / 'cmeta' / 'internal-repo'
    shutil.copytree(source, internal, ignore=shutil.ignore_patterns('__pycache__'))
    monkeypatch.setenv('CMETA_INTERNAL_REPO_PATH', str(internal))

    cm = CMeta(home=str(env / 'home'))
    assert access(cm, category='repo', command='plug', arg1=str(outer))['return'] == 0
    assert access(cm, category='app', command='find', arg1='cserver')['return'] == 0

    for command in ('reindex', 'unplug'):
        r = access(cm, category='repo', command=command, arg1='outer')
        assert r['return'] == 0, r.get('error')
        assert access(cm, category='app', command='find', arg1='cserver')['return'] == 0, f'cserver lost after {command}'


def test_the_current_directory_names_the_nested_repository(nested):
    # "." (the artifact of the current directory) takes the deepest repository that holds it: the first one found
    # could be the outer repository, whose artifact was named instead
    from cmeta import utils
    cm, outer, inner, other = nested

    r = utils.common.detect_cid_in_the_current_directory(cm, path=str(inner / 'log' / 'inner-a'))
    assert r['return'] == 0, r.get('error')
    assert r['artifact_repo_name'].startswith('inner,') and r['artifact_alias'] == 'inner-a'

    r = utils.common.detect_cid_in_the_current_directory(cm, path=str(outer / 'log' / 'outer-a'))
    assert r['return'] == 0 and r['artifact_repo_name'].startswith('outer,') and r['artifact_alias'] == 'outer-a'
