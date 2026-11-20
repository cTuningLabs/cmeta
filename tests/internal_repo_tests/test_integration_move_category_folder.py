"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

Integration tests for the category folder of a rename (`cx <category> move <artifact> <new alias>`, `migrate`,
`copy` within one repository): it is the folder create_ makes - the full path of the artifact's repository (its
subdir included) joined with the category alias, the shard folders below it - never a folder guessed from the
names of the path. Until 2026-11-19 it was the first folder of the path named like the category: a repository
inside another one's folder of that name (a test home inside a log:: artifact) lost its renamed artifact to the
outer folder, and a repository or a shard folder named like the category would have misled any guess by name.
"""

import os

import pytest

from cmeta import CMeta
from cmeta import repos as cmeta_repos

CATEGORY_UID = 'fedcba9876543210'


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX',
                'CMETA_DEBUG', 'CMETA_VERBOSE', 'CMETA_FAIL_ON_ERROR'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path / 'home'))
    monkeypatch.setattr(cmeta_repos, '_migrated_notices', set())
    return CMeta(home=str(tmp_path / 'home'))


def access(cm, **params):
    params.setdefault('con', False)
    return cm.access(params)


def make(cm, alias, category='log', repo='local'):
    r = access(cm, category=category, command='create', arg1=f'{repo}:{alias}', yaml=True)
    assert r['return'] == 0, r.get('error')
    return r['meta']['artifact']


def find(cm, ref, category='log', **params):
    return access(cm, category=category, command='find', arg1=ref, **params)


def path_of(cm, ref, category='log'):
    r = find(cm, ref, category=category)
    assert r['return'] == 0 and len(r['artifacts']) == 1, r
    return os.path.normcase(os.path.normpath(r['artifacts'][0]['path']))


def same(path):
    return os.path.normcase(os.path.normpath(str(path)))


def plug(cm, repo):
    r = access(cm, category='repo', command='plug', arg1=str(repo))
    assert r['return'] == 0, r.get('error')


def category_repo(tmp_path, name, repo_uid, category_meta_extra):
    """A repository named like the category of its own it holds (`ab`), the category's meta given."""
    repo = tmp_path / 'extra' / name
    category = repo / 'category' / name
    (category / 'api').mkdir(parents=True)
    (repo / '_cmr.yaml').write_text(f'artifact: {name},{repo_uid}\ncategory: repo,f4f792ab40c7498f\n', encoding='utf-8')
    (category / '_cmeta.yaml').write_text(f'artifact: {name},{CATEGORY_UID}\ncategory: category,dd9ea50e7f76467f\n'
                                          'last_api_version: 1\nbase_category_default_api_versions:\n  "1": 1\n' + category_meta_extra,
                                          encoding='utf-8')
    (category / 'api' / 'v1.py').write_text('from cmeta.category import InitCategory\n\nclass Category(InitCategory):\n'
                                            '    def __init__(self, *args, **kwargs):\n'
                                            '        super().__init__(*args, module_file_path = __file__, **kwargs)\n', encoding='utf-8')
    return repo


def listing(folder):
    """Every path under a folder, relative, sorted - what a rename may have left or made."""
    out = []
    for root, dirs, files in os.walk(folder):
        for n in dirs + files:
            out.append(os.path.relpath(os.path.join(root, n), folder).replace(os.sep, '/'))
    return sorted(out)


##########################################################################################
# A sharded category whose shard folder, category folder and repository folder all carry one name

@pytest.mark.parametrize('command', ['move', 'migrate'])
def test_a_rename_in_a_sharded_category_named_like_its_shards_and_its_repository(cm, tmp_path, command):
    repo = category_repo(tmp_path, 'ab', '3333333333333333', 'sharding_slices:\n- 2\n')
    plug(cm, repo)
    uid = make(cm, 'abcdef', category='ab', repo='ab')

    # .../extra/ab (the repository) / ab (the category) / ab (the shard) / abcdef: the first "ab" is the
    # repository's folder, the last the shard's - only the middle one is the category's
    assert path_of(cm, 'abcdef', category='ab') == same(repo / 'ab' / 'ab' / 'abcdef')

    r = access(cm, category='ab', command=command, arg1='abcdef', arg2='xyzdef')
    assert r['return'] == 0, r.get('error')

    assert path_of(cm, 'xyzdef', category='ab') == same(repo / 'ab' / 'xy' / 'xyzdef')
    assert find(cm, 'xyzdef', category='ab')['artifacts'][0]['cmeta_ref_parts']['artifact_uid'] == uid
    tree = listing(repo / 'ab')
    if command == 'move':
        assert tree == ['xy', 'xy/xyzdef', 'xy/xyzdef/_cmeta.yaml']                 # the empty "ab" shard removed
    else:
        assert 'ab/abcdef/_cmeta.yaml' in tree and 'xy/xyzdef/_cmeta.yaml' in tree   # the stub under the old name
    assert sorted(os.listdir(repo)) == ['_cmr.yaml', 'ab', 'category']                 # nothing beside the category


def test_a_copy_in_that_sharded_category(cm, tmp_path):
    repo = category_repo(tmp_path, 'ab', '3333333333333333', 'sharding_slices:\n- 2\n')
    plug(cm, repo)
    make(cm, 'abcdef', category='ab', repo='ab')

    r = access(cm, category='ab', command='copy', arg1='abcdef', arg2='abzzzz')
    assert r['return'] == 0, r.get('error')
    assert path_of(cm, 'abzzzz', category='ab') == same(repo / 'ab' / 'ab' / 'abzzzz')
    assert path_of(cm, 'abcdef', category='ab') == same(repo / 'ab' / 'ab' / 'abcdef')
    assert sorted(os.listdir(repo)) == ['_cmr.yaml', 'ab', 'category']


##########################################################################################
# A repository with a subdir, a home inside a folder named like the category, another repository

def test_a_rename_in_a_repository_with_a_subdir(cm, tmp_path):
    repo = tmp_path / 'extra' / 'log' / 'withsub'          # the repository itself sits in a folder named "log"
    (repo / 'content').mkdir(parents=True)
    (repo / '_cmr.yaml').write_text('artifact: withsub,6666666666666666\ncategory: repo,f4f792ab40c7498f\nsubdir: content\n',
                                    encoding='utf-8')
    plug(cm, repo)
    make(cm, 'in-sub', repo='withsub')

    r = access(cm, category='log', command='move', arg1='withsub:in-sub', arg2='in-sub-2')
    assert r['return'] == 0, r.get('error')
    assert path_of(cm, 'in-sub-2') == same(repo / 'content' / 'log' / 'in-sub-2')
    assert sorted(os.listdir(tmp_path / 'extra' / 'log')) == ['withsub']                # nothing in the outer "log"


def test_a_move_to_another_repository_is_as_before(cm, tmp_path):
    other = tmp_path / 'extra' / 'other'
    other.mkdir(parents=True)
    (other / '_cmr.yaml').write_text('artifact: other,7777777777777777\ncategory: repo,f4f792ab40c7498f\n', encoding='utf-8')
    plug(cm, other)
    uid = make(cm, 'traveller')

    # into the other repository under the same alias, then back under a new one
    r = access(cm, category='log', command='move', arg1='traveller', arg2='other:')
    assert r['return'] == 0, r.get('error')
    assert path_of(cm, uid) == same(other / 'log' / 'traveller')

    r = access(cm, category='log', command='move', arg1=uid, arg2='local:back-home')
    assert r['return'] == 0, r.get('error')
    assert path_of(cm, uid) == same(tmp_path / 'home' / 'repos' / 'local' / 'log' / 'back-home')
    assert not (other / 'log' / 'traveller').exists()


def test_a_rename_into_a_name_that_exists_is_refused_as_before(cm):
    make(cm, 'one')
    make(cm, 'two')
    r = access(cm, category='log', command='move', arg1='one', arg2='two')
    assert r['return'] > 0 and 'already exists' in r['error']
    assert find(cm, 'one')['return'] == 0 and find(cm, 'two')['return'] == 0


def test_an_artifact_outside_its_category_folder_is_an_error_that_moves_nothing(cm, tmp_path, monkeypatch):
    # No second way of finding the folder: when the artifact does not lie in <its repository>/<category>, the
    # rename stops with an error and leaves everything where it was
    make(cm, 'stays')
    before = listing(tmp_path)
    elsewhere = tmp_path / 'elsewhere'
    original = cm.repos.find

    def find_elsewhere(ref, *args, **kwargs):
        r = original(ref, *args, **kwargs)
        if r.get('return') == 0 and ref.get('category_alias') == 'repo':
            r = dict(r, artifacts=[dict(a, full_path=str(elsewhere)) for a in r['artifacts']])
        return r

    monkeypatch.setattr(cm.repos, 'find', find_elsewhere)
    r = access(cm, category='log', command='move', arg1='stays', arg2='renamed')
    monkeypatch.setattr(cm.repos, 'find', original)

    assert r['return'] > 0 and 'is not in the folder of its category' in r['error'], r
    assert listing(tmp_path) == before
    assert find(cm, 'stays')['return'] == 0 and find(cm, 'renamed')['return'] == 16


##########################################################################################
# More corners: a category found by scan, a repository's own sharding, another repository, several artifacts, "."

def plain_repo(tmp_path, name, uid, extra=''):
    repo = tmp_path / 'extra' / name
    repo.mkdir(parents=True)
    (repo / '_cmr.yaml').write_text(f'artifact: {name},{uid}\ncategory: repo,f4f792ab40c7498f\n{extra}', encoding='utf-8')
    return repo


def test_a_rename_in_a_category_without_an_index(cm, tmp_path):
    # no_index: its artifacts are found by a scan of the folders, their repository comes with them
    repo = category_repo(tmp_path, 'noidx', '4444444444444444', 'no_index: true\n')
    plug(cm, repo)
    uid = make(cm, 'scanned', category='noidx', repo='noidx')

    r = access(cm, category='noidx', command='move', arg1='scanned', arg2='renamed')
    assert r['return'] == 0, r.get('error')
    assert path_of(cm, 'renamed', category='noidx') == same(repo / 'noidx' / 'renamed')
    assert find(cm, 'renamed', category='noidx')['artifacts'][0]['cmeta_ref_parts']['artifact_uid'] == uid
    assert find(cm, 'scanned', category='noidx')['return'] == 16
    assert sorted(os.listdir(repo / 'noidx')) == ['renamed']


def test_a_repository_with_its_own_sharding_of_a_category(cm, tmp_path):
    # the repository's _cmr.yaml shards the category `log` (the category itself does not): a rename there moves the
    # artifact to the shard of its new name; a move to a repository without sharding and back follows each one's rule
    repo = plain_repo(tmp_path, 'sharded', '8888888888888888', 'sharding_slices:\n  487a7639093a4685: [2]\n')
    plug(cm, repo)
    uid = make(cm, 'abcdef', repo='sharded')
    assert path_of(cm, uid) == same(repo / 'log' / 'ab' / 'abcdef')

    r = access(cm, category='log', command='move', arg1='sharded:abcdef', arg2='xyzdef')
    assert r['return'] == 0, r.get('error')
    assert path_of(cm, uid) == same(repo / 'log' / 'xy' / 'xyzdef')

    r = access(cm, category='log', command='move', arg1=uid, arg2='local:')
    assert r['return'] == 0, r.get('error')
    assert path_of(cm, uid) == same(tmp_path / 'home' / 'repos' / 'local' / 'log' / 'xyzdef')

    r = access(cm, category='log', command='move', arg1=uid, arg2='sharded:back')
    assert r['return'] == 0, r.get('error')
    assert path_of(cm, uid) == same(repo / 'log' / 'ba' / 'back')
    assert not (tmp_path / 'home' / 'repos' / 'local' / 'log' / 'xyzdef').exists()
    assert listing(repo / 'log') == ['ba', 'ba/back', 'ba/back/_cmeta.yaml']          # no emptied shard folder is left


def test_a_migration_into_another_repository(cm, tmp_path):
    other = plain_repo(tmp_path, 'other', '7777777777777777')
    plug(cm, other)
    uid = make(cm, 'old-name')

    r = access(cm, category='log', command='migrate', arg1='old-name', arg2='other:new-name')
    assert r['return'] == 0, r.get('error')
    assert path_of(cm, uid) == same(other / 'log' / 'new-name')

    # the stub stays where the artifact was, under the old alias, and leads to it
    local_log = tmp_path / 'home' / 'repos' / 'local' / 'log'
    assert sorted(os.listdir(local_log)) == ['old-name']
    stub = find(cm, 'old-name', follow_migrated=False)['artifacts'][0]
    assert stub['cmeta']['migrated_to'] == f'new-name,{uid}' and same(stub['path']) == same(local_log / 'old-name')
    assert find(cm, 'old-name')['artifacts'][0]['cmeta_ref_parts']['artifact_uid'] == uid


def test_several_artifacts_moved_into_another_repository(cm, tmp_path):
    other = plain_repo(tmp_path, 'other', '7777777777777777')
    plug(cm, other)
    made = {name: make(cm, name) for name in ('w-one', 'w-two', 'stays')}

    r = access(cm, category='log', command='move', arg1='w-*', arg2='other:')
    assert r['return'] == 0, r.get('error')
    assert sorted(os.listdir(other / 'log')) == ['w-one', 'w-two']
    assert sorted(os.listdir(tmp_path / 'home' / 'repos' / 'local' / 'log')) == ['stays']
    for name in ('w-one', 'w-two'):
        assert path_of(cm, made[name]) == same(other / 'log' / name)


def test_a_copy_into_another_repository(cm, tmp_path):
    other = plain_repo(tmp_path, 'other', '7777777777777777')
    plug(cm, other)
    uid = make(cm, 'original')

    r = access(cm, category='log', command='copy', arg1='original', arg2='other:twin')
    assert r['return'] == 0, r.get('error')
    twin = find(cm, 'other:twin')['artifacts'][0]
    assert same(twin['path']) == same(other / 'log' / 'twin') and twin['cmeta_ref_parts']['artifact_uid'] != uid
    assert path_of(cm, uid) == same(tmp_path / 'home' / 'repos' / 'local' / 'log' / 'original')


def test_the_current_directory_is_matched_against_the_records(cm, tmp_path):
    # "." on the command line: the path matched against the plugged repositories, the category folder right under
    # the repository and the index's artifacts - also where the repository, the category and a shard share one name
    from cmeta.utils.common import detect_cid_in_the_current_directory

    repo = category_repo(tmp_path, 'ab', '3333333333333333', 'sharding_slices:\n- 2\n')
    plug(cm, repo)
    uid = make(cm, 'abcdef', category='ab', repo='ab')
    folder = repo / 'ab' / 'ab' / 'abcdef'
    (folder / 'inside' / 'deeper').mkdir(parents=True)

    for where in (folder, folder / 'inside' / 'deeper'):
        r = detect_cid_in_the_current_directory(cm, path=str(where))
        assert r['return'] == 0, r.get('error')
        assert (r['artifact_repo_alias'], r['artifact_repo_uid']) == ('ab', '3333333333333333')
        assert (r['category_alias'], r['category_uid']) == ('ab', CATEGORY_UID)
        assert (r['artifact_alias'], r['artifact_uid']) == ('abcdef', uid)

    # the shard folder itself is no artifact; a folder outside every repository is an error, not a nearest match
    r = detect_cid_in_the_current_directory(cm, path=str(repo / 'ab' / 'ab'))
    assert r['return'] == 0 and r['category_alias'] == 'ab' and r['artifact_uid'] is None
    r = detect_cid_in_the_current_directory(cm, path=str(tmp_path / 'extra'))
    assert r['return'] > 0 and 'no cMeta repository' in r['error']


@pytest.mark.parametrize('command', ['move', 'migrate'])
def test_the_current_directory_inside_a_home_nested_under_a_folder_named_like_the_category(tmp_path, monkeypatch, command):
    from cmeta.utils.common import detect_cid_in_the_current_directory

    home = tmp_path / 'outer' / 'log' / 'session' / 'home'
    home.mkdir(parents=True)
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(home))
    monkeypatch.setattr(cmeta_repos, '_migrated_notices', set())
    nested = CMeta(home=str(home))
    uid = make(nested, 'old-name')

    here = home / 'repos' / 'local' / 'log' / 'old-name'
    r = detect_cid_in_the_current_directory(nested, path=str(here))
    assert r['return'] == 0
    assert (r['artifact_repo_alias'], r['category_alias'], r['artifact_alias'], r['artifact_uid']) == ('local', 'log', 'old-name', uid)

    # what "cx . <command> new-name" then asks for: the artifact by its UID
    r = access(nested, category='log', command=command, arg1=f'old-name,{uid}', arg2='new-name')
    assert r['return'] == 0, r.get('error')
    r = detect_cid_in_the_current_directory(nested, path=str(home / 'repos' / 'local' / 'log' / 'new-name'))
    assert r['return'] == 0 and (r['artifact_alias'], r['artifact_uid']) == ('new-name', uid)
    assert sorted(p.name for p in (tmp_path / 'outer' / 'log').iterdir()) == ['session']
