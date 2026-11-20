"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

An artifact in use is never moved, renamed or migrated (2026-11-20, the user: "if I am inside it on Windows, Linux or
MacOS - that happens often since I use either Far or MC to go to those artifacts and work with them, or they are used
by AI session - and I, by accident, try to move them to [an archive repository], then they are broken"). A real program holds the
artifact's folder here - its working directory in it, or a file of it open - and the command must stop before
anything changes: the folder with all its files where it was, nothing made in the target, the index as it was, no
migration stub. Linux and macOS name the program (/proc, lsof); Windows refuses the rename itself. A folder is
renamed on its file system and copied to another one, either completely or not at all.
"""

import itertools
import os
import subprocess
import sys
import time

import pytest

from cmeta import CMeta
from cmeta import repos as cmeta_repos
from cmeta.utils import files as cmeta_files

COUNTER = itertools.count()


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX',
                'CMETA_DEBUG', 'CMETA_VERBOSE', 'CMETA_FAIL_ON_ERROR'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path / 'home'))
    monkeypatch.setattr(cmeta_repos, '_migrated_notices', set())
    return CMeta(home=str(tmp_path / 'home'))


def access(cm, **params):
    params.setdefault('con', False)
    return cm.access(params)


def make(cm, alias, repo='local'):
    """An artifact with files of its own, as a user's work item has: -> its folder."""
    r = access(cm, category='log', command='create', arg1=f'{repo}:{alias}', yaml=True)
    assert r['return'] == 0, r.get('error')
    folder = r['path']
    with open(os.path.join(folder, 'notes.txt'), 'w', encoding='utf-8') as f:
        f.write('the user\'s own notes\n')
    os.makedirs(os.path.join(folder, 'sub'))
    with open(os.path.join(folder, 'sub', 'more.txt'), 'w', encoding='utf-8') as f:
        f.write('more\n')
    return folder


def other_repo(cm, tmp_path):
    repo = tmp_path / 'extra' / 'other'
    repo.mkdir(parents=True)
    (repo / '_cmr.yaml').write_text('artifact: other,7777777777777777\ncategory: repo,f4f792ab40c7498f\n', encoding='utf-8')
    r = access(cm, category='repo', command='plug', arg1=str(repo))
    assert r['return'] == 0, r.get('error')
    return repo


def listing(folder):
    out = []
    for root, dirs, files in os.walk(folder):
        for n in dirs + files:
            out.append(os.path.relpath(os.path.join(root, n), folder).replace(os.sep, '/'))
    return sorted(out)


def hold(tmp_path, folder, what):
    """A program that uses the folder - `cwd`: its working directory in it (a terminal, a Far or mc panel, an AI
    session); `file`: a file of it open - running until killed. -> the process (started and holding)."""
    ready = tmp_path / ('ready-%d' % next(COUNTER))
    if what == 'cwd':
        code = 'import sys, time; open(sys.argv[1], "w").close(); time.sleep(120)'
        args, cwd = [str(ready)], str(folder)
    else:
        code = 'import sys, time; held = open(sys.argv[2], "a"); open(sys.argv[1], "w").close(); time.sleep(120)'
        args, cwd = [str(ready), os.path.join(str(folder), 'notes.txt')], str(tmp_path)
    p = subprocess.Popen([sys.executable, '-c', code] + args, cwd=cwd,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0 = time.monotonic()
    while not ready.exists():
        if time.monotonic() - t0 > 30 or p.poll() is not None:
            p.kill()
            raise AssertionError('the holding program did not start')
        time.sleep(0.05)
    return p


def release(p):
    p.kill()
    p.wait(timeout=30)


def can_name_programs():
    return cmeta_files.processes_in_folders([os.getcwd()])['checked']


##########################################################################################
# Nothing changes while the artifact is in use

@pytest.mark.parametrize('what', ['cwd', 'file'])
@pytest.mark.parametrize('how', ['rename', 'another repository', 'migrate'])
def test_an_artifact_in_use_is_neither_moved_nor_renamed_nor_migrated(cm, tmp_path, how, what):
    other = other_repo(cm, tmp_path)
    folder = make(cm, 'held')
    uid = access(cm, category='log', command='find', arg1='held')['artifacts'][0]['cmeta_ref_parts']['artifact_uid']
    before = listing(folder)
    local_log = os.path.dirname(folder)

    command, target = {'rename': ('move', 'renamed'), 'another repository': ('move', 'other:'),
                       'migrate': ('migrate', 'renamed')}[how]
    p = hold(tmp_path, folder, what)
    try:
        r = access(cm, category='log', command=command, arg1='held', arg2=target)
    finally:
        release(p)

    assert r['return'] > 0 and 'in use - nothing was moved' in r['error'], r
    if os.name != 'nt' and can_name_programs():
        assert f'pid {p.pid}' in r['error'], r['error']
        assert ('working directory' if what == 'cwd' else 'a file open in it') in r['error'], r['error']

    # the artifact where it was, whole; nothing in the target; the index as it was; no stub
    assert listing(folder) == before
    assert sorted(os.listdir(local_log)) == ['held']
    assert sorted(os.listdir(other)) == ['_cmr.yaml']
    found = access(cm, category='log', command='find', arg1='held', follow_migrated=False)['artifacts']
    assert len(found) == 1 and found[0]['cmeta_ref_parts']['artifact_uid'] == uid
    assert os.path.normcase(os.path.normpath(found[0]['path'])) == os.path.normcase(os.path.normpath(folder))
    assert 'migrated_to' not in found[0]['cmeta']
    assert access(cm, category='log', command='find', arg1='renamed')['return'] == 16

    # once the program has left, the same command works
    r = access(cm, category='log', command=command, arg1='held', arg2=target)
    assert r['return'] == 0, r.get('error')


def test_several_artifacts_one_of_them_in_use_none_is_moved(cm, tmp_path):
    other = other_repo(cm, tmp_path)
    folders = {name: make(cm, name) for name in ('w-a', 'w-b', 'w-c')}
    p = hold(tmp_path, folders['w-b'], 'cwd')
    try:
        r = access(cm, category='log', command='move', arg1='w-*', arg2='other:')
    finally:
        release(p)
    assert r['return'] > 0 and 'w-b' in r['error'] and 'w-a:' not in r['error'], r
    assert sorted(os.listdir(os.path.dirname(folders['w-a']))) == ['w-a', 'w-b', 'w-c']
    assert sorted(os.listdir(other)) == ['_cmr.yaml']


def test_a_copy_of_an_artifact_in_use_is_made(cm, tmp_path):
    # a copy only reads the folder: allowed while it is in use, as before
    folder = make(cm, 'read-only-use')
    p = hold(tmp_path, folder, 'cwd')
    try:
        r = access(cm, category='log', command='copy', arg1='read-only-use', arg2='twin')
    finally:
        release(p)
    assert r['return'] == 0, r.get('error')
    assert listing(os.path.join(os.path.dirname(folder), 'twin')) == listing(folder)


@pytest.mark.skipif(os.name == 'nt', reason='Windows refuses the rename of a folder in use whatever is asked')
def test_ignore_in_use_moves_it_on_linux_and_macos(cm, tmp_path):
    folder = make(cm, 'moved-anyway')
    before = listing(folder)
    p = hold(tmp_path, folder, 'cwd')
    try:
        r = access(cm, category='log', command='move', arg1='moved-anyway', arg2='there', ignore_in_use=True)
    finally:
        release(p)
    assert r['return'] == 0, r.get('error')
    assert listing(os.path.join(os.path.dirname(folder), 'there')) == before and not os.path.exists(folder)


@pytest.mark.skipif(os.name != 'nt', reason='the system refusal is a Windows matter')
def test_on_windows_ignore_in_use_cannot_move_it_and_leaves_nothing_behind(cm, tmp_path):
    # the check is skipped, the system still refuses: the category folder made in the target is removed again
    other = other_repo(cm, tmp_path)
    folder = make(cm, 'held')
    before = listing(folder)
    p = hold(tmp_path, folder, 'cwd')
    try:
        r = access(cm, category='log', command='move', arg1='held', arg2='other:', ignore_in_use=True)
    finally:
        release(p)
    assert r['return'] > 0 and r.get('in_use') is True and 'nothing was moved' in r['error'], r
    assert listing(folder) == before and sorted(os.listdir(other)) == ['_cmr.yaml']


##########################################################################################
# The helpers

def test_who_uses_a_folder(tmp_path):
    used, free = tmp_path / 'used', tmp_path / 'free'
    (used / 'deeper').mkdir(parents=True)
    free.mkdir()
    (used / 'notes.txt').write_text('x', encoding='utf-8')

    r = cmeta_files.processes_in_folders([str(used), str(free)])
    assert r['return'] == 0 and r['processes'] == []
    if not r['checked']:
        assert os.name == 'nt' or not os.path.isdir('/proc')
        pytest.skip('no way to list the programs on this system: the rename itself refuses (Windows)')

    for what, word in (('cwd', 'working directory'), ('file', 'open file')):
        p = hold(tmp_path, used / 'deeper' if what == 'cwd' else used, what)
        try:
            r = cmeta_files.processes_in_folders([str(used), str(free)])
        finally:
            release(p)
        mine = [x for x in r['processes'] if x['pid'] == p.pid]
        assert len(mine) == 1 and mine[0]['what'] == word and mine[0]['folder'] == str(used), r
        assert not [x for x in r['processes'] if x['folder'] == str(free)]


def test_a_rename_refused_is_told_and_the_folder_is_left_as_it_was(tmp_path):
    folder = tmp_path / 'probe-me'
    (folder / 'sub').mkdir(parents=True)
    (folder / 'sub' / 'f.txt').write_text('x', encoding='utf-8')
    assert cmeta_files.rename_refused(str(folder)) is None
    assert listing(folder) == ['sub', 'sub/f.txt'] and sorted(os.listdir(tmp_path)) == ['probe-me']

    p = hold(tmp_path, folder, 'cwd')
    try:
        refused = cmeta_files.rename_refused(str(folder))
    finally:
        release(p)
    if os.name == 'nt':
        assert refused, 'Windows lets a folder in use be renamed?'
    else:
        assert refused is None                             # Linux and macOS allow it: processes_in_folders tells
    assert listing(folder) == ['sub', 'sub/f.txt'] and [n for n in os.listdir(tmp_path) if 'probe' in n] == ['probe-me']


def test_a_move_to_another_file_system_is_whole_or_not_at_all(tmp_path, monkeypatch):
    # another file system: copied, checked, the source taken aside and removed - the copy of every case made here
    monkeypatch.setattr(cmeta_files, 'same_file_system', lambda a, b: False)

    def source(name):
        folder = tmp_path / name
        (folder / 'sub').mkdir(parents=True)
        (folder / 'a.txt').write_text('a', encoding='utf-8')
        (folder / 'sub' / 'b.txt').write_text('bb', encoding='utf-8')
        return folder

    src, dst = source('src1'), tmp_path / 'target' / 'dst1'
    dst.parent.mkdir()
    r = cmeta_files.move_folder(str(src), str(dst))
    assert r == {'return': 0, 'how': 'copy', 'in_use': False}
    assert listing(dst) == ['a.txt', 'sub', 'sub/b.txt'] and not src.exists()
    assert not [n for n in os.listdir(tmp_path) if 'cmeta-moving' in n]

    # the copy fails half way: the half copy is removed, the source is as it was
    src, dst = source('src2'), tmp_path / 'target' / 'dst2'
    real_copytree = cmeta_files.shutil.copytree

    def half(a, b, **kwargs):
        os.makedirs(b)
        open(os.path.join(b, 'a.txt'), 'w').close()
        raise OSError('the disk is full')

    monkeypatch.setattr(cmeta_files.shutil, 'copytree', half)
    r = cmeta_files.move_folder(str(src), str(dst))
    monkeypatch.setattr(cmeta_files.shutil, 'copytree', real_copytree)
    assert r['return'] > 0 and 'nothing was moved' in r['error'] and 'the disk is full' in r['error']
    assert not dst.exists() and listing(src) == ['a.txt', 'sub', 'sub/b.txt']

    # a target that exists is never written into
    src = source('src3')
    (tmp_path / 'target' / 'taken').mkdir()
    r = cmeta_files.move_folder(str(src), str(tmp_path / 'target' / 'taken'))
    assert r['return'] > 0 and 'exists already' in r['error'] and listing(src) == ['a.txt', 'sub', 'sub/b.txt']

    if os.name == 'nt':
        # in use: the copy is made, then taking the source aside is refused - the copy goes, the source stays
        src, dst = source('src4'), tmp_path / 'target' / 'dst4'
        p = hold(tmp_path, src, 'cwd')
        try:
            r = cmeta_files.move_folder(str(src), str(dst))
        finally:
            release(p)
        assert r['return'] > 0 and r['in_use'] is True and 'nothing was moved' in r['error']
        assert not dst.exists() and listing(src) == ['a.txt', 'sub', 'sub/b.txt']
