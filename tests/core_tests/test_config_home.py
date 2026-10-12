"""
Tests of how the cMeta home is chosen (`config.home_from_env`) and of what says so: `config.home_choice`, the
line of the first run on a new home, and the "cMeta home chosen by" line of `cx --version`.

The order is the one cMeta always had - CMETA_HOME, <VIRTUAL_ENV>/CMETA, <CONDA_PREFIX>/CMETA, CMETA_HOME2,
~/CMETA - and nothing of it changes: only the words about it are new. They are for whoever expects the home
somewhere else: inside a virtual or conda environment it is `<environment>/CMETA`, not `~/CMETA`.

Every home is under tmp_path, the user's own folder included, so nothing of the user's cMeta state is touched.

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import pathlib
import subprocess
import sys

import pytest

from cmeta import CMeta
from cmeta import config

HOME_VARS = ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX')

# Not an error: a line of information on the standard output (the standard error is for errors only)
NOTICE = 'cMeta info: a new cMeta home is set up in '


@pytest.fixture()
def user(tmp_path, monkeypatch):
    """No variable chooses a home, and the user's folder (where the default home is) is a folder of the test."""
    for var in HOME_VARS + ('CMETA_DEBUG', 'CMETA_VERBOSE', 'CMETA_LOG', 'CMETA_LOG_FILE'):
        monkeypatch.delenv(var, raising=False)

    folder = tmp_path / 'user'
    folder.mkdir()

    monkeypatch.setenv('HOME', str(folder))
    monkeypatch.setenv('USERPROFILE', str(folder))

    return folder


def notices(text):
    return [line for line in text.splitlines() if line.startswith('cMeta info:')]


# What is set -> the variable that chooses the home, and the home below tmp_path ('~' is the user's folder)
ORDER = [
    ({}, '', '~/CMETA'),
    ({'CMETA_HOME': 'explicit'}, 'CMETA_HOME', 'explicit'),
    ({'VIRTUAL_ENV': 'venv'}, 'VIRTUAL_ENV', 'venv/CMETA'),
    ({'CONDA_PREFIX': 'conda'}, 'CONDA_PREFIX', 'conda/CMETA'),
    ({'CMETA_HOME2': 'second'}, 'CMETA_HOME2', 'second'),
    ({'VIRTUAL_ENV': 'venv', 'CONDA_PREFIX': 'conda'}, 'VIRTUAL_ENV', 'venv/CMETA'),
    ({'VIRTUAL_ENV': 'venv', 'CMETA_HOME2': 'second'}, 'VIRTUAL_ENV', 'venv/CMETA'),
    ({'CONDA_PREFIX': 'conda', 'CMETA_HOME2': 'second'}, 'CONDA_PREFIX', 'conda/CMETA'),
    ({'CMETA_HOME': 'explicit', 'VIRTUAL_ENV': 'venv', 'CONDA_PREFIX': 'conda', 'CMETA_HOME2': 'second'}, 'CMETA_HOME', 'explicit'),
]


def place(tmp_path, user, name):
    """The folder a row of ORDER names."""
    if name.startswith('~/'):
        return str(user / name[2:])

    return os.path.join(str(tmp_path), *name.split('/'))


@pytest.mark.parametrize('settings, variable, home', ORDER)
def test_the_order_in_which_the_home_is_chosen(tmp_path, user, monkeypatch, settings, variable, home):
    for name, folder in settings.items():
        monkeypatch.setenv(name, place(tmp_path, user, folder))

    expected = place(tmp_path, user, home)

    assert config.home_from_env() == (expected, variable)
    assert config.check_init_vars_from_env()['init']['home'] == expected
    assert str(CMeta().home_path) == expected

    choice = config.home_choice(expected)
    assert choice['source'] == (variable or 'default'), choice
    assert choice['value'] == (place(tmp_path, user, settings[variable]) if variable else '')


def test_a_blank_variable_chooses_nothing(tmp_path, user, monkeypatch):
    monkeypatch.setenv('CMETA_HOME', '   ')
    monkeypatch.setenv('CMETA_HOME2', '  ' + str(tmp_path / 'second') + ' ')

    assert config.home_from_env() == (str(tmp_path / 'second'), 'CMETA_HOME2')

    monkeypatch.setenv('CMETA_HOME2', ' ')

    assert config.home_from_env() == (str(user / 'CMETA'), '')


def test_what_chose_the_home_in_words(tmp_path, user, monkeypatch):
    assert config.home_choice(user / 'CMETA')['text'] == 'the default'

    # A home given to the instance and not by the environment
    given = config.home_choice(tmp_path / 'elsewhere')
    assert given['source'] == 'given' and given['text'].startswith('this run')

    venv = str(tmp_path / 'venv')
    monkeypatch.setenv('VIRTUAL_ENV', venv)
    assert config.home_choice(os.path.join(venv, 'CMETA'))['text'] == f'VIRTUAL_ENV={venv} - a virtual environment keeps a home of its own'

    # The default folder is still named the default when the environment would choose another one
    assert config.home_choice(user / 'CMETA')['source'] == 'default'

    monkeypatch.delenv('VIRTUAL_ENV')
    conda = str(tmp_path / 'conda')
    monkeypatch.setenv('CONDA_PREFIX', conda)
    assert config.home_choice(os.path.join(conda, 'CMETA'))['text'] == f'CONDA_PREFIX={conda} - a conda environment keeps a home of its own'

    monkeypatch.setenv('CMETA_HOME', str(tmp_path / 'explicit'))
    assert config.home_choice(tmp_path / 'explicit')['text'] == 'CMETA_HOME'


def test_the_first_run_on_a_new_home_says_where_it_is_and_what_chose_it(tmp_path, user, monkeypatch, capsys):
    venv = str(tmp_path / 'venv')
    home = os.path.join(venv, 'CMETA')
    monkeypatch.setenv('VIRTUAL_ENV', venv)

    cm = CMeta()
    assert not os.path.exists(os.path.join(home, 'repos.json'))

    capsys.readouterr()
    r = cm.access({'category': 'repo', 'command': 'find', 'con': True})
    assert r['return'] == 0, r.get('error')

    captured = capsys.readouterr()
    assert notices(captured.out) == [f'{NOTICE}{home} (chosen by VIRTUAL_ENV={venv} - a virtual environment keeps a home of its own); '
                                     f'set CMETA_HOME to keep the home elsewhere, "cx --version" shows the home in use'], captured.out
    assert captured.err == '', captured.err
    assert os.path.isfile(os.path.join(home, 'repos.json'))

    # Once: not at the next call, not in another instance on the same home
    r = cm.access({'category': 'repo', 'command': 'find', 'con': True})
    assert r['return'] == 0 and notices(capsys.readouterr().out) == []

    r = CMeta().access({'category': 'repo', 'command': 'find', 'con': True})
    assert r['return'] == 0 and notices(capsys.readouterr().out) == []


def test_the_line_for_the_default_home_and_for_an_explicit_one(tmp_path, user, monkeypatch, capsys):
    # The default
    r = CMeta().access({'category': 'repo', 'command': 'find', 'con': True})
    assert r['return'] == 0, r.get('error')

    assert notices(capsys.readouterr().out) == [f'{NOTICE}{user / "CMETA"} (the default); '
                                                f'set CMETA_HOME to keep the home elsewhere, "cx --version" shows the home in use']

    # CMETA_HOME: nothing to advise
    explicit = str(tmp_path / 'explicit')
    monkeypatch.setenv('CMETA_HOME', explicit)

    r = CMeta().access({'category': 'repo', 'command': 'find', 'con': True})
    assert r['return'] == 0, r.get('error')

    assert notices(capsys.readouterr().out) == [f'{NOTICE}{explicit} (chosen by CMETA_HOME); "cx --version" shows the home in use']

    # A home given to the instance
    given = str(tmp_path / 'given')

    r = CMeta(home=given).access({'category': 'repo', 'command': 'find', 'con': True})
    assert r['return'] == 0, r.get('error')

    assert notices(capsys.readouterr().out) == [f'{NOTICE}{given} (chosen by this run: --home or the home argument of CMeta); '
                                                f'set CMETA_HOME to keep the home elsewhere, "cx --version" shows the home in use']


def test_without_the_console_a_new_home_is_set_up_without_a_word(tmp_path, user, monkeypatch, capsys):
    monkeypatch.setenv('VIRTUAL_ENV', str(tmp_path / 'venv'))

    r = CMeta().access({'category': 'repo', 'command': 'find', 'con': False})
    assert r['return'] == 0, r.get('error')

    captured = capsys.readouterr()
    assert captured.err == '' and captured.out == ''
    assert (tmp_path / 'venv' / 'CMETA' / 'repos.json').is_file()


def cx(args, user, **settings):
    """`python -m cmeta <args>` in another process whose environment chooses the home by `settings` only."""
    env = {k: v for k, v in os.environ.items() if not k.startswith('CMETA_') and k not in HOME_VARS}
    env.update({'HOME': str(user), 'USERPROFILE': str(user), 'PYTHONIOENCODING': 'utf-8'})
    env.update(settings)

    p = subprocess.run([sys.executable, '-m', 'cmeta'] + list(args), env=env, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)

    return p.returncode, p.stdout.decode('utf-8', 'replace'), p.stderr.decode('utf-8', 'replace')


def test_cx_version_names_what_chose_the_home_and_the_first_command_says_it_once(tmp_path, user):
    venv = str(tmp_path / 'venv')
    home = os.path.join(venv, 'CMETA')

    rc, out, err = cx(['--version'], user, VIRTUAL_ENV=venv)
    assert rc == 0, out + err

    lines = [line.rstrip() for line in out.splitlines()]
    at = lines.index(f'cMeta home path:           {home}')
    assert lines[at + 1] == f'cMeta home chosen by:      VIRTUAL_ENV={venv} - a virtual environment keeps a home of its own', lines
    assert lines[at + 2] == f'cMeta repositories path:   {os.path.join(home, "repos")}', lines

    # The line of the new home is a line of information on the standard output; nothing is on the standard error
    assert len(notices(out)) == 1 and notices(out)[0].startswith(NOTICE + home), out
    assert 'a new cMeta home' not in err, err

    # The second command on that home says nothing
    rc, out2, err2 = cx(['--version'], user, VIRTUAL_ENV=venv)
    assert rc == 0 and notices(out2) == [] and 'a new cMeta home' not in err2, out2 + err2

    # Without any variable: the default
    rc, out, err = cx(['--version'], user)
    assert rc == 0, out + err
    assert f'cMeta home path:           {user / "CMETA"}' in out and 'cMeta home chosen by:      the default' in out, out
