"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

Tests for the way `cx app run` calls an app's run script (run_ of the app category).

The script is called by an explicit path: `call .\\_run.bat` / `. ./_run.sh` from the app's folder, the absolute
path when the app sets skip_chdir. A bare `_run.bat` failed with "is not recognized" when cmd.exe does not look in
the current folder (NoDefaultCurrentDirectoryInExePath, set in hardened setups and agent shells, 2026-10-31), and
skip_chdir on Linux and macOS made ".//<absolute path>" of the absolute path, relative to the current folder.
"""

import os

import pytest

from cmeta import CMeta


@pytest.fixture()
def app(tmp_path, monkeypatch):
    """A fresh home with the app local:probe-app; its run script writes PROBE_WORD into PROBE_OUT."""
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('CMETA_VERBOSE', 'false')

    cm = CMeta(home=str(tmp_path / 'home'))
    assert cm.access({'category': 'app', 'command': 'add', 'arg1': 'local:probe-app', 'con': False})['return'] == 0
    r = cm.access({'category': 'app', 'command': 'find', 'arg1': 'local:probe-app', 'con': False})
    path = r['artifacts'][0]['path']

    with open(os.path.join(path, '_run.bat'), 'w', encoding='utf-8') as f:
        f.write('@echo off\r\necho %PROBE_WORD%>"%PROBE_OUT%"\r\n')
    with open(os.path.join(path, '_run.sh'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('echo "$PROBE_WORD" > "$PROBE_OUT"\n')

    return cm, path


def _run(cm, out, **options):
    r = cm.access(dict(category='app', command='run', arg1='local:probe-app', con=False,
                       param={'word': 'hello', 'out': str(out)}, **options))
    assert r['return'] == 0, r
    assert r['return_code'] == 0
    with open(out, encoding='utf-8') as f:
        return f.read().strip()


def _set_meta(cm, meta):
    r = cm.access({'category': 'app', 'command': 'update', 'arg1': 'local:probe-app', 'meta': meta, 'con': False})
    assert r['return'] == 0, r


def test_run_script_found_in_the_app_folder(app, tmp_path, monkeypatch):
    cm, path = app
    _set_meta(cm, {'param_env_prefix': 'PROBE_'})

    # cmd.exe without the current folder in its search; ignored by sh
    monkeypatch.setenv('NoDefaultCurrentDirectoryInExePath', '1')

    cwd = os.getcwd()
    assert _run(cm, tmp_path / 'out1.txt') == 'hello'
    assert os.getcwd() == cwd


def test_run_script_by_absolute_path_with_skip_chdir(app, tmp_path, monkeypatch):
    cm, path = app
    _set_meta(cm, {'param_env_prefix': 'PROBE_', 'skip_chdir': True})

    # Somewhere else, where no _run script is
    monkeypatch.setenv('NoDefaultCurrentDirectoryInExePath', '1')
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert _run(cm, tmp_path / 'out2.txt') == 'hello'
    assert os.getcwd() == str(elsewhere)
