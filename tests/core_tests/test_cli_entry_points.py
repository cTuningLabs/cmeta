"""
The command-line entry points of pyproject.toml: each one names a function that exists in cmeta/cli.py, and the
shortcuts put their words in front of the user's arguments (`cxt` = `cx task run`, `cxa` = `cx task run run-ai`,
their `u` twins with a bare `--home` first). Before 0.37.5.2 `cli.py` defined `main_cserver` twice and
`main_ucserver`, the entry point of `ucserver`, did not exist.

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import importlib
import os
import re
import sys

import pytest

# The module itself: the package's `cmeta.cli` attribute is the function `process`
cli = importlib.import_module('cmeta.cli')

PYPROJECT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'pyproject.toml')


def scripts_of_pyproject():
    # The [project.scripts] table read line by line (tomllib is not in Python 3.9)
    scripts = {}
    inside = False

    with open(PYPROJECT, encoding='utf-8') as f:
        for line in f:
            line = line.strip()

            if line.startswith('['):
                inside = line == '[project.scripts]'
                continue

            m = re.match(r'^([A-Za-z0-9_.-]+)\s*=\s*"([^"]+)"$', line) if inside else None
            if m:
                scripts[m.group(1)] = m.group(2)

    return scripts


def test_every_entry_point_names_a_function_of_cli():
    scripts = scripts_of_pyproject()

    assert {'cx', 'cxt', 'cxa', 'cserver', 'ucx', 'ucxt', 'ucxa', 'ucserver'} <= set(scripts)

    for name, target in scripts.items():
        module, _, function = target.partition(':')
        assert module == 'cmeta.cli', name
        assert callable(getattr(cli, function, None)), f'{name} = "{target}": no such function in cmeta/cli.py'


def test_each_shortcut_has_its_own_function():
    scripts = scripts_of_pyproject()
    functions = [target for target in scripts.values()]

    assert len(functions) == len(set(functions))
    assert cli.main_cserver is not cli.main_ucserver


# The words each entry point puts in front of the user's arguments
SHORTCUTS = [
    ('main_cx', []),
    ('main_cxt', ['task', 'run']),
    ('main_cxa', ['task', 'run', 'run-ai']),
    ('main_cserver', ['app', 'run', 'cserver']),
    ('main_ucx', ['--home']),
    ('main_ucxt', ['--home', 'task', 'run']),
    ('main_ucxa', ['--home', 'task', 'run', 'run-ai']),
    ('main_ucserver', ['--home', 'app', 'run', 'cserver']),
]


@pytest.mark.parametrize('function, words', SHORTCUTS)
def test_a_shortcut_puts_its_words_before_the_arguments(monkeypatch, function, words):
    calls = []

    def fake_main(args=None):
        calls.append(args)
        return 0

    user_args = ['--project=.', '--new', '-q', '--', '--harness-flag']

    monkeypatch.setattr(cli, 'main', fake_main)
    monkeypatch.setattr(cli, 'caller', None)
    monkeypatch.setattr(sys, 'argv', ['shortcut'] + user_args)

    assert getattr(cli, function)() == 0
    assert cli.caller == 'cx'

    # `cx` itself lets main read sys.argv
    expected = None if function == 'main_cx' else words + user_args
    assert calls == [expected]
