"""
Integration tests of what `cx repo plug` / `init` may register. A bare `cx repo plug` plugs the current directory, and
typed in ~/CMETA/repos it registered the folder of the repositories itself as the repository "repos" (a `_cmr.yaml`
written there without a word, a P14s Gen 4, 2026-09-18): every other repository was nested in it. The folder of the
repositories of the home, and the home itself, are refused now - a folder further up is not: a project can hold its
own home (<project>/.venv/CMETA); a folder without a descriptor still becomes a repository, and says so. And a
descriptor with a category but no artifact gets its new name written (a typo kept it in memory only, and the next
index found a repository that "names no artifact").

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import json
import os

import pytest

from cmeta import CMeta


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE',
                'CMETA_INTERNAL_REPO_PATH'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path / 'home'))
    return CMeta(home=str(tmp_path / 'home'))


def access(cm, **params):
    params.setdefault('con', False)
    return cm.access(params)


def registered(cm):
    if not os.path.isfile(cm.repos_config_path):                         # a fresh home writes it at its first access
        access(cm, category='repo', command='find', arg1='*')
    with open(cm.repos_config_path, encoding='utf-8') as f:
        return [os.path.normcase(os.path.normpath(p)) for p in json.load(f)]


def test_the_folder_of_the_repositories_is_refused(cm, monkeypatch):
    repos = str(cm.repos_path)
    before = registered(cm)

    r = access(cm, category='repo', command='plug', arg1=repos)
    assert r['return'] > 0 and 'folder of the repositories' in r['error']

    # the bare plug typed in that folder, as on the P14s Gen 4
    monkeypatch.chdir(repos)
    r = access(cm, category='repo', command='plug')
    assert r['return'] > 0 and 'folder of the repositories' in r['error']

    assert not os.path.exists(os.path.join(repos, '_cmr.yaml'))          # nothing written there
    assert registered(cm) == before                                       # nothing registered


def test_the_home_is_refused(cm):
    home = os.path.dirname(str(cm.repos_path))                             # the cMeta home holds repos/
    r = access(cm, category='repo', command='plug', arg1=home)
    assert r['return'] > 0 and 'this cMeta home' in r['error']
    assert not os.path.exists(os.path.join(home, '_cmr.yaml'))


def test_a_project_that_holds_its_home_can_be_plugged(tmp_path, monkeypatch):
    # A project with its virtual environment inside it: the home is <project>/.venv/CMETA (VIRTUAL_ENV/CMETA), and the
    # project is a repository of its own - plugged as before, and an index of it keeps the home's local repository
    # nested in it
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE',
                'CMETA_INTERNAL_REPO_PATH'):
        monkeypatch.delenv(var, raising=False)
    project = tmp_path / 'project'
    (project / 'log' / 'project-note').mkdir(parents=True)
    (project / '_cmr.yaml').write_text('artifact: project,c1b2c3d4e5f60101\ncategory: repo,f4f792ab40c7498f\n', encoding='utf-8')
    (project / 'log' / 'project-note' / '_cmeta.yaml').write_text('artifact: project-note,d1b2c3d4e5f60101\n'
                                                                   'category: log,f1b42d8e3e1a4b50\n', encoding='utf-8')
    home = project / '.venv' / 'CMETA'
    monkeypatch.setenv('VIRTUAL_ENV', str(project / '.venv'))
    cm = CMeta()
    assert os.path.normcase(str(cm.repos_path)) == os.path.normcase(str(home / 'repos'))

    r = access(cm, category='repo', command='plug', arg1=str(project))
    assert r['return'] == 0, r.get('error')                               # refused by the first guard of 2026-10-17
    r = access(cm, category='log', command='create', arg1='local:local-note')
    assert r['return'] == 0, r.get('error')

    assert access(cm, category='repo', command='reindex', arg1='project')['return'] == 0
    for alias in ('project-note', 'local-note'):
        assert access(cm, category='log', command='find', arg1=alias)['return'] == 0, alias


def test_a_new_folder_still_becomes_a_repository_and_says_so(cm, tmp_path, capsys):
    folder = tmp_path / 'my-notes'
    folder.mkdir()

    r = access(cm, category='repo', command='plug', arg1=str(folder), con=True)
    assert r['return'] == 0, r.get('error')
    text = (folder / '_cmr.yaml').read_text(encoding='utf-8')
    assert 'artifact: my-notes,' in text and 'category: repo,' in text
    assert os.path.normcase(os.path.normpath(str(folder))) in registered(cm)
    assert 'has no _cmr.yaml: it becomes the repository "my-notes,' in capsys.readouterr().out

    # and init under the repositories folder, as before
    r = access(cm, category='repo', command='init', arg1='my-new-repo')
    assert r['return'] == 0, r.get('error')
    assert os.path.isfile(os.path.join(str(cm.repos_path), 'my-new-repo', '_cmr.yaml'))


def test_a_descriptor_without_an_artifact_gets_its_name_written(cm, tmp_path):
    folder = tmp_path / 'half'
    folder.mkdir()
    (folder / '_cmr.yaml').write_text('category: repo,f4f792ab40c7498f\n', encoding='utf-8')

    r = access(cm, category='repo', command='plug', arg1=str(folder))
    assert r['return'] == 0, r.get('error')
    assert 'artifact: half,' in (folder / '_cmr.yaml').read_text(encoding='utf-8')

    # a full index finds it (before: "names no artifact", the repository out of reach)
    assert access(cm, reindex=True)['return'] == 0
    assert access(cm, category='repo', command='find', arg1='half')['return'] == 0
