"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

The AI context of an artifact chosen from declared templates (2026-11-02): an artifact declares itself a
template for `ai_uses` in its meta (template: ai_uses: {alias, title, sort}); `add`/`update` with
`ai_uses`/`ai` write the full cRefs into the artifact's _desc.yaml (appended, no duplicates), a name is a
template alias first, then an artifact alias in any category, then a cRef, and an ambiguity is an error
naming the candidates; `desc` merges any keys into _desc.yaml; a _desc.json is converted; a quiet run with
`ai` True asks nothing; `meta` and `desc` refuse a text (2026-11-05: `--desc=@file.yaml` reads no file - a whole
argument `@file.yaml` holding `desc:` does). Each test runs in a fresh CMETA_HOME.
"""

import os
import subprocess
import sys

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


def meta_file_of(path):
    return next(os.path.join(path, f) for f in ('_cmeta.json', '_cmeta.yaml') if os.path.isfile(os.path.join(path, f)))


def test_meta_and_desc_refuse_a_text_before_anything_is_made_or_changed(cm):
    # 2026-11-05: "update --desc=@keys.yaml" said "Artifact was updated" and wrote nothing (a flag's value is never
    # read as a file; a desc that was not keys was dropped), "--meta=@keys.yaml" broke with an AttributeError
    r = add(cm, 'config', 't1')
    meta_file = meta_file_of(r['path'])
    with open(meta_file, 'rb') as f:
        before = f.read()

    for params in ({'desc': '@keys.yaml'}, {'desc': 'hello'}, {'desc': ['a', 'b']}, {'meta': '@keys.yaml'}, {'meta': 'x'}):
        name = next(iter(params))
        r2 = cm.access({'category': 'config', 'command': 'update', 'arg1': 'local:t1', 'con': False, **params})
        assert r2['return'] == 1, (params, r2)
        assert r2['error'].startswith(f'"{name}" takes keys, not ') and f'--{name}.<key>=<value>' in r2['error'], r2
        assert f'holding {name}: {{...}}' in r2['error'], r2
        assert ('reads no file' in r2['error']) == str(params[name]).startswith('@'), r2

    assert not os.path.isfile(os.path.join(r['path'], '_desc.yaml'))
    with open(meta_file, 'rb') as f:
        assert f.read() == before                                                   # nothing written

    # add, get and set: refused before an artifact is made
    for command, params in (('add', {'desc': '@keys.yaml'}), ('add', {'meta': 'x'}), ('get', {'meta': 'x'}),
                            ('get', {'desc': 'x'}), ('set', {'meta': 'x'})):
        r3 = cm.access({'category': 'config', 'command': command, 'arg1': 'local:t2', 'con': False, **params})
        assert r3['return'] == 1 and 'takes keys' in r3['error'], (command, params, r3)
        assert cm.access({'category': 'config', 'command': 'find', 'arg1': 'local:t2', 'con': False})['return'] == 16

    # repo get: refused before anything is fetched (a text crashed after the clone, with _cmr.yaml locked)
    r6 = cm.access({'category': 'repo', 'command': 'get', 'arg1': 'never-made', 'url': 'https://example.invalid/x.git',
                    'con': False, 'meta': '@m.yaml'})
    assert r6['return'] == 1 and r6['error'].startswith('"meta" takes keys') and 'reads no file' in r6['error'], r6
    assert not os.path.exists(os.path.join(cm.repos_path, 'never-made'))

    # an empty value is no keys, as before; keys work as before
    r4 = cm.access({'category': 'config', 'command': 'update', 'arg1': 'local:t1', 'con': False, 'desc': '', 'meta': ''})
    assert r4['return'] == 0 and not os.path.isfile(os.path.join(r['path'], '_desc.yaml')), r4
    r5 = cm.access({'category': 'config', 'command': 'update', 'arg1': 'local:t1', 'con': False, 'desc': {'note': 'x'}})
    assert r5['return'] == 0 and desc_of(r['path']) == {'note': 'x'}, r5


def cx(args, home, cwd):
    env = {k: v for k, v in os.environ.items() if not k.startswith('CMETA_')}
    env.update({'CMETA_HOME': str(home), 'PYTHONIOENCODING': 'utf-8'})
    p = subprocess.run([sys.executable, '-m', 'cmeta'] + list(args), env=env, cwd=str(cwd), stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
    return p.returncode, p.stdout.decode('utf-8', 'replace') + p.stderr.decode('utf-8', 'replace')


def test_the_command_line_takes_several_keys_from_a_whole_file_argument(cm, tmp_path):
    r = add(cm, 'config', 'c1')
    work = tmp_path / 'work'
    work.mkdir()
    (work / 'keys.yaml').write_text('note: from keys.yaml\n', encoding='utf-8')
    (work / 'desc.yaml').write_text('desc:\n  note: from desc.yaml\n  owner: me\n', encoding='utf-8')

    # a flag's value is a text: refused with the way to do it, nothing written
    rc, out = cx(['config', 'update', 'local:c1', '--desc=@keys.yaml'], tmp_path, work)
    assert rc != 0 and '"desc" takes keys' in out and '--desc=@<file> reads no file' in out, out
    assert not os.path.isfile(os.path.join(r['path'], '_desc.yaml'))
    rc, out = cx(['config', 'update', 'local:c1', '--meta=@keys.yaml'], tmp_path, work)
    assert rc != 0 and '"meta" takes keys' in out and 'AttributeError' not in out, out

    # the whole argument @desc.yaml: its desc keys merged into _desc.yaml
    rc, out = cx(['config', 'update', 'local:c1', '@desc.yaml'], tmp_path, work)
    assert rc == 0, out
    assert desc_of(r['path']) == {'note': 'from desc.yaml', 'owner': 'me'}
