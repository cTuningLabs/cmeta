"""
The command line of cMeta pinned in tables: what `parse_cmd` makes of each kind of token, how the engine's own control
flags read a word given as their value, and what a command says when it gets text after "--" that it does not read.

The rules (point 4 of the hardening work, after cMeta 0.35.2):

- a bare `key=value` is a flag only when the part before the first "=" looks like a key (a letter or "_", then
  letters, digits, "_", ".", "," or "-"); any other token with "=" - a command, a URL with a query string, an
  expression - is one positional argument, kept as it is;
- a negative number (-5, -1.5) is a positional argument, not a flag;
- a control flag (--quiet, --verbose, --json, ...) given a word takes yes/no, true/false, on/off, 1/0 - before,
  such a word crashed the conversion or took the value of the flag converted before it;
- text after "--" goes to the command as `unparsed`; a keyword-style command without such a parameter (and without
  **kwargs) says '"<category> <command>" takes no arguments after "--"' instead of Python's TypeError.

Everything else is as it always was, and the table says so: every form that worked keeps its result.

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import random
import re
import subprocess
import sys

import pytest

from cmeta import CMeta
from cmeta import config
from cmeta.utils import cli
from cmeta.utils.cli import parse_cmd, check_params


# (tokens, the params parse_cmd makes of them)
TABLE = [
    # Free text with "=" stays one positional argument
    (['host', 'run', 'h', 'echo a=b'], {'args': ['host', 'run', 'h', 'echo a=b']}),
    (['download', 'https://x/file?id=42'], {'args': ['download', 'https://x/file?id=42']}),
    (['task', 'run', 'cmd', 'python -c "print(1==1)"'], {'args': ['task', 'run', 'cmd', 'python -c "print(1==1)"']}),
    (['x', 'a b=c'], {'args': ['x', 'a b=c']}),
    (['x', '=v'], {'args': ['x', '=v']}),
    (['x', '1x=2'], {'args': ['x', '1x=2']}),
    (['x', 'x@y=1'], {'args': ['x', 'x@y=1']}),
    (['x', 'C:\\a=b'], {'args': ['x', 'C:\\a=b']}),
    (['x', '/p/a=b'], {'args': ['x', '/p/a=b']}),

    # Negative numbers are positional; a value may still be negative
    (['task', 'run', 'x', '-5', '-1.5'], {'args': ['task', 'run', 'x', '-5', '-1.5']}),
    (['x', '--delta=-5'], {'args': ['x'], 'delta': '-5'}),
    (['x', '-5x'], {'args': ['x'], '5x': True}),

    # Bare key=value as before, the value may hold anything
    (['x', 'name=v'], {'args': ['x'], 'name': 'v'}),
    (['x', 'name=John Smith'], {'args': ['x'], 'name': 'John Smith'}),
    (['x', 'path=C:\\x\\y'], {'args': ['x'], 'path': 'C:\\x\\y'}),
    (['x', 'url=https://a/b?c=d'], {'args': ['x'], 'url': 'https://a/b?c=d'}),
    (['x', 'a.b=v'], {'args': ['x'], 'a': {'b': 'v'}}),
    (['x', 'tags,=a,b'], {'args': ['x'], 'tags': ['a', 'b']}),
    (['x', 'log-level=debug'], {'args': ['x'], 'log_level': 'debug'}),
    (['x', '_private=1'], {'args': ['x'], '_private': '1'}),
    (['x', 'na\u00efve=1'], {'args': ['x'], 'na\u00efve': '1'}),

    # Dash flags as before
    (['x', '--quiet=yes'], {'args': ['x'], 'quiet': 'yes'}),
    (['x', '--x'], {'args': ['x'], 'x': True}),
    (['x', '--y-'], {'args': ['x'], 'y': False}),
    (['x', '--no-z'], {'args': ['x'], 'z': False}),
    (['x', '-q'], {'args': ['x'], 'q': True}),
    (['x', '--cmd=echo a=b'], {'args': ['x'], 'cmd': 'echo a=b'}),
    (['x', '--tags,=a,b'], {'args': ['x'], 'tags': ['a', 'b']}),
    (['x', '--tags,='], {'args': ['x'], 'tags': []}),
    (['x', '--a.b-c=1'], {'args': ['x'], 'a': {'b-c': '1'}}),
    (['x', '--log-level=debug'], {'args': ['x'], 'log_level': 'debug'}),
    (['x', '--k=v1', '--k=v2'], {'args': ['x'], 'k': 'v2'}),

    # "--key value" is not a form: a flag and a positional argument
    (['x', '--name', 'foo'], {'args': ['x', 'foo'], 'name': True}),

    # "--" ends the parsing
    (['x', '--', 'echo', 'a=b', '-5', '--y'], {'args': ['x'], 'unparsed': ['echo', 'a=b', '-5', '--y']}),
    (['x', '--'], {'args': ['x'], 'unparsed': []}),

    # Plain positional arguments
    (['repo', 'list'], {'args': ['repo', 'list']}),
    ([], {}),
]


@pytest.mark.parametrize('tokens, params', TABLE, ids=[' '.join(t) or '(none)' for t, _ in TABLE])
def test_what_the_parser_makes_of_each_token(tokens, params):
    r = parse_cmd(tokens)
    assert r['return'] == 0, r.get('error')
    assert r['params'] == params


def test_a_triple_dash_is_still_an_error():
    r = parse_cmd(['x', '---y'])
    assert r['return'] > 0 and '"---y"' in r['error']


# The parser as it was, against the parser as it is: exactly two kinds of token changed their meaning

def parse_as_before(tokens):
    """The rules before this change: every token with "=" was a flag, and every token that starts with "-"."""
    with pytest.MonkeyPatch.context() as m:
        m.setattr(cli, 'KEY_LIKE', re.compile(r'^.*$', re.S))
        m.setattr(cli, 'NEGATIVE_NUMBER', re.compile(r'(?!x)x'))
        return parse_cmd(tokens)


def changed_meaning(token):
    """True for a token the change is meant for: a negative number, or a dash-less token with "=" whose part
    before the "=" does not look like a key."""
    if cli.NEGATIVE_NUMBER.match(token):
        return True
    return '=' in token and not token.startswith('-') and not cli.KEY_LIKE.match(token.split('=', 1)[0])


PIECES = ['a', 'B', 'z', '_', '1', '0', '5', '.', ',', '-', '--', '=', ' ', '/', ':', '?', '\\', '"', "'", '+', '#',
          'no-', 'naïve', 'C:', 'http://x', '(', ')', '==', '!', '*']


def random_tokens(rng):
    tokens = []
    for _ in range(rng.randint(1, 4)):
        token = ''.join(rng.choice(PIECES) for _ in range(rng.randint(1, 6)))
        if token.startswith('@'):           # a file inclusion reads (or deletes) a file: not a parsing matter
            token = 'x' + token
        tokens.append(token)
    return tokens


def test_only_free_text_with_equals_and_negative_numbers_changed_their_meaning():
    rng = random.Random(20261013)
    changed, same = 0, 0

    for _ in range(20000):
        tokens = random_tokens(rng)
        before, now = parse_as_before(tokens), parse_cmd(tokens)

        # "--" ends the parsing: a changed token after it never mattered
        parsed = tokens[:tokens.index('--')] if '--' in tokens else tokens
        meant = [t for t in parsed if changed_meaning(t)]

        if not meant:
            assert before == now, (tokens, before, now)
            same += 1
        elif before['return'] == 0 and now['return'] == 0:
            # The changed tokens are positional arguments now, and nothing else changed
            assert before != now, (tokens, now)
            for t in meant:
                assert t in now['params'].get('args', []), (tokens, now)
            changed += 1
        # else: a parsing error in one of them (a "---" prefix, a key set as a value and then as a dict) - the
        # error is the same text in both or comes from the changed token itself; nothing to compare

    assert changed > 500 and same > 5000, (changed, same)     # both kinds of case were really exercised


# The control flags of the engine, the words they take

BOOL_CONTROL_FLAGS = [item for desc in (config.params_desc, config.params_command_desc, config.params_command2_desc,
                                         config.params_init_desc, config.params_command3_desc)
                      for item in desc if item and item.get('type') == bool]

WORDS = {'yes': True, 'Yes': True, 'true': True, 'on': True, '1': True, ' YES ': True,
         'no': False, 'false': False, 'OFF': False, '0': False}


@pytest.mark.parametrize('item', BOOL_CONTROL_FLAGS, ids=lambda i: i['key'])
def test_every_bool_control_flag_takes_a_word(item):
    desc = [item]

    for word, value in WORDS.items():
        r = check_params({item['key']: word}, desc)
        assert r['return'] == 0, (item['key'], word, r.get('error'))
        assert r['checked_params'][item['key']] is value, (item['key'], word)

    r = check_params({item['key']: 'maybe'}, desc)
    assert r['return'] > 0 and "Invalid bool value 'maybe'" in r['error']


def test_a_word_flag_after_another_flag_keeps_its_own_value():
    # Before: quiet took the value converted for verbose just before it
    r = check_params({'verbose': False, 'quiet': 'yes'}, config.params_desc)
    assert r['return'] == 0, r.get('error')
    assert r['checked_params']['verbose'] is False and r['checked_params']['quiet'] is True


# Text after "--": the commands that read it and the ones that do not

CATEGORY_UID = '0123456789abcdef'

API_V1 = '''from cmeta.category import InitCategory

class Category(InitCategory):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path = __file__, **kwargs)

    def plain_(self, ctx, arg1 = None):
        return {'return': 0, 'arg1': arg1}

    def words_(self, ctx, arg1 = None, unparsed = None):
        return {'return': 0, 'arg1': arg1, 'got': unparsed}

    def anything_(self, ctx, **kwargs):
        return {'return': 0, 'got': kwargs.get('unparsed')}

    def asdict__(self, params):
        return {'return': 0, 'got': params.get('unparsed')}
'''


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """A home of the test with a repository whose category has commands of each style."""
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)

    home = tmp_path / 'home'
    monkeypatch.setenv('CMETA_HOME', str(home))

    repo = tmp_path / 'repo-p4'
    category = repo / 'category' / 'p4cat'
    (category / 'api').mkdir(parents=True)
    (repo / '_cmr.yaml').write_text('artifact: repo-p4,1111111111111111\ncategory: repo,f4f792ab40c7498f\n', encoding='utf-8')
    (category / '_cmeta.yaml').write_text(f'artifact: p4cat,{CATEGORY_UID}\ncategory: category,dd9ea50e7f76467f\n'
                                          'last_api_version: 1\nbase_category_default_api_versions:\n  "1": 1\n',
                                          encoding='utf-8')
    (category / 'api' / 'v1.py').write_text(API_V1, encoding='utf-8')

    cm = CMeta(home=str(home))
    r = cm.access({'category': 'repo', 'command': 'plug', 'arg1': str(repo), 'con': False})
    assert r['return'] == 0, r.get('error')

    return {'cm': cm, 'home': home}


def test_text_after_dashes_reaches_the_commands_that_read_it(home):
    cm = home['cm']

    for command in ('words', 'anything', 'asdict'):
        r = cm.access({'category': 'p4cat', 'command': command, 'unparsed': ['echo', 'a=b'], 'con': False})
        assert r['return'] == 0, (command, r.get('error'))
        assert r['got'] == ['echo', 'a=b'], command


def test_a_command_that_does_not_read_it_says_so(home):
    r = home['cm'].access({'category': 'p4cat', 'command': 'plain', 'unparsed': ['x'], 'con': False})
    assert r['return'] > 0
    assert 'takes no arguments after "--"' in r['error'] and 'p4cat' in r['error'] and 'plain' in r['error'], r['error']

    # Without "--" the same command runs
    r = home['cm'].access({'category': 'p4cat', 'command': 'plain', 'arg1': 'x', 'con': False})
    assert r['return'] == 0 and r['arg1'] == 'x'


def cx(args, env_home):
    env = {k: v for k, v in os.environ.items() if not k.startswith('CMETA_')}
    env.update({'CMETA_HOME': str(env_home), 'PYTHONIOENCODING': 'utf-8'})
    p = subprocess.run([sys.executable, '-m', 'cmeta'] + list(args), env=env, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
    return p.returncode, p.stdout.decode('utf-8', 'replace'), p.stderr.decode('utf-8', 'replace')


def test_the_command_line_end_to_end(home):
    # A control flag given a word
    rc, out, err = cx(['repo', 'list', '--quiet=yes', '--json=no'], home['home'])
    assert rc == 0, out + err

    rc, out, err = cx(['repo', 'list', '--quiet=maybe'], home['home'])
    assert rc != 0 and "Invalid bool value 'maybe'" in err, out + err

    # Free text with "=" and a negative number reach the command as positional arguments
    rc, out, err = cx(['p4cat', 'plain', 'echo a=b'], home['home'])
    assert rc == 0, out + err

    rc, out, err = cx(['p4cat', 'plain', '-5'], home['home'])
    assert rc == 0, out + err

    # Text after "--": read by one command, refused in words by another
    rc, out, err = cx(['p4cat', 'words', '--', 'echo', 'a=b'], home['home'])
    assert rc == 0, out + err

    rc, out, err = cx(['p4cat', 'plain', '--', 'x'], home['home'])
    assert rc != 0 and 'takes no arguments after "--"' in err, out + err
