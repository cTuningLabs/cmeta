"""
Integration tests for `cx <category> migrate <artifact> [repo:]<new alias>`: the artifact
keeps its UID under the new alias, a stub with a new UID stays under the old alias
(`migrated_to`, `migrated_when`), and a lookup of the old alias alone follows the stub,
while the commands that change artifacts act on the stub itself.

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import datetime

import pytest

from cmeta import CMeta
from cmeta import repos as cmeta_repos


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX',
                'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    # Each test sees its own notices (they are printed once per process)
    monkeypatch.setattr(cmeta_repos, '_migrated_notices', set())
    return CMeta(home=str(tmp_path))


def access(cm, **params):
    params.setdefault('con', False)
    return cm.access(params)


def make(cm, alias, category='log', repo='local', **meta):
    r = access(cm, category=category, command='create', arg1=f'{repo}:{alias}', meta=meta)
    assert r['return'] == 0, r.get('error')
    return r['meta']['artifact']


def migrate(cm, old, new, category='log'):
    return access(cm, category=category, command='migrate', arg1=old, arg2=new)


def find(cm, ref, category='log', **params):
    return access(cm, category=category, command='find', arg1=ref, **params)


def uids(r):
    return [a['cmeta_ref_parts']['artifact_uid'] for a in r.get('artifacts', [])]


def test_migrate_moves_the_artifact_and_leaves_a_stub(cm, tmp_path):
    uid = make(cm, 'old-name', payload='x')

    r = migrate(cm, 'old-name', 'new-name')
    assert r['return'] == 0, r.get('error')
    assert r['migrated_to'] == f'new-name,{uid}'
    assert datetime.datetime.fromisoformat(r['migrated_when']).tzinfo is not None

    moved = r['artifact']
    assert moved['cmeta_ref_parts']['artifact_uid'] == uid
    assert moved['cmeta']['payload'] == 'x'
    assert (tmp_path / 'repos' / 'local' / 'log' / 'new-name').is_dir()

    stub = r['stub_meta']
    assert stub['artifact'] != uid
    assert stub['migrated_to'] == f'new-name,{uid}'
    assert stub['migrated_when'] == r['migrated_when']
    assert 'payload' not in stub
    assert (tmp_path / 'repos' / 'local' / 'log' / 'old-name').is_dir()


def test_the_old_alias_alone_follows_the_stub_with_one_notice(cm, capsys):
    uid = make(cm, 'old-name')
    assert migrate(cm, 'old-name', 'new-name')['return'] == 0
    capsys.readouterr()

    for _ in range(2):
        r = find(cm, 'old-name')
        assert r['return'] == 0, r.get('error')
        assert uids(r) == [uid]

    err = capsys.readouterr().err
    assert err.count(f'log "old-name" was migrated to "new-name,{uid}"') == 1


def test_a_uid_finds_exactly_what_it_names(cm):
    uid = make(cm, 'old-name')
    stub_uid = migrate(cm, 'old-name', 'new-name')['stub_meta']['artifact']

    assert uids(find(cm, f'old-name,{stub_uid}')) == [stub_uid]   # the stub, by its own UID
    assert uids(find(cm, f'old-name,{uid}')) == [uid]             # an old alias,UID: the artifact
    assert uids(find(cm, uid)) == [uid]
    assert uids(find(cm, 'new-name')) == [uid]
    assert uids(find(cm, 'old-name', follow_migrated=False)) == [stub_uid]


def test_select_artifact_follows_the_stub(cm):
    # what "cx task run <old alias>" resolves its task with
    uid = make(cm, 'old-name')
    assert migrate(cm, 'old-name', 'new-name')['return'] == 0

    r = access(cm, category='utils', command='select_artifact',
               select_category='log', select_artifact='old-name')
    assert r['return'] == 0, r.get('error')
    assert r['artifact_uid'] == uid


def test_delete_of_the_old_alias_removes_only_the_stub(cm):
    uid = make(cm, 'old-name')
    assert migrate(cm, 'old-name', 'new-name')['return'] == 0

    r = access(cm, category='log', command='delete', arg1='old-name', force=True)
    assert r['return'] == 0, r.get('error')

    assert uids(find(cm, 'new-name')) == [uid]
    assert find(cm, 'old-name')['return'] == 16


def test_update_acts_on_the_stub(cm):
    make(cm, 'old-name')
    stub_uid = migrate(cm, 'old-name', 'new-name')['stub_meta']['artifact']

    r = access(cm, category='log', command='update', arg1='old-name', meta={'note': 'kept'})
    assert r['return'] == 0, r.get('error')

    assert find(cm, f'old-name,{stub_uid}')['artifacts'][0]['cmeta']['note'] == 'kept'
    assert 'note' not in find(cm, 'new-name')['artifacts'][0]['cmeta']


def test_list_marks_the_stub(cm, capsys):
    uid = make(cm, 'old-name')
    assert migrate(cm, 'old-name', 'new-name')['return'] == 0
    capsys.readouterr()

    assert access(cm, category='log', command='list', con=True)['return'] == 0
    lines = capsys.readouterr().out.splitlines()
    assert f'old-name  -> new-name,{uid} (migrated)' in lines
    assert 'new-name' in lines


def test_migrate_to_another_repository(cm):
    assert access(cm, category='repo', command='init', arg1='other')['return'] == 0
    uid = make(cm, 'old-name')

    r = migrate(cm, 'local:old-name', 'other:new-name')
    assert r['return'] == 0, r.get('error')

    found = find(cm, 'old-name')['artifacts']
    assert [a['cmeta_ref_parts']['artifact_uid'] for a in found] == [uid]
    assert found[0]['cmeta_ref_parts']['repo_alias'] == 'other'

    stub = find(cm, 'old-name', follow_migrated=False)['artifacts'][0]
    assert stub['cmeta_ref_parts']['repo_alias'] == 'local'


def test_a_chain_of_migrations_resolves_to_the_last_name(cm):
    uid = make(cm, 'first')
    assert migrate(cm, 'first', 'second')['return'] == 0
    assert migrate(cm, 'second', 'third')['return'] == 0

    for alias in ('first', 'second', 'third'):
        assert uids(find(cm, alias)) == [uid], alias


def test_refusals(cm):
    make(cm, 'old-name')
    make(cm, 'taken')

    for old, new in [('old-name', 'old-name'), ('old-name', 'OLD-NAME'), ('old-*', 'x'),
                     ('old-name', 'new,0123456789abcdef'), ('old-name', 'new-*'), ('old-name', '')]:
        assert migrate(cm, old, new)['return'] > 0, (old, new)

    # An alias that is taken: move refuses, and no stub appears
    assert migrate(cm, 'old-name', 'taken')['return'] > 0
    assert 'migrated_to' not in find(cm, 'old-name', follow_migrated=False)['artifacts'][0]['cmeta']

    # A stub is not migrated again
    assert migrate(cm, 'old-name', 'new-name')['return'] == 0
    assert migrate(cm, 'old-name', 'newer-name')['return'] > 0


def test_a_stub_whose_artifact_is_gone_says_so(cm):
    make(cm, 'old-name')
    assert migrate(cm, 'old-name', 'new-name')['return'] == 0
    assert access(cm, category='log', command='delete', arg1='new-name', force=True)['return'] == 0

    r = find(cm, 'old-name')
    assert r['return'] == 16
    assert 'was migrated to' in r['error']


def test_the_stub_survives_a_reindex(cm):
    uid = make(cm, 'old-name')
    assert migrate(cm, 'old-name', 'new-name')['return'] == 0

    assert cm.access({'reindex': True, 'con': False})['return'] == 0

    assert uids(find(cm, 'old-name')) == [uid]


def test_a_category_alias_is_not_migrated(cm):
    # The "category" category does not rename aliases, so migrate stops before any stub
    assert access(cm, category='category', command='create', arg1='local:mycat')['return'] == 0

    assert migrate(cm, 'mycat', 'mycat2', category='category')['return'] > 0

    r = find(cm, 'mycat', category='category', follow_migrated=False)
    assert r['return'] == 0 and len(r['artifacts']) == 1
    assert 'migrated_to' not in r['artifacts'][0]['cmeta']
