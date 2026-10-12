"""
Integration tests for a registered repository whose folder cannot be reached when the index is built - a detached
drive, a share that is down, a descriptor that cannot be read: it stays registered (repos.json keeps its line,
marked "unreachable"), is left out of the index with a notice, comes back by itself with the next index run once
its folder is there again, and can be forgotten by its path with `cx repo unplug <path>`. Before, the repository
was dropped from repos.json without a word and had to be plugged again.

Each test runs against a fresh <CMETA_HOME> in tmp_path so it does not touch the user's real cMeta state.

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import json
import os
import pickle

import pytest

from cmeta import CMeta


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX',
                'CMETA_DEBUG', 'CMETA_VERBOSE', 'CMETA_FAIL_ON_ERROR'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    return CMeta(home=str(tmp_path))


def access(cm, **params):
    params.setdefault('con', False)
    return cm.access(params)


def make_repo(tmp_path, name, repo_uid, where='extra'):
    repo = tmp_path / where / name
    repo.mkdir(parents=True)
    (repo / '_cmr.yaml').write_text(f'artifact: {name},{repo_uid}\ncategory: repo,f4f792ab40c7498f\n', encoding='utf-8')
    return repo


def plug(cm, repo, **params):
    r = access(cm, category='repo', command='plug', arg1=str(repo), **params)
    assert r['return'] == 0, r.get('error')


def make(cm, alias, repo, category='log', **meta):
    r = access(cm, category=category, command='create', arg1=f'{repo}:{alias}', meta=meta, yaml=True)
    assert r['return'] == 0, r.get('error')
    return r['meta']['artifact']


def find(cm, ref=None, category='log', **params):
    return access(cm, category=category, command='find', arg1=ref, **params)


def uids(r):
    return sorted(a['cmeta_ref_parts']['artifact_uid'] for a in r.get('artifacts', []))


def repos_json(tmp_path):
    return json.loads((tmp_path / 'repos.json').read_text(encoding='utf-8'))


def same(path):
    return os.path.normcase(os.path.normpath(str(path)))


def registered(tmp_path, repo):
    """The entry of a repository in repos.json (None when it is not listed)."""
    for path, entry in repos_json(tmp_path).items():
        if same(path) == same(repo):
            return entry
    return None


def marked(tmp_path, repo):
    """True / False: the repository is listed, with / without the "unreachable" mark. None: it is not listed."""
    entry = registered(tmp_path, repo)
    return None if entry is None else bool(entry.get('unreachable'))


def index_data(tmp_path, category):
    with open(tmp_path / 'index' / f'{category}.pkl', 'rb') as f:
        return pickle.load(f)


def reindex_all(cm, **params):
    r = cm.repos.index(clean=True, **params)
    assert r['return'] == 0, r.get('error')


def detach(repo):
    away = repo.with_name(repo.name + '-detached')
    repo.rename(away)
    return away


def test_an_unreachable_repository_stays_registered_and_comes_back(cm, tmp_path, capsys):
    repo = make_repo(tmp_path, 'mine', '1111111111111111')
    other = make_repo(tmp_path, 'other', '2222222222222222')
    plug(cm, repo)
    plug(cm, other)
    uid = make(cm, 'on-the-drive', 'mine')
    other_uid = make(cm, 'elsewhere', 'other')
    order = [same(p) for p in repos_json(tmp_path)]

    away = detach(repo)

    # A full reindex while the drive is away: the line stays where it was, marked; a notice says what to do
    reindex_all(cm, con=True)
    captured = capsys.readouterr()
    out = captured.out
    assert 'cMeta warning: repository' in out and 'cannot be reached' in out and 'cx repo unplug' in out and str(repo) in out
    assert 'cannot be reached' not in captured.err      # a warning, not an error: nothing on stderr
    assert [same(p) for p in repos_json(tmp_path)] == order
    assert marked(tmp_path, repo) is True
    assert marked(tmp_path, other) is False
    assert access(cm, category='repo', command='find', arg1='mine')['return'] == 16
    assert find(cm, 'on-the-drive')['return'] == 16
    assert uids(find(cm, 'elsewhere')) == [other_uid]

    # ... and again: nothing changes, the file is not rewritten for it
    before = (tmp_path / 'repos.json').read_bytes()
    reindex_all(cm)
    assert (tmp_path / 'repos.json').read_bytes() == before
    assert 'cannot be reached' not in capsys.readouterr().out        # without the console, the warning goes to the log only

    # The drive is back: the next index run - of any kind - indexes it again and clears the mark
    away.rename(repo)
    reindex_all(cm)
    assert marked(tmp_path, repo) is False
    assert [same(p) for p in repos_json(tmp_path)] == order
    assert uids(find(cm, 'on-the-drive')) == [uid]
    assert access(cm, category='repo', command='find', arg1='mine')['return'] == 0


def test_an_incremental_index_drops_its_records_and_brings_them_back(cm, tmp_path):
    repo = make_repo(tmp_path, 'mine', '1111111111111111')
    plug(cm, repo)
    uid = make(cm, 'on-the-drive', 'mine')
    local_uid = make(cm, 'in-local', 'local')

    away = detach(repo)

    # The incremental index of another operation (here: a third repository is plugged) notices it: registered,
    # marked, and its records are out of the index - a find must not hand out artifacts whose folder is away
    third = make_repo(tmp_path, 'third', '3333333333333333')
    plug(cm, third)
    assert marked(tmp_path, repo) is True
    assert find(cm, 'on-the-drive')['return'] == 16
    assert uid not in index_data(tmp_path, 'log')['uids']
    assert uids(find(cm, 'in-local')) == [local_uid]

    # Back, and another incremental operation runs (a fourth repository is plugged): the repository is indexed
    # with it, although nobody named it
    away.rename(repo)
    fourth = make_repo(tmp_path, 'fourth', '4444444444444444')
    plug(cm, fourth)
    assert marked(tmp_path, repo) is False
    assert uids(find(cm, 'on-the-drive')) == [uid]
    assert uids(find(cm, 'in-local')) == [local_uid]
    assert access(cm, category='repo', command='find', arg1='mine')['return'] == 0


def test_repo_reindex_by_its_path_brings_an_unindexed_repository_back(cm, tmp_path, monkeypatch):
    repo = make_repo(tmp_path, 'mine', '1111111111111111')
    plug(cm, repo)
    uid = make(cm, 'on-the-drive', 'mine')
    away = detach(repo)
    reindex_all(cm)
    assert marked(tmp_path, repo) is True

    # Still away: refused, nothing changes
    r = access(cm, category='repo', command='reindex', arg1=str(repo))
    assert r['return'] > 0
    assert marked(tmp_path, repo) is True

    away.rename(repo)
    r = access(cm, category='repo', command='reindex', arg1=str(repo))       # not by its alias: the index does not know it
    assert r['return'] == 0, r.get('error')
    assert [same(p) for p in r['paths']] == [same(repo)] and r['artifacts'] == []
    assert marked(tmp_path, repo) is False
    assert uids(find(cm, 'on-the-drive')) == [uid]

    # ... also from inside it
    detached_again = detach(repo)
    reindex_all(cm)
    detached_again.rename(repo)
    monkeypatch.chdir(repo / 'log')
    r = access(cm, category='repo', command='reindex', arg1='.')
    assert r['return'] == 0, r.get('error')
    assert uids(find(cm, 'on-the-drive')) == [uid]


def test_unplug_by_path_forgets_an_unreachable_repository(cm, tmp_path, capsys):
    repo = make_repo(tmp_path, 'mine', '1111111111111111')
    other = make_repo(tmp_path, 'other', '2222222222222222')
    plug(cm, repo)
    plug(cm, other)
    make(cm, 'on-the-drive', 'mine')
    other_uid = make(cm, 'elsewhere', 'other')
    away = detach(repo)
    reindex_all(cm)

    # By its alias it is not known any more; by its path it is forgotten
    assert access(cm, category='repo', command='unplug', arg1='mine')['return'] == 16
    assert marked(tmp_path, repo) is True
    r = access(cm, category='repo', command='unplug', arg1=str(repo), con=True)
    assert r['return'] == 0, r.get('error')
    assert [same(p) for p in r['unregistered_paths']] == [same(repo)] and r['deleted_artifacts'] == []
    assert 'Unregistered' in capsys.readouterr().out
    assert registered(tmp_path, repo) is None
    assert marked(tmp_path, other) is False and uids(find(cm, 'elsewhere')) == [other_uid]
    assert away.is_dir() and (away / 'log' / 'on-the-drive').is_dir()      # the folder is nobody's business

    # A folder that is no registered repository is still "not found", and a folder inside one does not unplug it
    assert access(cm, category='repo', command='unplug', arg1=str(tmp_path / 'extra'))['return'] == 16
    assert access(cm, category='repo', command='unplug', arg1=str(other / 'log'))['return'] == 16
    assert marked(tmp_path, other) is False

    # A reachable, indexed repository can be unplugged by its path too
    r = access(cm, category='repo', command='unplug', arg1=str(other))
    assert r['return'] == 0, r.get('error')
    assert registered(tmp_path, other) is None and find(cm, 'elsewhere')['return'] == 16
    assert other.is_dir()


def test_plugging_it_again_is_not_needed_but_works(cm, tmp_path):
    repo = make_repo(tmp_path, 'mine', '1111111111111111')
    plug(cm, repo)
    uid = make(cm, 'on-the-drive', 'mine')
    away = detach(repo)
    reindex_all(cm)
    away.rename(repo)

    plug(cm, repo)                       # the old habit after a drive came back
    assert marked(tmp_path, repo) is False
    assert len([p for p in repos_json(tmp_path) if same(p) == same(repo)]) == 1
    assert uids(find(cm, 'on-the-drive')) == [uid]


def test_a_descriptor_that_cannot_be_read_does_not_unregister_the_repository(cm, tmp_path, capsys):
    repo = make_repo(tmp_path, 'mine', '1111111111111111')
    plug(cm, repo)
    uid = make(cm, 'art', 'mine')
    descriptor = repo / '_cmr.yaml'
    good = descriptor.read_text(encoding='utf-8')

    for broken, why in (('artifact: [unclosed\n', 'cannot be read'), ('category: repo,f4f792ab40c7498f\n', 'names no artifact')):
        descriptor.write_text(broken, encoding='utf-8')                # a slip while editing it by hand
        reindex_all(cm, con=True)
        assert why in capsys.readouterr().out
        assert marked(tmp_path, repo) is True
        assert find(cm, 'art')['return'] == 16

        descriptor.write_text(good, encoding='utf-8')
        reindex_all(cm)
        assert marked(tmp_path, repo) is False
        assert uids(find(cm, 'art')) == [uid]


def test_a_kept_repository_keeps_its_stored_descriptor_through_rewrites(cm, tmp_path):
    """`cx repo plug --keep` stores the descriptor of a repository on a removable drive, so that it stays in the
    repository index while the drive is away. The stored copy must survive a rewrite of repos.json made while the
    repository is reachable (it was left out then, and the next time the drive was away the repository was dropped)."""
    kept = make_repo(tmp_path, 'on-usb', '1111111111111111')
    plug(cm, kept, keep=True)
    assert registered(tmp_path, kept)['keep_repo_meta']['artifact'] == 'on-usb,1111111111111111'

    # another repository goes away and comes back: repos.json is rewritten twice while the kept one is reachable
    other = make_repo(tmp_path, 'other', '2222222222222222')
    plug(cm, other)
    away = detach(other)
    reindex_all(cm)
    away.rename(other)
    reindex_all(cm)
    assert registered(tmp_path, kept)['keep_repo_meta']['artifact'] == 'on-usb,1111111111111111'

    # the drive of the kept repository is away: still registered, still in the repository index, never "unreachable"
    kept_away = detach(kept)
    reindex_all(cm)
    entry = registered(tmp_path, kept)
    assert entry['meta']['keep'] is True and 'unreachable' not in entry
    assert access(cm, category='repo', command='find', arg1='on-usb')['return'] == 0
    kept_away.rename(kept)


def test_the_lines_of_repos_json_keep_their_order_and_only_the_mark_is_added(cm, tmp_path):
    repo = make_repo(tmp_path, 'mine', '1111111111111111')
    plug(cm, repo)
    before = repos_json(tmp_path)
    assert len(before) >= 2                                    # the internal repository, local, mine

    away = detach(repo)
    reindex_all(cm)
    after = repos_json(tmp_path)
    assert list(after) == list(before)                         # the same lines in the same order
    for path in before:
        expected = dict(before[path], unreachable=True) if same(path) == same(repo) else before[path]
        assert after[path] == expected, path

    away.rename(repo)
    reindex_all(cm)
    assert repos_json(tmp_path) == before and list(repos_json(tmp_path)) == list(before)      # and back to what it was
