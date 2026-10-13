"""
The words of the command line, read by what a command expects (cMeta 0.37): for the parameters a keyword-style
command annotates `bool`, the words yes/no, true/false, on/off and 1/0 become booleans (before, `--x=no` handed
the command the string 'no', which is true); a category can describe sensitive parameters of a command in its
`_cmeta` (`cli_params`: a type, allowed values, a range) and they are converted and checked; everything else is as
it was. The Python API is not read: a caller passes Python values. `CMETA_CLI_TYPES=off` and `cli_types: false`
in a category's `_cmeta` keep the words text.

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import json
import os
import subprocess
import sys

import pytest

from cmeta import CMeta
from cmeta.utils import cli
from cmeta.utils.cli import bool_params_of, typed_params_from_cli


###################################################################################################
# The helper

def sample(ctx, flag: bool = False, other: bool = None, count: int = 0, name: str = None, items: list = None, free = None):
    pass


@pytest.mark.parametrize('word,expected', [
    ('yes', True), ('YES', True), (' true ', True), ('on', True), ('1', True),
    ('no', False), ('False', False), ('off', False), ('OFF', False), ('0', False),
])
def test_every_word_of_a_bool(word, expected):
    params = {'flag': word}

    r = typed_params_from_cli(sample, params)

    assert r['return'] == 0 and params['flag'] is expected and r['converted'] == {'flag': expected}


def test_only_the_strings_of_bool_parameters_change():
    params = {'flag': 'no', 'other': True, 'count': '5', 'name': 'yes', 'items': ['yes'], 'free': 'no',
              'unknown': 'no', 'nested': {'flag': 'no'}}
    before = dict(params)

    r = typed_params_from_cli(sample, params)

    assert r['return'] == 0 and r['converted'] == {'flag': False}
    assert params['flag'] is False

    for name in before:
        if name != 'flag':
            assert params[name] == before[name], name


@pytest.mark.parametrize('word', ['auto', '', ' ', 'yess', 'n', 'TRUE!'])
def test_a_word_that_is_not_a_bool_is_an_error(word):
    r = typed_params_from_cli(sample, {'flag': word}, where=' of "x y"')

    assert r['return'] == 1
    assert r['error'] == f"Invalid bool value '{word}' for 'flag' of \"x y\": use yes/no, true/false, on/off, 1/0 or the flags --flag / --flag-"


def test_the_place_of_an_error_can_be_computed_only_when_needed():
    calls = []

    def where():
        calls.append(1)
        return ' of "late"'

    assert typed_params_from_cli(sample, {'flag': 'no'}, where=where)['return'] == 0 and calls == []
    assert 'of "late"' in typed_params_from_cli(sample, {'flag': 'x'}, where=where)['error'] and calls == [1]


def test_the_annotations_of_future_annotations_are_strings_and_are_read():
    namespace = {}
    exec('from __future__ import annotations\n'
         'def f(ctx, a: bool = False, b: int = 0, c: str = None): pass\n', namespace)

    assert bool_params_of(namespace['f']) == frozenset({'a'})


def test_a_bound_method_and_a_function_without_a_signature():
    class Api:
        def run(self, ctx, flag: bool = False, count: int = 0):
            pass

    assert bool_params_of(Api().run) == frozenset({'flag'})
    assert bool_params_of(print) == frozenset()

    params = {'a': 'no'}
    assert typed_params_from_cli(print, params) == {'return': 0, 'converted': {}} and params == {'a': 'no'}


def test_described_parameters_are_converted_and_checked():
    described = {'count': 'int', 'ratio': {'type': 'float', 'min': 0, 'max': 1}, 'mode': {'values': ['fast', 'full']},
                 'name': 'str', 'size': {'type': 'INT', 'min': 1}, 'odd': 'no-such-type', 'absent': 'int'}

    params = {'count': '7', 'ratio': '0.5', 'mode': 'fast', 'name': 'x', 'size': '3', 'odd': '1'}
    r = typed_params_from_cli(sample, params, described, where=' of "t"')
    assert r['return'] == 0, r
    assert params == {'count': 7, 'ratio': 0.5, 'mode': 'fast', 'name': 'x', 'size': 3, 'odd': '1'}
    assert r['converted'] == {'count': 7, 'ratio': 0.5, 'size': 3}

    for params, text in (({'count': 'ten'}, "Invalid int value 'ten' for 'count' of \"t\""),
                         ({'ratio': 'x'}, "Invalid float value 'x' for 'ratio' of \"t\""),
                         ({'ratio': '1.5'}, "Invalid value 1.5 for 'ratio' of \"t\": must be at most 1"),
                         ({'size': '0'}, "Invalid value 0 for 'size' of \"t\": must be at least 1"),
                         ({'mode': 'auto'}, "Invalid value 'auto' for 'mode' of \"t\": must be one of fast, full"),
                         ({'mode': True}, "Invalid value 'True' for 'mode' of \"t\": must be one of fast, full")):
        r = typed_params_from_cli(sample, params, described, where=' of "t"')
        assert r['return'] == 1 and r['error'] == text, r

    # A described bool says the same as an annotated one; a value that cannot be compared with a bound is left alone
    r = typed_params_from_cli(sample, {'free': 'maybe'}, {'free': 'bool'})
    assert r['return'] == 1 and r['error'].startswith("Invalid bool value 'maybe' for 'free': use yes/no")

    params = {'count': 'x'}
    assert typed_params_from_cli(sample, params, {'count': {'min': 1}})['return'] == 0 and params == {'count': 'x'}


@pytest.mark.parametrize('value,enabled', [(None, True), ('', True), ('on', True), ('1', True), ('anything', True),
                                           ('off', False), ('OFF ', False), ('0', False), ('no', False), ('false', False)])
def test_the_environment_switch(monkeypatch, value, enabled):
    if value is None:
        monkeypatch.delenv(cli.CLI_TYPES_ENV, raising=False)
    else:
        monkeypatch.setenv(cli.CLI_TYPES_ENV, value)

    assert cli.cli_types_enabled() is enabled


###################################################################################################
# The engine: a category with commands of each style, through the Python API and the command line

CATEGORY_UID = 'c5c5c5c5c5c5c5c5'
OFF_CATEGORY_UID = 'c5c5c5c5c5c5c5c6'

API_V1 = '''from cmeta.category import InitCategory

class Category(InitCategory):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path = __file__, **kwargs)

    def typed_(self, ctx, flag: bool = False, other: bool = None, count: int = 0, name: str = None, free = None):
        return {'return': 0, 'got': {'flag': flag, 'other': other, 'count': count, 'name': name, 'free': free}}

    def nested_(self, ctx, flag: bool = False):
        # a nested call passes Python values and is not read, whatever the request that started it
        r = self.cm.access({'category': 'c5cat', 'command': 'typed', 'flag': 'no', 'con': False})
        if r['return'] > 0: return r
        return {'return': 0, 'flag': flag, 'inner': r['got']['flag']}

    def asdict__(self, params):
        return {'return': 0, 'got': params.get('flag')}
'''

META = 'artifact: {alias},{uid}\ncategory: category,dd9ea50e7f76467f\nlast_api_version: 1\nbase_category_default_api_versions:\n  "1": 1\n'

DESCRIBED = 'cli_params:\n  typed:\n    count: int\n    name:\n      values: [a, b]\n'


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """A home of the test with a repository of two categories: one with described parameters, one switched off."""
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE', cli.CLI_TYPES_ENV):
        monkeypatch.delenv(var, raising=False)

    home = tmp_path / 'home'
    monkeypatch.setenv('CMETA_HOME', str(home))

    repo = tmp_path / 'repo-c5'
    (repo / '_cmr.yaml').parent.mkdir(parents=True)
    (repo / '_cmr.yaml').write_text('artifact: repo-c5,2222222222222222\ncategory: repo,f4f792ab40c7498f\n', encoding='utf-8')

    for alias, uid, extra in (('c5cat', CATEGORY_UID, DESCRIBED), ('c5off', OFF_CATEGORY_UID, 'cli_types: false\n')):
        category = repo / 'category' / alias
        (category / 'api').mkdir(parents=True)
        (category / '_cmeta.yaml').write_text(META.format(alias=alias, uid=uid) + extra, encoding='utf-8')
        (category / 'api' / 'v1.py').write_text(API_V1, encoding='utf-8')

    cm = CMeta(home=str(home))
    r = cm.access({'category': 'repo', 'command': 'plug', 'arg1': str(repo), 'con': False})
    assert r['return'] == 0, r.get('error')

    return {'cm': cm, 'home': home}


def typed(cm, category='c5cat', from_cli=True, **params):
    request = {'category': category, 'command': 'typed', 'con': False}
    request.update(params)

    if from_cli:
        request['_cli'] = {'cmd': [category, 'typed']}      # what cmeta/cli.py adds to the request it makes

    return cm.access(request)


def test_the_python_api_is_not_read(home):
    r = typed(home['cm'], from_cli=False, flag='no', other='yes', count='7', name='a', free='no')

    assert r['return'] == 0 and r['got'] == {'flag': 'no', 'other': 'yes', 'count': '7', 'name': 'a', 'free': 'no'}


def test_the_request_of_the_command_line_is_read(home):
    r = typed(home['cm'], flag='no', other='yes', count='7', name='a', free='no')

    assert r['return'] == 0, r.get('error')
    assert r['got'] == {'flag': False, 'other': True, 'count': 7, 'name': 'a', 'free': 'no'}

    # The flags are what they were
    r = typed(home['cm'], flag=True, other=False)
    assert r['got']['flag'] is True and r['got']['other'] is False


def test_a_nested_call_is_not_read(home):
    r = home['cm'].access({'category': 'c5cat', 'command': 'nested', 'flag': 'yes', 'con': False, '_cli': {'cmd': []}})

    assert r['return'] == 0, r.get('error')
    assert r['flag'] is True and r['inner'] == 'no'


def test_a_dict_style_command_is_not_read(home):
    r = home['cm'].access({'category': 'c5cat', 'command': 'asdict', 'flag': 'no', 'con': False, '_cli': {'cmd': []}})

    assert r['return'] == 0 and r['got'] == 'no'


def test_the_switches(home, monkeypatch):
    assert typed(home['cm'], category='c5off', flag='no')['got']['flag'] == 'no'

    monkeypatch.setenv(cli.CLI_TYPES_ENV, 'off')
    assert typed(home['cm'], flag='no', count='7')['got'] == {'flag': 'no', 'other': None, 'count': '7', 'name': None, 'free': None}


def test_errors_name_the_command(home):
    for params, text in ((dict(flag='auto'), "Invalid bool value 'auto' for 'flag' of \"c5cat typed\": use yes/no, true/false, on/off, 1/0 or the flags --flag / --flag-"),
                         (dict(count='x'), "Invalid int value 'x' for 'count' of \"c5cat typed\""),
                         (dict(name='c'), "Invalid value 'c' for 'name' of \"c5cat typed\": must be one of a, b")):
        r = typed(home['cm'], **params)

        assert r['return'] > 0 and r['error'].startswith(text), r
        assert 'Rerun with --help' in r['error']


def cx(args, env_home, **env_extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith('CMETA_')}
    env.update({'CMETA_HOME': str(env_home), 'PYTHONIOENCODING': 'utf-8'})
    env.update(env_extra)
    p = subprocess.run([sys.executable, '-m', 'cmeta'] + list(args), env=env, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
    return p.returncode, p.stdout.decode('utf-8', 'replace'), p.stderr.decode('utf-8', 'replace')


def got(out):
    return json.loads(out[out.index('{'):])['got']


def test_the_command_line_end_to_end(home):
    rc, out, err = cx(['c5cat', 'typed', '--flag=no', '--other=1', '--count=7', '--name=b', '--free=no', '--json'], home['home'])
    assert rc == 0, out + err
    assert got(out) == {'flag': False, 'other': True, 'count': 7, 'name': 'b', 'free': 'no'}

    # The engine's own commands: the test command of the cache category annotates flag1 bool
    rc, out, err = cx(['cache', 'test', '--flag1=no'], home['home'])
    assert rc == 0 and 'flag1=False' in out, out + err

    # A word that is not of the type stops the command with the message, before the command runs
    rc, out, err = cx(['c5cat', 'typed', '--flag=auto'], home['home'])
    assert rc != 0 and "Invalid bool value 'auto' for 'flag' of \"c5cat typed\"" in err, out + err

    rc, out, err = cx(['c5cat', 'typed', '--name=c'], home['home'])
    assert rc != 0 and "must be one of a, b" in err, out + err

    # The switches: the category's and the environment's
    rc, out, err = cx(['c5off', 'typed', '--flag=no', '--json'], home['home'])
    assert rc == 0 and got(out)['flag'] == 'no', out + err

    rc, out, err = cx(['c5cat', 'typed', '--flag=no', '--count=7', '--json'], home['home'], CMETA_CLI_TYPES='off')
    assert rc == 0 and got(out) == {'flag': 'no', 'other': None, 'count': '7', 'name': None, 'free': None}, out + err
