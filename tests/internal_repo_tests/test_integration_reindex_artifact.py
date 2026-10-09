"""
Integration tests for `cx <category> reindex [<artifact>]`: the index record of an artifact is
rewritten from the meta file in its folder without any file being changed - after a meta edited by
hand, a folder renamed or copied in by hand, a stale lookup - and nothing is ever removed from the
index or touched on disk. The record is the one a full `cx --reindex` records.

Each test runs against a fresh <CMETA_HOME> in tmp_path so it does not touch the user's real
cMeta state.

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import pickle
import shutil
import subprocess
import sys

import pytest

from cmeta import CMeta
from cmeta import repos as cmeta_repos

CATEGORY_UID = 'fedcba9876543210'


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX',
                'CMETA_DEBUG', 'CMETA_VERBOSE', 'CMETA_FAIL_ON_ERROR'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    monkeypatch.setattr(cmeta_repos, '_migrated_notices', set())
    return CMeta(home=str(tmp_path))


def access(cm, **params):
    params.setdefault('con', False)
    return cm.access(params)


def make(cm, alias, category='log', repo='local', yaml=False, **meta):
    """An artifact made by cMeta; returns its UID."""
    r = access(cm, category=category, command='create', arg1=f'{repo}:{alias}', meta=meta, yaml=yaml)
    assert r['return'] == 0, r.get('error')
    return r['meta']['artifact']


def reindex(cm, ref=None, category='log', **params):
    return access(cm, category=category, command='reindex', arg1=ref, **params)


def find(cm, ref=None, category='log', **params):
    return access(cm, category=category, command='find', arg1=ref, **params)


def uids(r):
    return sorted(a['cmeta_ref_parts']['artifact_uid'] for a in r.get('artifacts', []))


def same(path):
    return os.path.normcase(os.path.normpath(str(path)))


def record(cm, ref, category='log'):
    """The index record of one artifact as `find` returns it (path, cmeta, cmeta_ref_parts, sharding)."""
    r = find(cm, ref, category=category)
    assert r['return'] == 0, r.get('error')
    assert len(r['artifacts']) == 1, r['artifacts']
    a = r['artifacts'][0]
    return {k: a[k] for k in a if k != 'index_file'}


def index_data(tmp_path, category='log'):
    """The pickled index of a category as it is on disk."""
    with open(tmp_path / 'index' / f'{category}.pkl', 'rb') as f:
        return pickle.load(f)


def index_bytes(tmp_path, category='log'):
    return (tmp_path / 'index' / f'{category}.pkl').read_bytes()


def meta_file(folder):
    for name in ('_cmeta.yaml', '_cmeta.json'):
        if (folder / name).is_file():
            return folder / name
    raise AssertionError(f'no meta file in {folder}')


def file_state(path):
    return (path.stat().st_mtime_ns, path.read_bytes())


def hand_edit(folder, text):
    """Append text to the meta file as a user would, keeping its format: YAML lines or a JSON key."""
    f = meta_file(folder)
    if f.suffix == '.yaml':
        f.write_text(f.read_text(encoding='utf-8') + text, encoding='utf-8')
    else:
        import json
        data = json.loads(f.read_text(encoding='utf-8'))
        for line in text.strip().splitlines():
            key, value = line.split(':', 1)
            data[key.strip()] = value.strip()
        f.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return f


def make_repo(tmp_path, name, repo_uid):
    """A repository folder with its descriptor only (its artifacts use the categories of the internal repo)."""
    repo = tmp_path / 'extra' / name
    repo.mkdir(parents=True)
    (repo / '_cmr.yaml').write_text(f'artifact: {name},{repo_uid}\ncategory: repo,f4f792ab40c7498f\n', encoding='utf-8')
    return repo


def plug(cm, repo):
    r = access(cm, category='repo', command='plug', arg1=str(repo))
    assert r['return'] == 0, r.get('error')


def case_insensitive_fs(tmp_path):
    probe = tmp_path / 'CaseProbe'
    probe.mkdir(exist_ok=True)
    return (tmp_path / 'caseprobe').is_dir()


##########################################################################################
# A meta edited by hand

def test_reindex_reads_a_hand_edited_meta_and_leaves_the_file_alone(cm, tmp_path):
    uid = make(cm, 'edited', yaml=True, tags=['before'])
    folder = tmp_path / 'repos' / 'local' / 'log' / 'edited'
    f = hand_edit(folder, 'owner: me\n')
    before = file_state(f)

    assert find(cm, 'edited', tags='before')['return'] == 0
    assert 'owner' not in record(cm, 'edited')['cmeta']

    r = reindex(cm, 'edited')
    assert r['return'] == 0, r.get('error')
    assert [a['cmeta_ref_parts']['artifact_uid'] for a in r['artifacts']] == [uid]
    assert r['dropped_aliases'] == {} and r['errors'] == []

    # The index knows the edit, the file is exactly as the user left it
    assert record(cm, 'edited')['cmeta']['owner'] == 'me'
    assert record(cm, uid)['cmeta']['tags'] == ['before']
    assert file_state(f) == before


def test_reindex_of_a_json_meta(cm, tmp_path):
    uid = make(cm, 'json-one', payload='x')
    folder = tmp_path / 'repos' / 'local' / 'log' / 'json-one'
    f = hand_edit(folder, 'owner: me\n')
    before = file_state(f)

    r = reindex(cm, 'json-one')
    assert r['return'] == 0, r.get('error')
    assert record(cm, 'json-one')['cmeta'] == {**record(cm, uid)['cmeta']}
    assert record(cm, uid)['cmeta']['owner'] == 'me' and record(cm, uid)['cmeta']['payload'] == 'x'
    assert file_state(f) == before


def test_the_record_is_the_one_of_a_full_reindex(cm, tmp_path):
    make(cm, 'yaml-art', yaml=True, tags=['t1'])
    make(cm, 'json-art', tags=['t2'])
    hand_edit(tmp_path / 'repos' / 'local' / 'log' / 'yaml-art', 'owner: me\n')
    hand_edit(tmp_path / 'repos' / 'local' / 'log' / 'json-art', 'owner: you\n')

    # A folder made by hand, unknown to the index, is indexed by reindex as well
    hand_made = tmp_path / 'repos' / 'local' / 'log' / 'By-Hand'
    hand_made.mkdir()
    (hand_made / '_cmeta.yaml').write_text('artifact: By-Hand,0123456789abcdef\ncategory: log,487a7639093a4685\ntags:\n- hand\n', encoding='utf-8')

    r = reindex(cm)      # every artifact of the category
    assert r['return'] == 0, r.get('error')
    assert sorted(a['cmeta_ref_parts']['artifact_alias'] for a in r['artifacts']) == ['By-Hand', 'json-art', 'yaml-art']

    after_reindex = {ref: record(cm, ref) for ref in ('yaml-art', 'json-art', 'By-Hand', 'by-hand', '0123456789abcdef')}
    data_reindex = index_data(tmp_path)

    r = access(cm, reindex=True)
    assert r['return'] == 0, r.get('error')

    for ref in after_reindex:
        assert record(cm, ref) == after_reindex[ref], ref

    data_full = index_data(tmp_path)
    assert data_full['uids'] == data_reindex['uids']
    assert data_full['lowercase_aliases'] == data_reindex['lowercase_aliases']
    # The alias keeps the case of the folder, the lowercase form is recorded when it differs
    parts = after_reindex['By-Hand']['cmeta_ref_parts']
    assert parts['artifact_alias'] == 'By-Hand' and parts['artifact_alias_lowercase'] == 'by-hand'


def test_a_second_reindex_changes_nothing(cm, tmp_path):
    make(cm, 'stable', yaml=True)
    assert reindex(cm, 'stable')['return'] == 0
    data = index_data(tmp_path)
    r = reindex(cm, 'stable')
    assert r['return'] == 0 and r['dropped_aliases'] == {}
    assert index_data(tmp_path) == data


##########################################################################################
# Folders renamed by hand

def test_a_folder_renamed_by_hand_is_found_by_its_new_name(cm, tmp_path):
    uid = make(cm, 'old-name', yaml=True, payload='x')
    other = make(cm, 'other', yaml=True)
    base = tmp_path / 'repos' / 'local' / 'log'
    (base / 'old-name').rename(base / 'new-name')

    # Before: the index still answers with the old name and a folder that is gone
    assert uids(find(cm, 'old-name')) == [uid]
    assert find(cm, 'new-name')['return'] == 16

    r = reindex(cm, 'new-name')
    assert r['return'] == 0, r.get('error')
    assert r['dropped_aliases'] == {uid: ['old-name']}

    assert uids(find(cm, 'new-name')) == [uid]
    assert find(cm, 'old-name')['return'] == 16
    assert same(record(cm, uid)['path']) == same(base / 'new-name')
    assert record(cm, uid)['cmeta_ref_parts']['artifact_alias'] == 'new-name'
    assert record(cm, uid)['cmeta']['payload'] == 'x'
    assert 'old-name' not in index_data(tmp_path)['lowercase_aliases']
    # alias,UID with the old alias still resolves: the UID is authoritative
    assert uids(find(cm, f'old-name,{uid}')) == [uid]
    # The other artifact is untouched
    assert uids(find(cm, 'other')) == [other]


def test_a_folder_renamed_by_hand_is_found_by_its_uid_or_its_old_name(cm, tmp_path):
    base = tmp_path / 'repos' / 'local' / 'log'

    uid1 = make(cm, 'by-uid', yaml=True)
    (base / 'by-uid').rename(base / 'by-uid-renamed')
    r = reindex(cm, uid1)
    assert r['return'] == 0, r.get('error')
    assert r['dropped_aliases'] == {uid1: ['by-uid']}
    assert uids(find(cm, 'by-uid-renamed')) == [uid1] and find(cm, 'by-uid')['return'] == 16

    uid2 = make(cm, 'by-old', yaml=True)
    (base / 'by-old').rename(base / 'by-old-renamed')
    r = reindex(cm, 'by-old')          # the stale alias: the folder is looked for by its UID
    assert r['return'] == 0, r.get('error')
    assert r['dropped_aliases'] == {uid2: ['by-old']}
    assert uids(find(cm, 'by-old-renamed')) == [uid2] and find(cm, 'by-old')['return'] == 16

    uid3 = make(cm, 'by-both', yaml=True)
    (base / 'by-both').rename(base / 'by-both-renamed')
    r = reindex(cm, f'by-both,{uid3}')
    assert r['return'] == 0, r.get('error')
    assert uids(find(cm, 'by-both-renamed')) == [uid3] and find(cm, 'by-both')['return'] == 16

    data = index_data(tmp_path)
    assert set(data['lowercase_aliases']) == {'by-uid-renamed', 'by-old-renamed', 'by-both-renamed'}
    assert set(data['uids']) == {uid1, uid2, uid3}


def test_a_folder_renamed_twice_loses_both_old_aliases(cm, tmp_path):
    uid = make(cm, 'first', yaml=True)
    base = tmp_path / 'repos' / 'local' / 'log'
    (base / 'first').rename(base / 'second')
    # The plain "index" of the renamed folder keeps the old alias (today's behaviour, unchanged)
    r = access(cm, category='log', command='index', arg1='local:second')
    assert r['return'] == 0, r.get('error')
    assert uids(find(cm, 'first')) == [uid] and uids(find(cm, 'second')) == [uid]
    (base / 'second').rename(base / 'third')

    r = reindex(cm, 'third')
    assert r['return'] == 0, r.get('error')
    assert sorted(r['dropped_aliases'][uid]) == ['first', 'second']
    assert find(cm, 'first')['return'] == 16 and find(cm, 'second')['return'] == 16
    assert uids(find(cm, 'third')) == [uid]


def test_a_case_only_rename_follows_the_folder(cm, tmp_path):
    uid = make(cm, 'MixedCase', yaml=True)
    base = tmp_path / 'repos' / 'local' / 'log'
    assert record(cm, uid)['cmeta_ref_parts']['artifact_alias'] == 'MixedCase'
    assert record(cm, uid)['cmeta_ref_parts']['artifact_alias_lowercase'] == 'mixedcase'

    os.rename(str(base / 'MixedCase'), str(base / 'mixedcase'))
    assert sorted(p.name for p in base.iterdir()) == ['mixedcase']

    r = reindex(cm, 'mixedcase')
    assert r['return'] == 0, r.get('error')
    assert r['dropped_aliases'] == {}       # the same lowercase alias: nothing to drop

    parts = record(cm, uid)['cmeta_ref_parts']
    assert parts['artifact_alias'] == 'mixedcase'
    assert 'artifact_alias_lowercase' not in parts
    assert os.path.basename(record(cm, uid)['path']) == 'mixedcase'
    # Lookups are case-insensitive either way
    assert uids(find(cm, 'MixedCase')) == [uid] and uids(find(cm, 'MIXEDCASE')) == [uid]


def test_two_spellings_on_a_case_sensitive_file_system(cm, tmp_path):
    if case_insensitive_fs(tmp_path):
        pytest.skip('the file system folds case: two spellings cannot coexist')
    base = tmp_path / 'repos' / 'local' / 'log'
    uid1 = make(cm, 'Spell', yaml=True)
    # cMeta itself refuses the second spelling (the index is case-insensitive): it can only be made by hand
    r = access(cm, category='log', command='create', arg1='local:spell', yaml=True)
    assert r['return'] == 8
    (base / 'spell').mkdir()
    (base / 'spell' / '_cmeta.yaml').write_text('artifact: spell,dddddddddddddddd\ncategory: log,487a7639093a4685\nowner: two\n', encoding='utf-8')
    hand_edit(base / 'Spell', 'owner: one\n')

    # Both folders are found, whichever spelling is given, and both UIDs sit under the one lowercase alias
    r = reindex(cm, 'spell')
    assert r['return'] == 0, r.get('error')
    assert uids(r) == sorted([uid1, 'dddddddddddddddd'])
    assert record(cm, uid1)['cmeta']['owner'] == 'one' and record(cm, 'dddddddddddddddd')['cmeta']['owner'] == 'two'
    assert record(cm, uid1)['cmeta_ref_parts']['artifact_alias'] == 'Spell'
    assert record(cm, 'dddddddddddddddd')['cmeta_ref_parts']['artifact_alias'] == 'spell'
    assert sorted(index_data(tmp_path)['lowercase_aliases']['spell']) == sorted([uid1, 'dddddddddddddddd'])
    # A lookup by the alias is ambiguous, as after a full reindex
    assert uids(find(cm, 'Spell')) == sorted([uid1, 'dddddddddddddddd'])
    both = {uid: record(cm, uid) for uid in (uid1, 'dddddddddddddddd')}
    assert access(cm, reindex=True)['return'] == 0
    for uid in both:
        assert record(cm, uid) == both[uid]


def test_a_json_meta_renamed_by_hand(cm, tmp_path):
    uid = make(cm, 'js-old', payload='j')          # a JSON meta
    base = tmp_path / 'repos' / 'local' / 'log'
    assert (base / 'js-old' / '_cmeta.json').is_file()
    (base / 'js-old').rename(base / 'js-new')
    f = base / 'js-new' / '_cmeta.json'
    before = file_state(f)

    r = reindex(cm, 'js-new')
    assert r['return'] == 0, r.get('error')
    assert r['dropped_aliases'] == {uid: ['js-old']}
    assert uids(find(cm, 'js-new')) == [uid] and find(cm, 'js-old')['return'] == 16
    assert record(cm, uid)['cmeta']['payload'] == 'j'
    assert file_state(f) == before


def test_an_upper_case_uid_in_a_meta(cm, tmp_path):
    make(cm, 'seed', yaml=True)
    base = tmp_path / 'repos' / 'local' / 'log'
    (base / 'upper').mkdir()
    (base / 'upper' / '_cmeta.yaml').write_text('artifact: upper,ABCDEF0123456789\ncategory: log,487a7639093a4685\n', encoding='utf-8')

    r = reindex(cm, 'upper')
    assert r['return'] == 0, r.get('error')
    assert uids(r) == ['abcdef0123456789']
    assert uids(find(cm, 'ABCDEF0123456789')) == ['abcdef0123456789']
    assert uids(find(cm, 'abcdef0123456789')) == ['abcdef0123456789']
    rec = record(cm, 'upper')
    assert access(cm, reindex=True)['return'] == 0
    assert record(cm, 'upper') == rec


def test_an_unreadable_meta_file(cm, tmp_path):
    uid = make(cm, 'broken', yaml=True)
    other = make(cm, 'fine', yaml=True)
    base = tmp_path / 'repos' / 'local' / 'log'
    f = base / 'broken' / '_cmeta.yaml'
    f.write_text('artifact: [unclosed\n', encoding='utf-8')
    before = index_bytes(tmp_path)
    state = file_state(f)

    for ref in ('broken', uid):
        r = reindex(cm, ref)
        assert r['return'] == 1 and 'cannot be read' in r['error'], r
        assert index_bytes(tmp_path) == before
    assert file_state(f) == state                      # the broken file is not touched either

    hand_edit(base / 'fine', 'owner: me\n')
    r = reindex(cm, ignore_errors=True)
    assert r['return'] == 0 and uids(r) == [other] and len(r['errors']) == 1
    assert uids(find(cm, 'broken')) == [uid]            # its old record is kept


def test_a_non_ascii_alias(cm, tmp_path):
    r = access(cm, category='log', command='create', arg1='local:café-ünïcode', yaml=True, meta={'payload': 'é'})
    if r['return'] != 0:
        pytest.skip(f'non-ASCII aliases are refused here: {r.get("error")}')
    uid = r['meta']['artifact']
    base = tmp_path / 'repos' / 'local' / 'log'
    hand_edit(base / 'café-ünïcode', 'owner: moi\n')
    r = reindex(cm, 'café-ünïcode')
    assert r['return'] == 0, r.get('error')
    assert record(cm, uid)['cmeta']['owner'] == 'moi'

    (base / 'café-ünïcode').rename(base / 'naïve-änderung')
    r = reindex(cm, 'naïve-änderung')
    assert r['return'] == 0, r.get('error')
    assert r['dropped_aliases'] == {uid: ['café-ünïcode']}
    assert uids(find(cm, 'naïve-änderung')) == [uid] and uids(find(cm, 'NAÏVE-ÄNDERUNG')) == [uid]
    assert find(cm, 'café-ünïcode')['return'] == 16


def test_a_rename_by_hand_inside_a_sharded_category(cm, tmp_path):
    repo = make_category_repo(tmp_path, 'shard', '3333333333333333', 'sharding_slices:\n- 2\n')
    plug(cm, repo)
    uid = make(cm, 'abcdef', category='shard', repo='shard', yaml=True)
    folder = pytest.importorskip('pathlib').Path(find(cm, 'abcdef', category='shard')['artifacts'][0]['path'])
    # Renamed in place: the folder stays in the "ab" shard although the new name would belong to "xy"
    folder.rename(folder.parent / 'xyzdef')

    r = reindex(cm, uid, category='shard')
    assert r['return'] == 0, r.get('error')
    assert r['dropped_aliases'] == {uid: ['abcdef']}
    rec = record(cm, uid, category='shard')
    assert rec['cmeta_ref_parts']['artifact_alias'] == 'xyzdef' and rec['sharding_slices_num'] == 1
    assert same(rec['path']) == same(folder.parent / 'xyzdef')
    assert uids(find(cm, 'xyzdef', category='shard')) == [uid]
    # The same record as the full reindex, which also finds the folder where it is
    assert access(cm, reindex=True)['return'] == 0
    assert record(cm, uid, category='shard') == rec


def test_a_category_without_an_index_file_yet(cm, tmp_path):
    repo = make_category_repo(tmp_path, 'fresh', '5555555555555555', '')
    plug(cm, repo)
    assert not (tmp_path / 'index' / 'fresh.pkl').is_file()
    folder = repo / 'fresh' / 'first'
    folder.mkdir(parents=True)
    (folder / '_cmeta.yaml').write_text(f'artifact: first,eeeeeeeeeeeeeeee\ncategory: fresh,{CATEGORY_UID}\n', encoding='utf-8')

    r = reindex(cm, category='fresh')
    assert r['return'] == 0, r.get('error')
    assert uids(r) == ['eeeeeeeeeeeeeeee']
    assert (tmp_path / 'index' / 'fresh.pkl').is_file()
    assert uids(find(cm, 'first', category='fresh')) == ['eeeeeeeeeeeeeeee']


def test_a_repository_with_a_subdir(cm, tmp_path):
    repo = tmp_path / 'extra' / 'withsub'
    (repo / 'content').mkdir(parents=True)
    (repo / '_cmr.yaml').write_text('artifact: withsub,6666666666666666\ncategory: repo,f4f792ab40c7498f\nsubdir: content\n', encoding='utf-8')
    plug(cm, repo)
    uid = make(cm, 'in-sub', repo='withsub', yaml=True)
    folder = repo / 'content' / 'log' / 'in-sub'
    assert folder.is_dir()
    hand_edit(folder, 'owner: me\n')

    r = reindex(cm, 'withsub:in-sub')
    assert r['return'] == 0, r.get('error')
    assert record(cm, uid)['cmeta']['owner'] == 'me'
    assert same(record(cm, uid)['path']) == same(folder)

    (folder.parent / 'in-sub').rename(folder.parent / 'in-sub-2')
    r = reindex(cm, uid)
    assert r['return'] == 0, r.get('error')
    assert uids(find(cm, 'in-sub-2')) == [uid] and find(cm, 'in-sub')['return'] == 16


def test_the_shipped_internal_repository_is_only_read(cm):
    before = record(cm, 'log', category='category')
    f = pytest.importorskip('pathlib').Path(before['path']) / '_cmeta.yaml'
    state = file_state(f)

    r = reindex(cm, 'log', category='category')
    assert r['return'] == 0, r.get('error')
    assert record(cm, 'log', category='category') == before
    assert file_state(f) == state


def test_several_processes_reindex_at_once(cm, tmp_path):
    # Six processes write the same index file at once: with the previous lock (its file removed after the
    # release) a waiter and a newcomer could both acquire on Linux and one record was lost; the engine's own
    # PathLock (the file removed before the release, the identity of the file checked after acquiring) keeps
    # every record on every platform
    base = tmp_path / 'repos' / 'local' / 'log'
    names = [f'par-{i}' for i in range(6)]
    made = {name: make(cm, name, yaml=True) for name in names}
    for name in names:
        hand_edit(base / name, f'owner: {name}\n')

    env = {k: v for k, v in os.environ.items() if not k.startswith('CMETA_') and k not in ('VIRTUAL_ENV', 'CONDA_PREFIX')}
    env['CMETA_HOME'] = str(tmp_path)
    env['PYTHONIOENCODING'] = 'utf-8'

    procs = [subprocess.Popen([sys.executable, '-m', 'cmeta', 'log', 'reindex', name], env=env,
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) for name in names]
    outputs = [p.communicate(timeout=180)[0] for p in procs]
    assert all(p.returncode == 0 for p in procs), outputs

    data = index_data(tmp_path)
    for name in names:
        assert data['uids'][made[name]]['cmeta']['owner'] == name
        assert data['lowercase_aliases'][name] == [made[name]]
    assert len(data['uids']) == len(names)


##########################################################################################
# Nothing is lost: the errors leave the index as it was

def test_two_folders_with_one_uid_is_an_error_that_changes_nothing(cm, tmp_path):
    uid = make(cm, 'original', yaml=True)
    base = tmp_path / 'repos' / 'local' / 'log'
    shutil.copytree(base / 'original', base / 'copied')
    before = index_bytes(tmp_path)

    for ref in ('copied', uid, None):
        r = reindex(cm, ref)
        assert r['return'] == 1, (ref, r)
        assert 'same UID' in r['error'] or 'two folders with one UID' in r['error'], r['error']
        assert index_bytes(tmp_path) == before, ref

    # With --ignore_errors the other artifacts are reindexed and the conflict is reported
    other = make(cm, 'fine', yaml=True)
    hand_edit(base / 'fine', 'owner: me\n')
    r = reindex(cm, ignore_errors=True)
    assert r['return'] == 0, r.get('error')
    assert uids(r) == [other]
    assert len(r['errors']) == 1 and uid in r['errors'][0]['error']
    assert record(cm, other)['cmeta']['owner'] == 'me'
    assert same(record(cm, uid)['path']) == same(base / 'original')

    # A new UID for the copy resolves it
    (base / 'copied' / '_cmeta.yaml').write_text('artifact: copied,aaaaaaaaaaaaaaaa\ncategory: log,487a7639093a4685\n', encoding='utf-8')
    r = reindex(cm, 'copied')
    assert r['return'] == 0, r.get('error')
    assert uids(find(cm, 'copied')) == ['aaaaaaaaaaaaaaaa'] and uids(find(cm, 'original')) == [uid]


def test_a_missing_folder_is_an_error_that_changes_nothing(cm, tmp_path):
    uid = make(cm, 'gone', yaml=True)
    shutil.rmtree(tmp_path / 'repos' / 'local' / 'log' / 'gone')
    before = index_bytes(tmp_path)

    for ref in ('gone', uid):
        r = reindex(cm, ref)
        assert r['return'] == 1 and 'no folder with its UID' in r['error'], r
        assert index_bytes(tmp_path) == before

    # delete, as the error says, removes the record of the missing folder
    r = access(cm, category='log', command='delete', arg1='gone', force=True)
    assert r['return'] == 0, r.get('error')
    assert find(cm, 'gone')['return'] == 16


def test_a_folder_replaced_by_another_artifact(cm, tmp_path):
    # The folder of an artifact was removed and another artifact was put under the same name by hand
    uid = make(cm, 'slot', yaml=True)
    other = make(cm, 'other', yaml=True)
    base = tmp_path / 'repos' / 'local' / 'log'
    shutil.rmtree(base / 'slot')
    (base / 'slot').mkdir()
    (base / 'slot' / '_cmeta.yaml').write_text('artifact: slot,aaaaaaaaaaaaaaaa\ncategory: log,487a7639093a4685\n', encoding='utf-8')

    r = reindex(cm, 'slot')
    assert r['return'] == 0, r.get('error')
    assert uids(r) == ['aaaaaaaaaaaaaaaa']
    # The record of the artifact that is not there any more is dropped, and said
    assert len(r['dropped_records']) == 1 and uid in r['dropped_records'][0]['ref'] and 'aaaaaaaaaaaaaaaa' in r['dropped_records'][0]['now']
    assert uids(find(cm, 'slot')) == ['aaaaaaaaaaaaaaaa']
    assert find(cm, uid)['return'] == 16
    assert uid not in index_data(tmp_path)['uids']
    assert index_data(tmp_path)['lowercase_aliases']['slot'] == ['aaaaaaaaaaaaaaaa']
    assert uids(find(cm, 'other')) == [other]
    # The new artifact's folder is untouched
    assert (base / 'slot' / '_cmeta.yaml').is_file()


def test_a_folder_moved_and_its_old_name_taken(cm, tmp_path):
    # The artifact was renamed by hand and another artifact took its old name
    uid1 = make(cm, 'taken', yaml=True, payload='one')
    base = tmp_path / 'repos' / 'local' / 'log'
    (base / 'taken').rename(base / 'moved-away')
    (base / 'taken').mkdir()
    (base / 'taken' / '_cmeta.yaml').write_text('artifact: taken,bbbbbbbbbbbbbbbb\ncategory: log,487a7639093a4685\n', encoding='utf-8')

    r = reindex(cm, 'taken')
    assert r['return'] == 0, r.get('error')
    assert uids(r) == sorted([uid1, 'bbbbbbbbbbbbbbbb'])
    assert r['dropped_records'] == []
    assert r['dropped_aliases'] == {uid1: ['taken']}
    assert uids(find(cm, 'taken')) == ['bbbbbbbbbbbbbbbb']
    assert uids(find(cm, 'moved-away')) == [uid1]
    assert record(cm, uid1)['cmeta']['payload'] == 'one'


def test_an_unknown_artifact_is_not_found(cm, tmp_path):
    make(cm, 'exists', yaml=True)
    r = reindex(cm, 'does-not-exist')
    assert r['return'] == 16 and 'not found' in r['error']
    r = reindex(cm, 'ffffffffffffffff')
    assert r['return'] == 16
    r = reindex(cm, 'no-such-repo:exists')
    assert r['return'] == 16


def test_a_hand_made_folder_without_a_valid_uid_is_not_indexed(cm, tmp_path):
    make(cm, 'exists', yaml=True)
    before = index_bytes(tmp_path)
    bad = tmp_path / 'repos' / 'local' / 'log' / 'bad-uid'
    bad.mkdir()
    (bad / '_cmeta.yaml').write_text('artifact: bad-uid\ncategory: log,487a7639093a4685\n', encoding='utf-8')

    r = reindex(cm, 'bad-uid')
    assert r['return'] == 16, r
    assert index_bytes(tmp_path) == before

    no_key = tmp_path / 'repos' / 'local' / 'log' / 'no-key'
    no_key.mkdir()
    (no_key / '_cmeta.yaml').write_text('tags:\n- x\n', encoding='utf-8')
    r = reindex(cm, 'no-key')
    assert r['return'] == 16, r
    assert index_bytes(tmp_path) == before


def test_a_folder_of_another_category_is_not_taken(cm, tmp_path):
    # A folder copied into the wrong category folder: its meta names another category
    make(cm, 'exists', yaml=True)
    before = index_bytes(tmp_path)
    wrong = tmp_path / 'repos' / 'local' / 'log' / 'an-asset'
    wrong.mkdir()
    (wrong / '_cmeta.yaml').write_text('artifact: an-asset,bbbbbbbbbbbbbbbb\ncategory: asset,e0982f19227743c8\n', encoding='utf-8')
    r = reindex(cm, 'an-asset')
    assert r['return'] == 16, r
    assert index_bytes(tmp_path) == before


def test_other_records_are_untouched(cm, tmp_path):
    uid_a = make(cm, 'art-a', yaml=True, tags=['a'])
    uid_b = make(cm, 'art-b', yaml=True, tags=['b'])
    uid_c = make(cm, 'art-c', tags=['c'])
    data = index_data(tmp_path)

    hand_edit(tmp_path / 'repos' / 'local' / 'log' / 'art-b', 'owner: me\n')
    r = reindex(cm, 'art-b')
    assert r['return'] == 0, r.get('error')

    after = index_data(tmp_path)
    for uid in (uid_a, uid_c):
        assert after['uids'][uid] == data['uids'][uid]
    assert after['uids'][uid_b]['cmeta']['owner'] == 'me'
    assert after['lowercase_aliases'] == data['lowercase_aliases']


##########################################################################################
# Selections: wildcards, tags, a repository, everything

def test_wildcards_tags_and_a_repository(cm, tmp_path):
    repo = make_repo(tmp_path, 'second', '2222222222222222')
    plug(cm, repo)
    base_local = tmp_path / 'repos' / 'local' / 'log'
    base_second = repo / 'log'

    a1 = make(cm, 'wild-1', yaml=True, tags=['odd'])
    a2 = make(cm, 'wild-2', yaml=True, tags=['even'])
    s1 = make(cm, 'wild-1', repo='second', yaml=True, tags=['odd', 'second'])
    other = make(cm, 'other', yaml=True)
    for folder in (base_local / 'wild-1', base_local / 'wild-2', base_second / 'wild-1', base_local / 'other'):
        hand_edit(folder, 'owner: me\n')

    r = reindex(cm, 'wild-*')
    assert r['return'] == 0, r.get('error')
    assert uids(r) == sorted([a1, a2, s1])
    assert 'owner' not in record(cm, other)['cmeta']

    r = reindex(cm, 'other', tags='nope')
    assert r['return'] == 16

    hand_edit(base_local / 'wild-1', 'owner2: me\n')
    hand_edit(base_second / 'wild-1', 'owner2: me\n')
    r = reindex(cm, 'second:wild-1')             # the one in the second repository only
    assert r['return'] == 0, r.get('error')
    assert uids(r) == [s1]
    assert 'owner2' in record(cm, s1)['cmeta'] and 'owner2' not in record(cm, a1)['cmeta']
    # The same alias in two repositories: both UIDs stay under the alias
    assert sorted(index_data(tmp_path)['lowercase_aliases']['wild-1']) == sorted([a1, s1])

    r = reindex(cm, 'wild-*', tags='odd,-second')
    assert r['return'] == 0, r.get('error')
    assert uids(r) == [a1]

    r = reindex(cm, 'local:')                   # everything of the category in one repository
    assert r['return'] == 0, r.get('error')
    assert uids(r) == sorted([a1, a2, other])


def test_everything_of_the_category_takes_the_folders_made_by_hand(cm, tmp_path):
    make(cm, 'made', yaml=True)
    base = tmp_path / 'repos' / 'local' / 'log'
    for i in range(3):
        folder = base / f'hand-{i}'
        folder.mkdir()
        (folder / '_cmeta.yaml').write_text(f'artifact: hand-{i},{i}{i}{i}{i}{i}{i}{i}{i}{i}{i}{i}{i}{i}{i}{i}{i}\ncategory: log,487a7639093a4685\n', encoding='utf-8')

    r = reindex(cm)
    assert r['return'] == 0, r.get('error')
    assert sorted(a['cmeta_ref_parts']['artifact_alias'] for a in r['artifacts']) == ['hand-0', 'hand-1', 'hand-2', 'made']
    assert uids(find(cm, 'hand-1')) == ['1111111111111111']


def test_a_folder_named_by_its_uid(cm, tmp_path):
    base = tmp_path / 'repos' / 'local' / 'log'
    make(cm, 'seed', yaml=True)       # the index exists
    folder = base / 'cccccccccccccccc'
    folder.mkdir()
    (folder / '_cmeta.yaml').write_text('artifact: cccccccccccccccc\ncategory: log,487a7639093a4685\n', encoding='utf-8')

    r = reindex(cm, 'cccccccccccccccc')
    assert r['return'] == 0, r.get('error')
    parts = record(cm, 'cccccccccccccccc')['cmeta_ref_parts']
    assert parts['artifact_uid'] == 'cccccccccccccccc'
    assert parts.get('artifact_alias') == 'cccccccccccccccc'      # the folder's name, as the full reindex records it

    r = access(cm, reindex=True)
    assert r['return'] == 0, r.get('error')
    assert record(cm, 'cccccccccccccccc')['cmeta_ref_parts'] == parts


##########################################################################################
# Categories with special layouts

def make_category_repo(tmp_path, name, repo_uid, category_meta_extra):
    """A repository with a category of its own (`shard` or `noidx`) and nothing else."""
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


def test_a_sharded_category(cm, tmp_path):
    repo = make_category_repo(tmp_path, 'shard', '3333333333333333', 'sharding_slices:\n- 2\n')
    plug(cm, repo)

    uid = make(cm, 'abcdef', category='shard', repo='shard', yaml=True)
    r = find(cm, 'abcdef', category='shard')
    folder = r['artifacts'][0]['path']
    assert r['artifacts'][0]['sharding_slices_num'] == 1
    assert os.path.basename(os.path.dirname(folder)) == 'ab'       # the shard

    hand_edit(pytest.importorskip('pathlib').Path(folder), 'owner: me\n')
    r = reindex(cm, 'abcdef', category='shard')
    assert r['return'] == 0, r.get('error')
    assert r['artifacts'][0]['sharding_slices_num'] == 1
    after_reindex = record(cm, uid, category='shard')
    assert after_reindex['cmeta']['owner'] == 'me' and after_reindex['sharding_slices_num'] == 1

    r = access(cm, reindex=True)
    assert r['return'] == 0, r.get('error')
    assert record(cm, uid, category='shard') == after_reindex


def test_a_no_index_category_is_refused(cm, tmp_path):
    repo = make_category_repo(tmp_path, 'noidx', '4444444444444444', 'no_index: true\n')
    plug(cm, repo)
    scanned = make(cm, 'scanned', category='noidx', repo='noidx', yaml=True)
    make(cm, 'other', category='noidx', repo='noidx', yaml=True)
    r = reindex(cm, 'scanned', category='noidx')
    assert r['return'] == 1 and 'no_index' in r['error']

    # The scan that finds the artifacts of such a category honours a wildcard (it used to return every folder)
    assert uids(find(cm, 'sc*', category='noidx')) == [scanned]
    assert uids(find(cm, 'SCAN?ED', category='noidx')) == [scanned]
    assert find(cm, 'nothing-*', category='noidx')['return'] == 16
    assert len(find(cm, '*', category='noidx')['artifacts']) == 2


def test_the_record_of_a_category_itself(cm, tmp_path):
    repo = make_category_repo(tmp_path, 'shard', '3333333333333333', '')
    plug(cm, repo)
    assert 'extra' not in record(cm, 'shard', category='category')['cmeta']

    f = repo / 'category' / 'shard' / '_cmeta.yaml'
    f.write_text(f.read_text(encoding='utf-8') + 'extra: 1\n', encoding='utf-8')
    before = file_state(f)

    r = reindex(cm, 'shard', category='category')
    assert r['return'] == 0, r.get('error')
    assert record(cm, 'shard', category='category')['cmeta']['extra'] == 1
    assert file_state(f) == before
    after_reindex = record(cm, 'shard', category='category')

    r = access(cm, reindex=True)
    assert r['return'] == 0, r.get('error')
    assert record(cm, 'shard', category='category') == after_reindex


def test_a_migration_stub_is_reindexed_as_itself(cm, tmp_path):
    uid = make(cm, 'old-name', yaml=True)
    r = access(cm, category='log', command='migrate', arg1='old-name', arg2='new-name')
    assert r['return'] == 0, r.get('error')
    stub_uid = r['stub_meta']['artifact']

    r = reindex(cm, 'old-name')
    assert r['return'] == 0, r.get('error')
    assert uids(r) == [stub_uid]            # the stub, not the artifact it points to
    assert record(cm, stub_uid)['cmeta']['migrated_to'] == f'new-name,{uid}'
    assert uids(find(cm, 'old-name')) == [uid]       # the old alias alone still follows the stub


##########################################################################################
# The commands that exist keep their answers

def test_index_and_update_are_unchanged(cm, tmp_path):
    uid = make(cm, 'kept', yaml=True)
    # "index" still refuses an artifact that is indexed
    r = access(cm, category='log', command='index', arg1='local:kept')
    assert r['return'] == 8
    # an empty "update" still refreshes the record and rewrites the file (its timestamp)
    f = meta_file(tmp_path / 'repos' / 'local' / 'log' / 'kept')
    before = file_state(f)
    r = access(cm, category='log', command='update', arg1='kept')
    assert r['return'] == 0, r.get('error')
    assert file_state(f) != before
    assert 'last_update_timestamp' in record(cm, uid)['cmeta']


def test_the_cli_route(cm, tmp_path):
    uid = make(cm, 'via-cli', yaml=True)
    hand_edit(tmp_path / 'repos' / 'local' / 'log' / 'via-cli', 'owner: me\n')

    env = {k: v for k, v in os.environ.items() if not k.startswith('CMETA_') and k not in ('VIRTUAL_ENV', 'CONDA_PREFIX')}
    env['CMETA_HOME'] = str(tmp_path)
    env['PYTHONIOENCODING'] = 'utf-8'

    r = subprocess.run([sys.executable, '-m', 'cmeta', 'log', 'reindex', 'via-cli'], stdin=subprocess.DEVNULL, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert f'Reindexed log "via-cli" ({uid})' in r.stdout
    assert record(cm, uid)['cmeta']['owner'] == 'me'

    r = subprocess.run([sys.executable, '-m', 'cmeta', 'log', 'reindex', 'nothing-here'], stdin=subprocess.DEVNULL, capture_output=True, text=True, env=env)
    assert r.returncode == 16, r.stdout + r.stderr

    r = subprocess.run([sys.executable, '-m', 'cmeta', 'log', 'reindex', '--help'], stdin=subprocess.DEVNULL, capture_output=True, text=True, env=env)
    assert r.returncode == 0 and 'ignore_errors' in r.stdout, r.stdout + r.stderr
