"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

An artifact whose alias holds commas and spaces (the user, 2026-11-23: "Kim Doe, joined Example Co, 20260922") through
the whole engine: create, find by every form, update, connect both ways, the cRef with a path, move, copy, migrate,
delete, the command line - and the one alias refused: a UID after its last comma reads as alias,UID. An artifact made
by hand with such a folder name is still indexed and found by its UID. Each test runs in a fresh <CMETA_HOME>.
"""

import os
import subprocess
import sys

import pytest
import yaml

from cmeta import CMeta

KIM = 'Kim Doe, joined Example Co, 20260922'
LIKE_UID = '0123456789abcdef'


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    return CMeta(home=str(tmp_path))


def call(cm, command, **params):
    return cm.access(dict({'category': 'log', 'command': command, 'con': False}, **params))


def make(cm, alias):
    r = call(cm, 'create', arg1='local:' + alias)
    assert r['return'] == 0, r
    return r['meta']['artifact'], r['path']


def found(cm, name):
    """The (alias, UID) of every artifact a name finds, as a set; an empty set when there is none."""
    r = call(cm, 'find', arg1=name)
    if r['return'] == 16:
        return set()
    assert r['return'] == 0, r
    return {(a['cmeta_ref_parts'].get('artifact_alias'), a['cmeta_ref_parts']['artifact_uid']) for a in r['artifacts']}


def desc_connections(path):
    p = os.path.join(path, '_desc.yaml')
    if not os.path.isfile(p):
        return []
    with open(p, encoding='utf-8') as f:
        return (yaml.safe_load(f) or {}).get('connections') or []


def test_create_find_update_and_delete_by_every_form(cm):
    uid, path = make(cm, KIM)
    assert os.path.basename(path) == KIM
    me = {(KIM, uid)}

    # every form of the name finds it: the alias alone, alias,UID (capitals too), the UID, the repository's prefix
    for name in (KIM, KIM + ',' + uid, KIM + ' , ' + uid.upper(), uid, uid.upper(), 'local:' + KIM,
                 'local:' + KIM + ',' + uid, 'Kim Doe, joined*'):
        assert found(cm, name) == me, name

    # the alias is the whole name: no part of it finds the artifact
    for name in ('Kim Doe', 'joined Example Co', '20260922', 'Kim Doe, joined Example Co'):
        assert found(cm, name) == set(), name

    # a UID after the last comma decides: the alias beside it is a label (as for every alias,UID)
    other_uid, _ = make(cm, 'other')
    assert found(cm, KIM + ',' + other_uid) == {('other', other_uid)}

    r = call(cm, 'update', arg1=KIM, meta={'note': 'updated by its alias'})
    assert r['return'] == 0, r
    assert call(cm, 'read', arg1=KIM + ',' + uid)['cmeta']['note'] == 'updated by its alias'

    r = call(cm, 'delete', arg1=KIM, force=True)
    assert r['return'] == 0, r
    assert found(cm, uid) == set() and not os.path.exists(path)


def test_an_alias_with_a_uid_after_its_last_comma_is_refused(cm):
    # by itself the name reads as alias,UID - the artifact "x" with that UID, as always
    uid, path = make(cm, 'x,' + LIKE_UID)
    assert uid == LIKE_UID and os.path.basename(path) == 'x'

    # with its own UID after it, the alias would end with a UID: refused before anything is made
    r = call(cm, 'create', arg1='local:y,' + LIKE_UID.upper() + ',5ca1ab1e5ca1ab1e')
    assert r['return'] == 1 and 'alias,UID' in r['error'], r
    assert found(cm, '5ca1ab1e5ca1ab1e') == set()

    # move and copy refuse such a new alias the same way; migrate takes no UID in the new name at all (its own rule)
    kim_uid, _ = make(cm, KIM)
    for command in ('move', 'copy'):
        r = call(cm, command, arg1=KIM, arg2='y, ' + LIKE_UID[::-1] + ',' + kim_uid)
        assert r['return'] == 1 and 'alias,UID' in r['error'], (command, r)
    for arg2 in ('y, ' + LIKE_UID[::-1], 'y, ' + LIKE_UID[::-1] + ',' + kim_uid):
        r = call(cm, 'migrate', arg1=KIM, arg2=arg2)
        assert r['return'] == 1 and 'without a UID' in r['error'], (arg2, r)
    assert found(cm, KIM) == {(KIM, kim_uid)}

    # commas elsewhere are fine, and so is a part after the last comma that is not a whole UID
    for alias in ('a, b', 'c,' + LIKE_UID[:15], 'd,' + LIKE_UID + 'x'):
        u, p = make(cm, alias)
        assert found(cm, alias) == {(alias, u)} and os.path.basename(p) == alias


def test_a_folder_made_by_hand_with_such_a_name_is_still_found_by_its_uid(cm, tmp_path):
    _, path = make(cm, 'seed')
    folder = os.path.join(os.path.dirname(path), 'hand,' + LIKE_UID)
    os.makedirs(folder)
    uid = 'fedcba9876543210'
    cat = cm.access({'category': 'category', 'command': 'find', 'arg1': 'log', 'con': False})['artifacts'][0]
    with open(os.path.join(folder, '_cmeta.yaml'), 'w', encoding='utf-8') as f:
        yaml.safe_dump({'artifact': uid, 'category': 'log,' + cat['cmeta_ref_parts']['artifact_uid']}, f)
    r = call(cm, 'reindex')
    assert r['return'] == 0, r

    assert found(cm, uid) == {('hand,' + LIKE_UID, uid)}
    assert found(cm, 'hand,' + LIKE_UID + ',' + uid) == {('hand,' + LIKE_UID, uid)}
    assert found(cm, 'hand,' + LIKE_UID) == set()                       # alias "hand" with another UID: nothing

    # one registered by "index": the UID of its meta (alias,UID, capitals) in lower case, as everywhere
    folder = os.path.join(os.path.dirname(path), 'Hand, made')
    os.makedirs(folder)
    with open(os.path.join(folder, '_cmeta.yaml'), 'w', encoding='utf-8') as f:
        yaml.safe_dump({'artifact': 'Hand, made,ABCDEF0123456789', 'category': 'log,' + cat['cmeta_ref_parts']['artifact_uid']}, f)
    r = call(cm, 'index', arg1='local:Hand, made')
    assert r['return'] == 0, r
    assert found(cm, 'abcdef0123456789') == {('Hand, made', 'abcdef0123456789')}
    assert found(cm, 'Hand, made') == {('Hand, made', 'abcdef0123456789')}


def test_an_artifact_named_by_its_uid_alone_as_before(cm):
    """An artifact without an alias (the user, 2026-11-23: "I allow creation of just UID without alias") - made with
    no name or with a UID, found by its UID in either case, named later: it keeps its UID and gets the alias."""
    r = call(cm, 'create')
    assert r['return'] == 0, r
    uid, path = r['meta']['artifact'], r['path']
    assert os.path.basename(path) == uid and found(cm, uid) == {(None, uid)}

    r = call(cm, 'create', arg1='local:' + LIKE_UID.upper())
    assert r['return'] == 0 and r['meta']['artifact'] == LIKE_UID and os.path.basename(r['path']) == LIKE_UID, r
    assert found(cm, LIKE_UID) == found(cm, LIKE_UID.upper()) == {(None, LIKE_UID)}

    # alias,UID makes the artifact with that UID, as always
    r = call(cm, 'create', arg1='local:Given, its UID,' + 'abcdef0123456789')
    assert r['return'] == 0 and r['meta']['artifact'] == 'abcdef0123456789', r
    assert found(cm, 'abcdef0123456789') == {('Given, its UID', 'abcdef0123456789')}

    # named later: the same UID, the alias with commas
    r = call(cm, 'move', arg1=uid, arg2='Named, at last')
    assert r['return'] == 0, r
    assert found(cm, uid) == found(cm, 'Named, at last') == {('Named, at last', uid)}


def test_a_meta_with_a_category_without_its_uid_is_skipped_not_a_crash(cm, capsys):
    """Its category named by the alias alone: the reindex skips it with a warning (it raised KeyError: 'uid')."""
    uid, path = make(cm, 'kept')
    folder = os.path.join(os.path.dirname(path), 'no, category uid')
    os.makedirs(folder)
    with open(os.path.join(folder, '_cmeta.yaml'), 'w', encoding='utf-8') as f:
        yaml.safe_dump({'artifact': 'fedcba9876543210', 'category': 'log'}, f)

    r = call(cm, 'reindex')
    assert r['return'] == 0, r
    assert 'has no category UID' in capsys.readouterr().out
    assert found(cm, 'fedcba9876543210') == set() and found(cm, 'kept') == {('kept', uid)}

    r = call(cm, 'reindex', arg1='fedcba9876543210')
    assert r['return'] != 0 or r.get('artifacts', []) == [], r


def test_connect_both_ways_and_the_cref_with_a_path(cm):
    kim_uid, kim_path = make(cm, KIM)
    carol_uid, carol_path = make(cm, 'Carol Roe')

    # a cRef by the alias alone, commas and spaces in it
    r = call(cm, 'update', arg1='Carol Roe', connect='log::' + KIM)
    assert r['return'] == 0, r
    cat_uid = cm.access({'category': 'category', 'command': 'find', 'arg1': 'log', 'con': False})['artifacts'][0]['cmeta_ref_parts']['artifact_uid']
    assert desc_connections(carol_path) == ['log,%s::%s,%s' % (cat_uid, KIM, kim_uid)]
    assert desc_connections(kim_path) == ['log,%s::Carol Roe,%s' % (cat_uid, carol_uid)]

    # removed both ways by the same name
    r = call(cm, 'update', arg1='Carol Roe', connect='-log::' + KIM + ',' + kim_uid)
    assert r['return'] == 0, r
    assert desc_connections(carol_path) == [] and desc_connections(kim_path) == []

    # a list: cRefs separated by ";", each keeps its commas
    other_uid, other_path = make(cm, 'Other, one')
    r = call(cm, 'update', arg1='Other, one', connect='log::%s; log::Carol Roe' % KIM)
    assert r['return'] == 0, r
    assert set(desc_connections(other_path)) == {'log,%s::%s,%s' % (cat_uid, KIM, kim_uid),
                                                 'log,%s::Carol Roe,%s' % (cat_uid, carol_uid)}
    assert desc_connections(kim_path) == ['log,%s::Other, one,%s' % (cat_uid, other_uid)]
    r = call(cm, 'update', arg1='Other, one', connect='-log::%s;-log::Carol Roe' % KIM)
    assert r['return'] == 0, r
    assert desc_connections(other_path) == [] and desc_connections(kim_path) == [] and desc_connections(carol_path) == []

    # {{{cRef}}}/path and the cRef alone, by the alias alone and with the UID
    with open(os.path.join(kim_path, 'README.md'), 'w', encoding='utf-8') as f:
        f.write('# Kim\n')
    for text in ('{{{log::%s,%s}}}/README.md' % (KIM, kim_uid), '{{{log::%s}}}/README.md' % KIM,
                 'log::%s,%s/README.md' % (KIM, kim_uid)):
        r = cm.access({'category': 'utils', 'command': 'find_by_cid', 'arg1': text, 'con': False})
        assert r['return'] == 0 and os.path.normcase(r['path']) == os.path.normcase(os.path.join(kim_path, 'README.md')), (text, r)
    r = cm.access({'category': 'utils', 'command': 'find_by_cid', 'arg1': 'log,%s::%s' % (cat_uid, KIM), 'con': False})
    assert r['return'] == 0 and [os.path.normcase(a['path']) for a in r['artifacts']] == [os.path.normcase(kim_path)], r


def test_move_copy_and_migrate_to_names_with_commas(cm):
    uid, path = make(cm, KIM)

    r = call(cm, 'move', arg1=KIM, arg2='Kim, CTO')
    assert r['return'] == 0, r
    assert found(cm, 'Kim, CTO') == {('Kim, CTO', uid)} and found(cm, KIM) == set()
    assert os.path.isdir(os.path.join(os.path.dirname(path), 'Kim, CTO')) and not os.path.exists(path)

    r = call(cm, 'copy', arg1='Kim, CTO', arg2='Kim, copy')
    assert r['return'] == 0, r
    (alias, copy_uid), = found(cm, 'Kim, copy')
    assert alias == 'Kim, copy' and copy_uid != uid

    # migrate: the new name with commas, a stub under the old one that a lookup by the old alias follows
    r = call(cm, 'migrate', arg1='Kim, CTO', arg2=KIM + ', CTO')
    assert r['return'] == 0, r
    assert r['migrated_to'] == '%s, CTO,%s' % (KIM, uid)
    assert found(cm, KIM + ', CTO') == {(KIM + ', CTO', uid)}
    assert found(cm, 'Kim, CTO') == {(KIM + ', CTO', uid)}


def test_the_config_category_is_known_by_its_uid_after_the_last_comma(cm):
    config_uid = cm.cfg['category_config_uid']
    for category in ('config', 'CONFIG', 'config,' + config_uid, config_uid, config_uid.upper(),
                     'old, name,' + config_uid):
        assert cm._config_call({'category': category}) is True, category
    for category in ('log', 'config,0123456789abcdef', 'config, x', 'my, config', None, 1):
        assert cm._config_call({'category': category}) is False, category


def cx(args, home):
    env = {k: v for k, v in os.environ.items() if not k.startswith('CMETA_')}
    env.update({'CMETA_HOME': str(home), 'PYTHONIOENCODING': 'utf-8'})
    p = subprocess.run([sys.executable, '-m', 'cmeta'] + list(args), env=env, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
    return p.returncode, p.stdout.decode('utf-8', 'replace'), p.stderr.decode('utf-8', 'replace')


def test_the_command_line(cm, tmp_path):
    rc, out, err = cx(['log', 'add', KIM, '-q'], tmp_path)
    assert rc == 0, out + err
    (_, uid), = found(cm, KIM)

    rc, out, err = cx(['log', 'find', KIM], tmp_path)
    assert rc == 0 and KIM in out, out + err

    rc, out, err = cx(['log', 'move', KIM, 'Kim Doe, CTO', '-q'], tmp_path)
    assert rc == 0, out + err
    assert found(cm, 'Kim Doe, CTO') == {('Kim Doe, CTO', uid)}

    rc, out, err = cx(['log', 'add', 'z,' + LIKE_UID + ',5ca1ab1e5ca1ab1e', '-q'], tmp_path)
    assert rc != 0 and 'alias,UID' in out + err, out + err
