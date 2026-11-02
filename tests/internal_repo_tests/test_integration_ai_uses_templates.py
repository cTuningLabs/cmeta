"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

The AI context of an artifact chosen from declared templates (2026-11-02): an artifact declares itself a
template for `ai_uses` in its meta (template: ai_uses: {alias, title, sort}); `add`/`update` with
`ai_uses`/`ai` write the full cRefs into the artifact's _desc.yaml (appended, no duplicates), a name is a
template alias first, then an artifact alias in any category, then a cRef, and an ambiguity is an error
naming the candidates; `desc` merges any keys into _desc.yaml; a _desc.json is converted; a quiet run with
`ai` True asks nothing. Each test runs in a fresh CMETA_HOME.
"""

import os

import pytest
import yaml

from cmeta import CMeta


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    """A fresh CMeta bound to a temp CMETA_HOME."""
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    return CMeta(home=str(tmp_path))


def add(cm, category, alias, **params):
    r = cm.access({'category': category, 'command': 'add', 'arg1': 'local:' + alias, 'con': False, **params})
    assert r['return'] == 0, r
    return r


def cref(r):
    m = r['meta']
    return f"{m['category']}::{m.get('alias') or ''},{m['artifact']}".replace('::,', '::')


def desc_of(path):
    p = os.path.join(path, '_desc.yaml')
    assert os.path.isfile(p), os.listdir(path)
    with open(p, encoding='utf-8') as f:
        return yaml.safe_load(f)


def test_templates_are_declared_in_the_meta_and_written_as_full_crefs(cm):
    a = add(cm, 'config', 'ctx-cmeta', meta={'template': {'ai_uses': {'alias': 'cmeta', 'title': 'cMeta rules', 'sort': 10}}})
    b = add(cm, 'config', 'ctx-fgg', meta={'template': {'ai_uses': {'alias': 'fgg', 'title': 'FGG context', 'sort': 30}}})
    add(cm, 'config', 'plain-one')

    # the list: sorted by sort, with the full cRefs
    api = cm.access({'category': 'config', 'command': 'find', 'arg1': 'local:ctx-cmeta', 'con': False})
    assert api['return'] == 0
    cat = cm.access({'category': 'category', 'command': 'find', 'arg1': 'config', 'con': False})
    assert cat['return'] == 0

    # a new artifact with two contexts by their template aliases
    r = add(cm, 'config', 'my-work', ai='cmeta,fgg')
    d = desc_of(r['path'])
    assert len(d['ai_uses']) == 2
    assert d['ai_uses'][0].endswith('::ctx-cmeta,' + a['meta']['artifact']) and d['ai_uses'][0].startswith('config,')
    assert d['ai_uses'][1].endswith('::ctx-fgg,' + b['meta']['artifact'])

    # update appends without duplicates: an artifact alias (no template), the same alias again, a cRef
    r = cm.access({'category': 'config', 'command': 'update', 'arg1': 'local:my-work', 'con': False, 'ai_uses': 'plain-one,cmeta'})
    assert r['return'] == 0 and len(r['updated_artifacts']) == 1
    d = desc_of(r['updated_artifacts'][0]['path'])
    assert len(d['ai_uses']) == 3 and d['ai_uses'][2].startswith('config,') and '::plain-one,' in d['ai_uses'][2]
    r = cm.access({'category': 'config', 'command': 'update', 'arg1': 'local:my-work', 'con': False, 'ai': d['ai_uses'][0]})
    assert r['return'] == 0
    assert desc_of(r['artifacts'][0]['path'])['ai_uses'] == d['ai_uses']        # a cRef already there: nothing added


def test_an_ambiguous_name_is_refused_with_the_candidates_and_a_cref_picks_one(cm):
    add(cm, 'category', 'notes')
    x = add(cm, 'config', 'twin')
    y = add(cm, 'notes', 'twin')
    r = cm.access({'category': 'config', 'command': 'add', 'arg1': 'local:w', 'con': False, 'ai': 'twin'})
    assert r['return'] == 1 and 'several artifacts' in r['error']
    assert 'config,' in r['error'] and 'notes,' in r['error'] and '::twin,' in r['error']
    assert not os.path.isdir(os.path.join(os.path.dirname(x['path']), 'w'))       # refused before anything is made
    r = cm.access({'category': 'config', 'command': 'add', 'arg1': 'local:w2', 'con': False, 'ai': 'notes::twin'})
    assert r['return'] == 0
    assert desc_of(r['path'])['ai_uses'] == [f"notes,{cm.access({'category': 'category', 'command': 'find', 'arg1': 'notes', 'con': False})['artifacts'][0]['cmeta']['artifact']}::twin,{y['meta']['artifact']}"]
    # two templates with the same alias: refused too
    add(cm, 'config', 'ctx-a', meta={'template': {'ai_uses': {'alias': 'same', 'title': 'A'}}})
    add(cm, 'config', 'ctx-b', meta={'template': {'ai_uses': {'alias': 'same', 'title': 'B'}}})
    r = cm.access({'category': 'config', 'command': 'add', 'arg1': 'local:w3', 'con': False, 'ai': 'same'})
    assert r['return'] == 1 and 'declared by several artifacts' in r['error'] and '::ctx-a,' in r['error'] and '::ctx-b,' in r['error']
    r = cm.access({'category': 'config', 'command': 'add', 'arg1': 'local:w4', 'con': False, 'ai': 'nobody'})
    assert r['return'] == 1 and 'no artifact for the name "nobody"' in r['error']
    assert not os.path.isdir(os.path.join(os.path.dirname(x['path']), 'w3')) and not os.path.isdir(os.path.join(os.path.dirname(x['path']), 'w4'))
    # an update with an unknown name changes nothing either
    before = desc_of(r2 := cm.access({'category': 'config', 'command': 'find', 'arg1': 'local:w2', 'con': False})['artifacts'][0]['path'])
    r = cm.access({'category': 'config', 'command': 'update', 'arg1': 'local:w2', 'con': False, 'ai': 'nobody'})
    assert r['return'] == 1 and 'nobody' in r['error'] and desc_of(r2) == before


def test_update_keeps_the_text_of_a_hand_written_desc_yaml(cm):
    add(cm, 'config', 'ctx', meta={'template': {'ai_uses': {'alias': 'ctx', 'title': 'C'}}})
    r = add(cm, 'config', 'w')
    text = ('# the links of the graph\nconnections:\n- a,1::b,2   # kept as it is\n\n'
            '# ai_uses: what the AI sessions of this artifact read\nai_uses:\n  - "x,1::y,2"\n  # an item note\n\nnotes: keep me\n')
    with open(os.path.join(r['path'], '_desc.yaml'), 'w', encoding='utf-8', newline='') as f:
        f.write(text)
    r = cm.access({'category': 'config', 'command': 'update', 'arg1': 'local:w', 'con': False, 'ai': 'ctx'})
    assert r['return'] == 0
    with open(os.path.join(r['artifacts'][0]['path'], '_desc.yaml'), encoding='utf-8', newline='') as f:
        after = f.read()
    cref = desc_of(r['artifacts'][0]['path'])['ai_uses'][1]
    assert after == text.replace('  - "x,1::y,2"\n', '  - "x,1::y,2"\n  - ' + cref + '\n')       # one line after the last item, nothing else touched
    assert desc_of(r['artifacts'][0]['path']) == {'connections': ['a,1::b,2'], 'ai_uses': ['x,1::y,2', cref], 'notes': 'keep me'}
    # a file without the key gets the block at its end; other keys through --desc keep the text too (preserve)
    r2 = add(cm, 'config', 'w2')
    with open(os.path.join(r2['path'], '_desc.yaml'), 'w', encoding='utf-8', newline='') as f:
        f.write('# only notes\nnotes: first\n')
    r = cm.access({'category': 'config', 'command': 'update', 'arg1': 'local:w2', 'con': False, 'ai': 'ctx', 'desc': {'ck': {'owner': 'me'}}})
    assert r['return'] == 0
    with open(os.path.join(r2['path'], '_desc.yaml'), encoding='utf-8') as f:
        after = f.read()
    assert after.startswith('# only notes\nnotes: first\n') and desc_of(r2['path']) == {'notes': 'first', 'ck': {'owner': 'me'}, 'ai_uses': [cref]}


def test_a_star_in_match_means_any_value_so_the_index_search_lists_the_templates(cm):
    add(cm, 'config', 'ctx-a', meta={'template': {'ai_uses': {'alias': 'a', 'title': 'A'}}})
    add(cm, 'config', 'ctx-b', meta={'template': {'ai_uses': {'alias': 'b', 'title': 'B'}}})
    add(cm, 'config', 'plain')
    aliases = lambda r: sorted(a['cmeta_ref_parts']['artifact_alias'] for a in r['artifacts'])
    r = cm.access({'category': 'config', 'command': 'find', 'con': False, 'match': {'template': {'ai_uses': {'alias': '*'}}}})
    assert r['return'] == 0 and aliases(r) == ['ctx-a', 'ctx-b']
    r = cm.access({'category': 'utils', 'command': 'find_by_cid', 'arg1': '*::*', 'con': False, 'match': {'template': {'ai_uses': '*'}}})
    assert r['return'] == 0 and aliases(r) == ['ctx-a', 'ctx-b']
    r = cm.access({'category': 'config', 'command': 'find', 'con': False, 'match': {'template': {'ai_uses': {'alias': 'a'}}}})
    assert aliases(r) == ['ctx-a']                                                      # an exact value as before


def test_desc_keys_merge_and_a_desc_json_is_converted_and_quiet_asks_nothing(cm):
    r = add(cm, 'config', 'd1', desc={'ck': {'owner': 'me'}, 'notes': ['first']})
    d = desc_of(r['path'])
    assert d == {'ck': {'owner': 'me'}, 'notes': ['first']}
    # a _desc.json left by hand is converted when the next write comes, never both files
    os.remove(os.path.join(r['path'], '_desc.yaml'))
    with open(os.path.join(r['path'], '_desc.json'), 'w', encoding='utf-8') as f:
        f.write('{"ck": {"owner": "me"}, "ai_uses": ["config,x::old,y"]}')
    add(cm, 'config', 'ctx', meta={'template': {'ai_uses': {'alias': 'ctx', 'title': 'C'}}})
    r = cm.access({'category': 'config', 'command': 'update', 'arg1': 'local:d1', 'con': False, 'ai': 'ctx', 'desc': {'notes': ['second']}})
    assert r['return'] == 0 and len(r['updated_artifacts']) == 1
    p = r['updated_artifacts'][0]['path']
    assert not os.path.isfile(os.path.join(p, '_desc.json'))
    d = desc_of(p)
    assert d['ck'] == {'owner': 'me'} and d['notes'] == ['second'] and d['ai_uses'][0] == 'config,x::old,y' and '::ctx,' in d['ai_uses'][1]
    # quiet + ask: nothing asked, nothing written
    r = cm.access({'category': 'config', 'command': 'add', 'arg1': 'local:q1', 'con': False, 'quiet': True, 'ai': True})
    assert r['return'] == 0 and not os.path.isfile(os.path.join(r['path'], '_desc.yaml'))
    # no templates and no names: nothing written either
    r = cm.access({'category': 'config', 'command': 'add', 'arg1': 'local:q2', 'con': False, 'ai_uses': ''})
    assert r['return'] == 0 and not os.path.isfile(os.path.join(r['path'], '_desc.yaml'))
