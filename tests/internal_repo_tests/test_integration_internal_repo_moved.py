"""
Integration tests of a home indexed by one installation of the engine and then used by another one (its internal
repository at another path: a tool reinstalled onto another Python, a virtual environment made again, a second
install that uses the same home). The index kept the records of the first installation's internal repository until a
full reindex: once that installation was gone, "cx app find cserver" answered a folder that was not there; an
incremental index (a plug, a pull, the reindex of one repository) wrote this engine's internal repository into
repos.json and its categories into the index, but kept the other one's apps (2026-10-17). Now an incremental index
moves the records too, and a gone internal repository is replaced at the next start. With both installations there,
the start changes nothing (as before).

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import json
import os
import shutil
import subprocess
import sys

import pytest

from cmeta import CMeta


def access(cm, **params):
    params.setdefault('con', False)
    return cm.access(params)


def cserver_path(home):
    r = access(CMeta(home=home), category='app', command='find', arg1='cserver')
    assert r['return'] == 0, r.get('error')
    return os.path.normcase(os.path.normpath(r['artifacts'][0]['path']))


def under(path, folder):
    return path.startswith(os.path.normcase(os.path.normpath(str(folder))) + os.sep)


def registered(home):
    with open(os.path.join(home, 'repos.json'), encoding='utf-8') as f:
        return [os.path.normcase(os.path.normpath(p)) for p in json.load(f)]


@pytest.fixture()
def engines(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE',
                'CMETA_INTERNAL_REPO_PATH'):
        monkeypatch.delenv(var, raising=False)
    home = str(tmp_path / 'home')
    monkeypatch.setenv('CMETA_HOME', home)

    import cmeta
    source = os.path.join(os.path.dirname(os.path.abspath(cmeta.__file__)), 'internal-repo')
    a = tmp_path / 'engine-a' / 'internal-repo'
    b = tmp_path / 'engine-b' / 'internal-repo'
    for folder in (a, b):
        shutil.copytree(source, folder, ignore=shutil.ignore_patterns('__pycache__'))

    # the home is indexed by installation A
    monkeypatch.setenv('CMETA_INTERNAL_REPO_PATH', str(a))
    assert under(cserver_path(home), a)
    return home, a, b, monkeypatch


def test_a_gone_internal_repository_is_replaced_at_the_next_start(engines):
    home, a, b, monkeypatch = engines

    shutil.rmtree(a.parent)
    monkeypatch.setenv('CMETA_INTERNAL_REPO_PATH', str(b))

    path = cserver_path(home)
    assert under(path, b) and os.path.isdir(path)                  # before: a folder of A that was not there
    assert os.path.normcase(os.path.normpath(str(b))) in registered(home)
    assert os.path.normcase(os.path.normpath(str(a))) not in registered(home)


def test_an_incremental_index_moves_the_records_to_this_engine(engines):
    home, a, b, monkeypatch = engines
    monkeypatch.setenv('CMETA_INTERNAL_REPO_PATH', str(b))

    # both installations there: the start changes nothing
    assert under(cserver_path(home), a)

    # an incremental index by B: repos.json, the categories and the apps name B's internal repository
    r = access(CMeta(home=home), category='repo', command='reindex', arg1='local')
    assert r['return'] == 0, r.get('error')
    assert under(cserver_path(home), b)                            # before: still A's
    r = access(CMeta(home=home), category='category', command='find', arg1='repo')
    assert r['return'] == 0 and under(os.path.normcase(r['artifacts'][0]['path']), b)
    assert os.path.normcase(os.path.normpath(str(b))) in registered(home)


def upgraded_in_place(internal_repo):
    """The release after, in the same folder (pip or uv upgraded the engine in place): another version, a new app."""
    meta = internal_repo / '_cmr.yaml'
    meta.write_text(meta.read_text(encoding='utf-8').replace("version: '", "version: '9", 1), encoding='utf-8')
    (internal_repo / 'app' / 'cserver-next').mkdir()
    (internal_repo / 'app' / 'cserver-next' / '_cmeta.yaml').write_text(
        'artifact: 0123456789abcdef\ncategory: app,554a9a2199104713\n', encoding='utf-8')


def cx(*words, timeout=300):
    """The command line of the engine in this process's environment (the home and the internal repository of the
    fixture), as a user runs it: its exit code and its output."""
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    p = subprocess.run([sys.executable, '-m', 'cmeta'] + list(words), capture_output=True, stdin=subprocess.DEVNULL,
                       env=env, timeout=timeout)
    return p.returncode, p.stdout.decode('utf-8', 'replace'), p.stderr.decode('utf-8', 'replace')


def test_an_engine_upgraded_in_place_indexes_its_repository_again(engines):
    home, a, b, monkeypatch = engines
    upgraded_in_place(a)

    r = access(CMeta(home=home), category='app', command='find', arg1='cserver-next')
    assert r['return'] == 0, r.get('error')                       # before: not found until "cx repo reindex internal"
    assert under(os.path.normcase(r['artifacts'][0]['path']), a)

    # once: the next start reads nothing again
    app_index = os.path.join(home, 'index', 'app.pkl')
    before = os.stat(app_index).st_mtime_ns
    assert under(cserver_path(home), a)
    assert os.stat(app_index).st_mtime_ns == before


def test_the_first_command_after_an_upgrade_in_place_keeps_its_output_usable(engines):
    """The one command that indexes again says so with an info line on stdout, as the first run of a new home does -
    and everything a script reads stays where it was: the exit code, the answer, the JSON of -j, nothing on stderr."""
    home, a, b, monkeypatch = engines
    upgraded_in_place(a)

    code, out, err = cx('app', 'find', 'cserver-next', '-j')
    assert code == 0, out + err
    assert 'cMeta info:' in out and 'indexing it again' in out
    assert 'cMeta notice' not in err
    j = json.loads(out.split('-' * 60, 1)[1])                   # the JSON of -j follows its line of dashes, as always
    assert j['return'] == 0 and under(os.path.normcase(j['artifacts'][0]['path']), a)

    # --version too: the start-up heals the home before the version is printed, once
    code, out, err = cx('--version')
    assert code == 0 and 'cMeta version' in out and 'indexing it again' not in out


def test_many_commands_starting_at_once_after_an_upgrade_in_place(engines):
    """Several processes meet the stale index at the same moment (a script, a server's workers): each one answers,
    none breaks the index - the index lock lets them in one after the other - and afterwards the home is at rest."""
    home, a, b, monkeypatch = engines
    upgraded_in_place(a)
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    cmd = [sys.executable, '-m', 'cmeta', 'app', 'find', 'cserver-next']

    procs = [subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env)
             for _ in range(6)]
    outs = [p.communicate(timeout=600)[0].decode('utf-8', 'replace') for p in procs]
    assert all(p.returncode == 0 for p in procs), outs
    assert all('cserver-next' in o for o in outs), outs

    code, out, err = cx('app', 'find', 'cserver-next', '-j')
    assert code == 0 and 'indexing it again' not in out, out + err
    j = json.loads(out.split('-' * 60, 1)[1])
    assert len(j['artifacts']) == 1 and under(os.path.normcase(j['artifacts'][0]['path']), a)


def test_the_same_engine_does_not_index_again_at_start(engines):
    home, a, b, monkeypatch = engines
    app_index = os.path.join(home, 'index', 'app.pkl')
    before = os.stat(app_index).st_mtime_ns

    # the same internal repository, named another way (a trailing separator; on Windows another case)
    monkeypatch.setenv('CMETA_INTERNAL_REPO_PATH', str(a) + os.sep)
    assert under(cserver_path(home), a)
    assert os.stat(app_index).st_mtime_ns == before
