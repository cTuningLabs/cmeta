"""
Tests of the questions cMeta asks when nobody can answer them (a detached job, nohup, a CI step: the standard
input is closed or at its end). input() raises EOFError there, and a command used to end in a traceback; the
questions go through utils.common.ask now: no terminal is an error of the command that names the flag which
makes the question unnecessary (-f for a deletion, -q for a selection), never a made-up answer. A terminal and
a piped answer are as before.

Each test runs against a fresh <CMETA_HOME> in tmp_path so it does not touch the user's real cMeta state.

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import io
import os
import subprocess
import sys

import pytest

from cmeta import CMeta
from cmeta import repos as cmeta_repos
from cmeta.utils import common, files

CATEGORY = 'cache'


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX',
                'CMETA_DEBUG', 'CMETA_VERBOSE', 'CMETA_FAIL_ON_ERROR', 'CMETA_INDEX_LOCK_TIMEOUT', 'CMETA_LOCK_TIMEOUT'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    monkeypatch.setattr(cmeta_repos, '_migrated_notices', set())
    return CMeta(home=str(tmp_path))


def no_terminal(monkeypatch, error=EOFError):
    """The standard input of a detached job: input() prints the prompt and raises."""
    def closed(prompt=''):
        print(prompt, end='')
        raise error() if error is EOFError else error
    monkeypatch.setattr('builtins.input', closed)


def answers(monkeypatch, *lines):
    it = iter(lines)
    monkeypatch.setattr('builtins.input', lambda prompt='': next(it))


def make(cm, alias):
    r = cm.access({'category': CATEGORY, 'command': 'create', 'arg1': f'local:{alias}', 'tags': ['noterm'],
                   'meta': {'params': {'name': alias}}, 'con': False})
    assert r['return'] == 0, r.get('error')
    return r['path']


def found(cm):
    r = cm.access({'category': CATEGORY, 'command': 'find', 'tags': 'noterm', 'con': False})
    assert r['return'] in (0, 16), r.get('error')
    return r.get('artifacts', []) if r['return'] == 0 else []


###################################################################################################
# utils.common.ask

def test_an_answer_is_returned_as_typed(monkeypatch):
    answers(monkeypatch, ' Yes ')
    assert common.ask('Proceed (y/N)? ') == {'return': 0, 'answer': ' Yes '}


def test_no_terminal_is_an_error_that_names_the_flag(monkeypatch, capsys):
    no_terminal(monkeypatch)
    r = common.ask('  Proceed (y/N)? ', how='-f (--force) to delete without asking')
    assert r['return'] == 1 and r['no_terminal'] is True
    assert 'no answer to "Proceed (y/N)?"' in r['error']
    assert 'no terminal' in r['error'] and '-f (--force) to delete without asking' in r['error']
    assert capsys.readouterr().out.endswith('\n')          # the open prompt line is closed


def test_the_default_flag_is_quiet(monkeypatch):
    no_terminal(monkeypatch)
    assert '-q (--quiet)' in common.ask('Select: ')['error']


def test_an_optional_question_has_the_empty_answer(monkeypatch):
    no_terminal(monkeypatch)
    assert common.ask('Enter name: ', optional=True) == {'return': 0, 'answer': '', 'no_terminal': True}


def test_python_without_a_standard_input(monkeypatch):
    no_terminal(monkeypatch, RuntimeError('input(): lost sys.stdin'))
    assert common.ask('Proceed (y/N)? ')['return'] == 1


@pytest.mark.parametrize('error', [OSError(9, 'Bad file descriptor'), OSError(5, 'Input/output error'),
                                   ValueError('I/O operation on closed file.')])
def test_a_standard_input_that_cannot_be_read(monkeypatch, error):
    """An invalid or closed handle (a job without a console on Windows), a terminal that hung up."""
    no_terminal(monkeypatch, error)
    r = common.ask('Proceed (y/N)? ')
    assert r['return'] == 1 and r['no_terminal'] is True


def test_other_errors_are_not_swallowed(monkeypatch):
    no_terminal(monkeypatch, RuntimeError('something else'))
    with pytest.raises(RuntimeError, match='something else'):
        common.ask('Proceed (y/N)? ')
    no_terminal(monkeypatch, ValueError('something else'))
    with pytest.raises(ValueError, match='something else'):
        common.ask('Proceed (y/N)? ')
    no_terminal(monkeypatch, KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        common.ask('Proceed (y/N)? ')


def test_a_real_closed_standard_input(monkeypatch):
    """Not a stand-in: a standard input at its end, as `< /dev/null` gives; then a piped answer."""
    monkeypatch.setattr(sys, 'stdin', io.StringIO(''))
    r = common.ask('Proceed (y/N)? ')
    assert r['return'] == 1 and r['no_terminal'] is True
    monkeypatch.setattr(sys, 'stdin', io.StringIO('y\n'))
    assert common.ask('Proceed (y/N)? ') == {'return': 0, 'answer': 'y'}


###################################################################################################
# The deletion of an artifact

def test_ask_to_delete(monkeypatch, tmp_path):
    answers(monkeypatch, 'y', 'n', '')
    assert files.ask_to_delete(True, False, str(tmp_path))['confirmed'] is True
    assert files.ask_to_delete(True, False, str(tmp_path))['confirmed'] is False
    assert files.ask_to_delete(True, False, str(tmp_path))['confirmed'] is False      # Enter: the default is no

    no_terminal(monkeypatch)
    r = files.ask_to_delete(True, False, str(tmp_path))
    assert r['return'] == 1 and '-f (--force)' in r['error'] and 'confirmed' not in r
    assert files.ask_to_delete(True, True, str(tmp_path)) == {'return': 0, 'confirmed': True}     # forced: no question
    assert files.ask_to_delete(False, False, str(tmp_path)) == {'return': 0, 'confirmed': True}    # no console: as before


def test_delete_without_a_terminal_deletes_nothing(cm, monkeypatch, capsys):
    folder = make(cm, 'entry-a')
    no_terminal(monkeypatch)
    r = cm.access({'category': CATEGORY, 'command': 'delete', 'arg1': 'entry-a', 'con': True})
    out = capsys.readouterr().out
    assert r['return'] > 0 and 'no terminal' in r['error'] and '-f (--force)' in r['error']
    assert 'Traceback' not in out
    assert os.path.isdir(folder) and len(found(cm)) == 1

    r = cm.access({'category': CATEGORY, 'command': 'delete', 'arg1': 'entry-a', 'con': True, 'force': True})
    assert r['return'] == 0, r.get('error')
    assert not os.path.isdir(folder) and found(cm) == []


###################################################################################################
# A selection among several artifacts

def select(cm, artifacts, **params):
    p = {'category': 'utils', 'command': 'select_artifact', 'select_category': CATEGORY, 'artifacts': artifacts,
         'con': True, 'quiet': False}
    p.update(params)
    return cm.access(p)


def test_selection_without_a_terminal(cm, monkeypatch, capsys):
    make(cm, 'entry-a')
    make(cm, 'entry-b')
    artifacts = found(cm)
    assert len(artifacts) == 2

    no_terminal(monkeypatch)
    r = select(cm, artifacts)
    out = capsys.readouterr().out
    assert r['return'] > 0 and 'no terminal' in r['error'] and '-q (--quiet) to take the first of the list' in r['error']
    assert 'Make your selection' in out and 'Traceback' not in out

    r = select(cm, artifacts, quiet=True)                   # the answer given in advance
    assert r['return'] == 0, r.get('error')
    first = r['artifact']['cmeta_ref_parts']['artifact_uid']

    answers(monkeypatch, '1')                               # a terminal (or a pipe) that chooses
    r = select(cm, artifacts)
    assert r['return'] == 0 and r['artifact']['cmeta_ref_parts']['artifact_uid'] != first

    answers(monkeypatch, '')                                # Enter: the first
    r = select(cm, artifacts)
    assert r['return'] == 0 and r['artifact']['cmeta_ref_parts']['artifact_uid'] == first


###################################################################################################
# The command line, with a standard input that is really closed

def cx(home, *args, stdin=subprocess.DEVNULL, text=None):
    env = dict(os.environ)
    for var in ('CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE', 'CMETA_FAIL_ON_ERROR'):
        env.pop(var, None)
    env['CMETA_HOME'] = str(home)
    env['PYTHONIOENCODING'] = 'utf-8'
    kw = {'input': text} if text is not None else {'stdin': stdin}
    return subprocess.run([sys.executable, '-m', 'cmeta'] + list(args), env=env, capture_output=True, text=True, **kw)


def test_cli_delete_with_a_closed_standard_input(cm, tmp_path):
    folder = make(cm, 'entry-cli')

    r = cx(tmp_path, CATEGORY, 'delete', 'entry-cli')
    output = r.stdout + r.stderr
    assert r.returncode != 0, output
    assert 'no terminal' in output and '-f (--force)' in output and 'Traceback' not in output
    assert os.path.isdir(folder)

    r = cx(tmp_path, CATEGORY, 'delete', 'entry-cli', text='n\n')        # a piped no: nothing deleted, no error
    assert r.returncode == 0, r.stdout + r.stderr
    assert os.path.isdir(folder)

    r = cx(tmp_path, CATEGORY, 'delete', 'entry-cli', text='y\n')        # a piped yes
    assert r.returncode == 0, r.stdout + r.stderr
    assert not os.path.isdir(folder)
