"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

Lists on the command line whose items hold commas and ";" (the user, 2026-11-23: an alias may hold both, and so may a
path): `--key+=value` appends one whole item to a list - a value the key got before without "+" becomes its first
item - while `--key=value` alone stays a value, exactly as before; a parameter a category or a task describes as a
list (`cli_params`: type list) gets a list from one plain value too, that value never split.
"""

import os
import subprocess
import sys

import pytest
import yaml

from cmeta import CMeta
from cmeta.utils.cli import parse_cmd, typed_params_from_cli


def params(words):
    r = parse_cmd(words)
    assert r['return'] == 0, r
    return r['params']


@pytest.mark.parametrize('words, expected', [
    # as before: one value, the last one of a key given twice, the comma list
    (['--k=a'], {'k': 'a'}),
    (['--k=a, b; c'], {'k': 'a, b; c'}),
    (['--k=a', '--k=b'], {'k': 'b'}),
    (['--k,=a,b'], {'k': ['a', 'b']}),
    (['--k'], {'k': True}),

    # "+": a list from the first one, every value whole
    (['--k+=a'], {'k': ['a']}),
    (['--k+=a, b;c', '--k+=d e'], {'k': ['a, b;c', 'd e']}),
    (['--k=a', '--k+=b'], {'k': ['a', 'b']}),
    (['--k=a', '--k+=b', '--k+=c'], {'k': ['a', 'b', 'c']}),

    # a plain value after them replaces them, as a key given twice always did
    (['--k+=a', '--k=b'], {'k': 'b'}),

    # with the comma list, nested keys, dashes in the key, one dash
    (['--k,=a,b', '--k+=c'], {'k': ['a', 'b', 'c']}),
    (['--k,+=a,b', '--k+=c'], {'k': ['a', 'b', 'c']}),
    (['--meta.tags+=x', '--meta.tags+=y, z'], {'meta': {'tags': ['x', 'y, z']}}),
    (['--k-name+=x'], {'k_name': ['x']}),
    (['-k+=x'], {'k': ['x']}),

    # a value may begin with "+" or hold "+=": only the key's "+" counts
    (['--k=+a'], {'k': '+a'}),
    (['--k=a+=b'], {'k': 'a+=b'}),
])
def test_parse(words, expected):
    assert params(words) == expected


def test_a_command_line_string_and_quotes():
    assert params('run --k+="demo.person::Kim Doe, joined Example Co; 2026,5ca1ab1e5ca1ab1e" --k+=b') == {
        'args': ['run'], 'k': ['demo.person::Kim Doe, joined Example Co; 2026,5ca1ab1e5ca1ab1e', 'b']}


def _func(ctx, items=None, other=None, count: int = 0):
    pass


def test_a_described_list():
    described = {'items': {'type': 'list'}, 'count': 'int'}

    # one plain value: one item, never split
    p = {'items': 'a, b; c', 'other': 'x, y', 'count': '3'}
    r = typed_params_from_cli(_func, p, described)
    assert r['return'] == 0 and p == {'items': ['a, b; c'], 'other': 'x, y', 'count': 3}

    # a list (from "+", a comma list or a file) stays as it is
    p = {'items': ['a', 'b, c']}
    assert typed_params_from_cli(_func, p, described)['return'] == 0 and p == {'items': ['a', 'b, c']}

    # the allowed values are checked item by item
    described = {'items': {'type': 'list', 'values': ['a', 'b']}}
    assert typed_params_from_cli(_func, {'items': ['a', 'b']}, described)['return'] == 0
    r = typed_params_from_cli(_func, {'items': ['a', 'c']}, described)
    assert r['return'] == 1 and "Invalid value 'c' for 'items'" in r['error']

    # not described: as before (an annotation list is not read - its commands may split a text themselves)
    p = {'items': 'a,b'}
    assert typed_params_from_cli(_func, p, {})['return'] == 0 and p == {'items': 'a,b'}


# ------------------------------------------------------------------------------------------------- the command line
API_V1 = '''from cmeta.category import InitCategory

class Category(InitCategory):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path = __file__, **kwargs)

    def items_(self, ctx, items = None, other = None):
        return {'return': 0, 'got': {'items': items, 'other': other}}
'''

META = ('artifact: c6cat,c6c6c6c6c6c6c6c6\ncategory: category,dd9ea50e7f76467f\nlast_api_version: 1\n'
        'base_category_default_api_versions:\n  "1": 1\ncli_params:\n  items:\n    items:\n      type: list\n')


@pytest.fixture()
def described_home(tmp_path, monkeypatch):
    """A home with a category whose command "items" describes its parameter items as a list."""
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE', 'CMETA_CLI_TYPES'):
        monkeypatch.delenv(var, raising=False)
    home = tmp_path / 'home'
    monkeypatch.setenv('CMETA_HOME', str(home))
    repo = tmp_path / 'repo-c6'
    category = repo / 'category' / 'c6cat'
    (category / 'api').mkdir(parents=True)
    (repo / '_cmr.yaml').write_text('artifact: repo-c6,6666666666666666\ncategory: repo,f4f792ab40c7498f\n', encoding='utf-8')
    (category / '_cmeta.yaml').write_text(META, encoding='utf-8')
    (category / 'api' / 'v1.py').write_text(API_V1, encoding='utf-8')
    cm = CMeta(home=str(home))
    r = cm.access({'category': 'repo', 'command': 'plug', 'arg1': str(repo), 'con': False})
    assert r['return'] == 0, r.get('error')
    return {'cm': cm, 'home': home}


def got(out):
    import json
    return json.loads(out[out.index('{'):])['got']


def test_a_described_list_from_the_command_line(described_home):
    home = described_home['home']

    # one plain value: a list of one, whole; a parameter not described stays a text, as before
    rc, out, err = cx(['c6cat', 'items', '--items=a, b; c', '--other=x, y', '--json'], home)
    assert rc == 0, out + err
    assert got(out) == {'items': ['a, b; c'], 'other': 'x, y'}

    # more with "+"; a comma list as before
    rc, out, err = cx(['c6cat', 'items', '--items=a, b', '--items+=c; d', '--other+=x', '--json'], home)
    assert rc == 0, out + err
    assert got(out) == {'items': ['a, b', 'c; d'], 'other': ['x']}
    rc, out, err = cx(['c6cat', 'items', '--items,=a,b', '--json'], home)
    assert rc == 0 and got(out) == {'items': ['a', 'b'], 'other': None}, out + err

    # the Python API passes Python values, read by nobody
    r = described_home['cm'].access({'category': 'c6cat', 'command': 'items', 'items': 'a,b', 'con': False})
    assert r['return'] == 0 and r['got'] == {'items': 'a,b', 'other': None}


KIM = 'Kim Doe, joined Example Co; 2026'
ACME = 'Acme; Inc., London'


@pytest.fixture()
def home(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    return tmp_path


def cx(args, home):
    env = {k: v for k, v in os.environ.items() if not k.startswith('CMETA_')}
    env.update({'CMETA_HOME': str(home), 'PYTHONIOENCODING': 'utf-8'})
    p = subprocess.run([sys.executable, '-m', 'cmeta'] + list(args), env=env, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
    return p.returncode, p.stdout.decode('utf-8', 'replace'), p.stderr.decode('utf-8', 'replace')


def connections(path):
    p = os.path.join(path, '_desc.yaml')
    if not os.path.isfile(p):
        return []
    with open(p, encoding='utf-8') as f:
        return (yaml.safe_load(f) or {}).get('connections') or []


def test_connect_names_with_commas_and_semicolons(home):
    for alias in (KIM, ACME, 'Carol'):
        rc, out, err = cx(['log', 'add', alias, '-q'], home)
        assert rc == 0, out + err
    cm = CMeta(home=str(home))

    def art(alias):
        a = cm.access({'category': 'log', 'command': 'find', 'arg1': alias, 'con': False})['artifacts']
        assert len(a) == 1, (alias, a)
        return a[0]['cmeta_ref_parts']['artifact_uid'], a[0]['path']

    kim_uid, kim_path = art(KIM)
    acme_uid, acme_path = art(ACME)
    carol_uid, carol_path = art('Carol')
    cat_uid = cm.access({'category': 'category', 'command': 'find', 'arg1': 'log', 'con': False})['artifacts'][0]['cmeta_ref_parts']['artifact_uid']

    # each with "+", by the alias alone and by alias,UID: every name whole
    rc, out, err = cx(['log', 'update', 'Carol', '--connect+=log::' + KIM, '--connect+=log::%s,%s' % (ACME, acme_uid), '-q'], home)
    assert rc == 0, out + err
    assert set(connections(carol_path)) == {'log,%s::%s,%s' % (cat_uid, KIM, kim_uid), 'log,%s::%s,%s' % (cat_uid, ACME, acme_uid)}
    assert connections(kim_path) == ['log,%s::Carol,%s' % (cat_uid, carol_uid)]

    # removed the same way
    rc, out, err = cx(['log', 'update', 'Carol', '--connect+=-log::' + KIM, '--connect+=-log::' + ACME, '-q'], home)
    assert rc == 0, out + err
    assert connections(carol_path) == [] and connections(kim_path) == [] and connections(acme_path) == []

    # one plain value, as before: a cRef keeps its commas...
    rc, out, err = cx(['log', 'add', 'Megacorp, Inc.', '-q'], home)
    assert rc == 0, out + err
    ms_uid, _ = art('Megacorp, Inc.')
    rc, out, err = cx(['log', 'update', 'Carol', '--connect=log::Megacorp, Inc.', '-q'], home)
    assert rc == 0, out + err
    assert connections(carol_path) == ['log,%s::Megacorp, Inc.,%s' % (cat_uid, ms_uid)]

    # ...but ";" separates cRefs in it, as before: a name that holds one is given with "+"
    rc, out, err = cx(['log', 'update', 'Carol', '--connect=log::%s,%s' % (KIM, kim_uid), '-q'], home)
    assert rc != 0 and 'Kim Doe, joined Example Co"' in out + err, out + err
