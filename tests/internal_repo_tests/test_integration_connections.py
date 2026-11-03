"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

The connections and the AI context of an artifact through add / update (2026-11-03): `connect` writes the full
cRef of each artifact named into this artifact's `connections` and this artifact's cRef into theirs,
`connect_to` (`ct`) this side only; a name with "-" in front removes (both sides with `connect`), also a name
whose artifact is gone; entries are compared by the artifact's UID, so an entry written before a rename is
neither duplicated nor left behind; `ai` removes the same way; the categories that add through `get` (dated
aliases: work) take the same options; a hand-written _desc.yaml keeps its text; a single value given with
--desc.<list>= is appended, never put in the place of the list; the question of `ai` / `connect` / `ct`
lists what the artifact has first ("-N": chosen = removed). Each test runs in a fresh CMETA_HOME.
"""

import os

import pytest
import yaml

from cmeta import CMeta
from cmeta import category_api_v1 as api


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    """A fresh CMeta bound to a temp CMETA_HOME."""
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    return CMeta(home=str(tmp_path))


def add(cm, alias, category='config', **params):
    r = cm.access({'category': category, 'command': 'add', 'arg1': 'local:' + alias, 'con': False, **params})
    assert r['return'] == 0, r
    return r


def update(cm, alias, category='config', **params):
    r = cm.access({'category': category, 'command': 'update', 'arg1': 'local:' + alias, 'con': False, **params})
    assert r['return'] == 0, r
    return r


def cref(r):
    m = r['meta']
    return f"{m['category']}::{m.get('alias') or ''},{m['artifact']}".replace('::,', '::')


def desc_of(path):
    p = os.path.join(path, '_desc.yaml')
    if not os.path.isfile(p):
        return {}
    with open(p, encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def uids(path, key='connections'):
    return [str(c).split(',')[-1] for c in desc_of(path).get(key) or []]


def test_connect_writes_both_sides_once_and_ct_one_side(cm):
    a, b, c = add(cm, 'a'), add(cm, 'b'), add(cm, 'c')
    update(cm, 'a', connect='b')
    update(cm, 'a', connect='b')                                       # again: no duplicate
    assert uids(a['path']) == [b['meta']['artifact']] and uids(b['path']) == [a['meta']['artifact']]
    assert desc_of(a['path'])['connections'][0].startswith('config,') and '::b,' in desc_of(a['path'])['connections'][0]
    r = update(cm, 'a', ct='c')                                        # this side only (connect_to)
    assert uids(a['path']) == [b['meta']['artifact'], c['meta']['artifact']] and desc_of(c['path']) == {}
    assert any('Connections in' in x for x in r['desc_changes'])


def test_a_dash_removes_from_both_sides_or_this_one_and_a_gone_artifact_by_its_name(cm):
    a, b, c = add(cm, 'a'), add(cm, 'b'), add(cm, 'c')
    update(cm, 'a', connect='b;c')
    update(cm, 'a', connect_to='-c')                                   # this side only: c keeps its entry
    assert uids(a['path']) == [b['meta']['artifact']] and uids(c['path']) == [a['meta']['artifact']]
    update(cm, 'a', connect='-b')                                      # both sides
    assert 'connections' not in desc_of(a['path']) and 'connections' not in desc_of(b['path'])
    # an artifact that is gone: removed by what the entry says
    d = add(cm, 'd')
    update(cm, 'a', ct='d')
    assert cm.access({'category': 'config', 'command': 'rm', 'arg1': 'local:d', 'force': True, 'con': False})['return'] == 0
    update(cm, 'a', ct='-d')
    assert 'connections' not in desc_of(a['path'])
    # a name to add must exist
    r = cm.access({'category': 'config', 'command': 'update', 'arg1': 'local:a', 'con': False, 'connect': 'nothing-here'})
    assert r['return'] > 0 and 'no artifact' in r['error']


def test_entries_are_the_same_artifact_by_uid_after_a_rename(cm):
    a, b = add(cm, 'a'), add(cm, 'b')
    old = f"{b['meta']['category']}::old-name,{b['meta']['artifact']}"
    with open(os.path.join(a['path'], '_desc.yaml'), 'w', encoding='utf-8') as f:
        f.write('connections:\n  - ' + old + '\n')
    update(cm, 'a', ct='b')
    assert desc_of(a['path'])['connections'] == [old]                  # not added again under the new alias
    update(cm, 'a', ct='-b')
    assert desc_of(a['path']) == {}                                    # and removed by its UID


def test_ai_removes_with_a_dash(cm):
    add(cm, 'ctx', meta={'template': {'ai_uses': {'alias': 'ctx', 'title': 'C'}}})
    w = add(cm, 'w', ai='ctx')
    assert len(desc_of(w['path'])['ai_uses']) == 1
    update(cm, 'w', ai='-ctx')
    assert desc_of(w['path']) == {}


def test_categories_that_add_through_get_take_the_options(cm):
    # work makes a dated alias and adds through "get": "-ai" failed with "unexpected keyword argument 'ai'"
    add(cm, 'ctx', meta={'template': {'ai_uses': {'alias': 'ctx', 'title': 'C'}}})
    other = add(cm, 'other')
    r = cm.access({'category': 'work', 'command': 'add', 'arg1': 'improve fgg dashboard', 'con': False,
                   'ai': 'ctx', 'connect': 'other'})
    assert r['return'] == 0, r
    path = r['artifact']['path']
    assert len(desc_of(path)['ai_uses']) == 1 and uids(path) == [other['meta']['artifact']]
    assert uids(other['path']) == [r['artifact']['cmeta']['artifact']]
    assert r['desc_changes']


def test_a_hand_written_desc_keeps_its_text(cm):
    a, b, c = add(cm, 'a'), add(cm, 'b'), add(cm, 'c')
    bc = desc_of(add(cm, 'tmp', ct='b;c')['path'])['connections']      # the full cRefs of b and c
    text = ('# the graph of a\nnotes: keep me   # a note\n\nconnections:\n  # the first\n  - ' + bc[0] +
            '   # why b\n  - ' + bc[1] + '\n\nmore: end\n')
    with open(os.path.join(a['path'], '_desc.yaml'), 'w', encoding='utf-8', newline='') as f:
        f.write(text)
    update(cm, 'a', ct='-b')
    with open(os.path.join(a['path'], '_desc.yaml'), encoding='utf-8', newline='') as f:
        after = f.read()
    assert after == text.replace('  - ' + bc[0] + '   # why b\n', '')       # its line alone, the comments kept
    update(cm, 'a', ct='-c')                                           # the list empty: its key goes
    with open(os.path.join(a['path'], '_desc.yaml'), encoding='utf-8', newline='') as f:
        assert f.read() == '# the graph of a\nnotes: keep me   # a note\n\nmore: end\n'


def test_desc_with_a_single_value_appends_to_a_list(cm):
    a = add(cm, 'a')
    update(cm, 'a', desc={'connections': 'x,1111111111111111::k,2222222222222222'})
    update(cm, 'a', desc={'connections': 'y,3333333333333333::l,4444444444444444'})
    assert desc_of(a['path'])['connections'] == ['x,1111111111111111::k,2222222222222222', 'y,3333333333333333::l,4444444444444444']
    update(cm, 'a', desc={'tags': ['t1']})
    update(cm, 'a', desc={'tags': 't2'})                               # any list: appended, not replaced
    assert desc_of(a['path'])['tags'] == ['t1', 't2']


def test_edit_list_text_keeps_crlf_and_refuses_an_inline_list():
    text = 'notes: n\r\nconnections:\r\n  - a,1::b,2\r\n'
    new = api.edit_list_text(text, 'connections', ['c,3::d,4'])
    assert new == 'notes: n\r\nconnections:\r\n  - a,1::b,2\r\n  - c,3::d,4\r\n'
    assert api.edit_list_text('connections: [a, b]\n', 'connections', ['c']) is None
    assert api.edit_list_text('notes: n\n', 'connections', [], lambda v: True) == 'notes: n\n'


def test_the_question_lists_what_the_artifact_has_first(cm, monkeypatch, capsys):
    add(cm, 'ctx1', meta={'template': {'ai_uses': {'alias': 'one', 'title': 'The first', 'sort': 1}}})
    add(cm, 'ctx2', meta={'template': {'ai_uses': {'alias': 'two', 'title': 'The second', 'sort': 2}}})
    w = add(cm, 'w', ai='two')
    answers = iter(['-1, 2'])
    monkeypatch.setattr(api.utils.common, 'ask', lambda *a, **k: {'return': 0, 'answer': next(answers)})
    update(cm, 'w', ai=True)
    out = capsys.readouterr().out
    assert out.index('-1  two') < out.index('2  one') and '(in use)' in out and '-1 removes two; 2 adds one' in out
    assert [c.split('::')[1].split(',')[0] for c in desc_of(w['path'])['ai_uses']] == ['ctx1']
    # a number that is not in the list, a "-N" for what is not in use: errors that say so
    for answer, error in (('9', 'not in the list'), ('-2', 'is not in use')):
        monkeypatch.setattr(api.utils.common, 'ask', lambda *a, answer=answer, **k: {'return': 0, 'answer': answer})
        r = cm.access({'category': 'config', 'command': 'update', 'arg1': 'local:w', 'con': False, 'ai': True})
        assert r['return'] > 0 and error in r['error'], r
