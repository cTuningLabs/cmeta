"""
Integration tests of what `cx repo plug` / `init` may register. A bare `cx repo plug` plugs the current directory, and
typed in ~/CMETA/repos it registered the folder of the repositories itself as the repository "repos" (a `_cmr.yaml`
written there without a word, a P14s Gen 4, 2026-09-18): every other repository was nested in it. The folder of the
repositories of the home, and a folder that holds it, are refused now; a folder without a descriptor still becomes a
repository, and says so. And a descriptor with a category but no artifact gets its new name written (a typo kept it in
memory only, and the next index found a repository that "names no artifact").

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


def test_a_folder_that_holds_the_repositories_is_refused(cm):
    home = os.path.dirname(str(cm.repos_path))                             # the cMeta home holds repos/
    r = access(cm, category='repo', command='plug', arg1=home)
    assert r['return'] > 0 and 'or holds it' in r['error']
    assert not os.path.exists(os.path.join(home, '_cmr.yaml'))


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
