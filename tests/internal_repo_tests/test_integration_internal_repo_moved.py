"""
Integration tests of a home indexed by one installation of the engine and then used by another one (its internal
repository at another path: a tool reinstalled onto another Python, a virtual environment made again, a second
install that uses the same home). The index kept the records of the first installation's internal repository until a
full reindex: once that installation was gone, "cx app find cserver" answered a folder that was not there; an
incremental index (a plug, a pull, the reindex of one repository) wrote this engine's internal repository into
repos.json and its categories into the index, but kept the other one's apps (2026-10-17). Now an incremental index
moves the records too, and a gone internal repository is replaced at the next start. With both installations there,
the start changes nothing (as before).

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import json
import os
import shutil

import pytest

from cmeta import CMeta


def access(cm, **params):
    params.setdefault('con', False)
    return cm.access(params)


def cserver_path(home):
    r = access(CMeta(home=home), category='app', command='find', arg1='cserver')
    assert r['return'] == 0, r.get('error')
    return os.path.normcase(os.path.normpath(r['artifacts'][0]['path']))


def under(path, folder):
    return path.startswith(os.path.normcase(os.path.normpath(str(folder))) + os.sep)


def registered(home):
    with open(os.path.join(home, 'repos.json'), encoding='utf-8') as f:
        return [os.path.normcase(os.path.normpath(p)) for p in json.load(f)]


@pytest.fixture()
def engines(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE',
                'CMETA_INTERNAL_REPO_PATH'):
        monkeypatch.delenv(var, raising=False)
    home = str(tmp_path / 'home')
    monkeypatch.setenv('CMETA_HOME', home)

    import cmeta
    source = os.path.join(os.path.dirname(os.path.abspath(cmeta.__file__)), 'internal-repo')
    a = tmp_path / 'engine-a' / 'internal-repo'
    b = tmp_path / 'engine-b' / 'internal-repo'
    for folder in (a, b):
        shutil.copytree(source, folder, ignore=shutil.ignore_patterns('__pycache__'))

    # the home is indexed by installation A
    monkeypatch.setenv('CMETA_INTERNAL_REPO_PATH', str(a))
    assert under(cserver_path(home), a)
    return home, a, b, monkeypatch


def test_a_gone_internal_repository_is_replaced_at_the_next_start(engines):
    home, a, b, monkeypatch = engines

    shutil.rmtree(a.parent)
    monkeypatch.setenv('CMETA_INTERNAL_REPO_PATH', str(b))

    path = cserver_path(home)
    assert under(path, b) and os.path.isdir(path)                  # before: a folder of A that was not there
    assert os.path.normcase(os.path.normpath(str(b))) in registered(home)
    assert os.path.normcase(os.path.normpath(str(a))) not in registered(home)


def test_an_incremental_index_moves_the_records_to_this_engine(engines):
    home, a, b, monkeypatch = engines
    monkeypatch.setenv('CMETA_INTERNAL_REPO_PATH', str(b))

    # both installations there: the start changes nothing
    assert under(cserver_path(home), a)

    # an incremental index by B: repos.json, the categories and the apps name B's internal repository
    r = access(CMeta(home=home), category='repo', command='reindex', arg1='local')
    assert r['return'] == 0, r.get('error')
    assert under(cserver_path(home), b)                            # before: still A's
    r = access(CMeta(home=home), category='category', command='find', arg1='repo')
    assert r['return'] == 0 and under(os.path.normcase(r['artifacts'][0]['path']), b)
    assert os.path.normcase(os.path.normpath(str(b))) in registered(home)


def test_the_same_engine_does_not_index_again_at_start(engines):
    home, a, b, monkeypatch = engines
    app_index = os.path.join(home, 'index', 'app.pkl')
    before = os.stat(app_index).st_mtime_ns

    # the same internal repository, named another way (a trailing separator; on Windows another case)
    monkeypatch.setenv('CMETA_INTERNAL_REPO_PATH', str(a) + os.sep)
    assert under(cserver_path(home), a)
    assert os.stat(app_index).st_mtime_ns == before
