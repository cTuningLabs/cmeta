"""
Tests of utils.files.remove_files_and_dirs_in_path - what cleans a build folder, a download folder, a test's
sandbox - and of the removal it shares with utils.files.safe_delete_directory (what deletes an artifact's folder).

An entry that cannot be removed - a file in use on Windows, a file in a folder this process may not change -
used to stop the removal with the exception of that entry, and everything it had not reached stayed (a sandbox
kept 21,500 files beside a few of another account, 2026-11-26). The removal now goes on: every other entry is
removed and the result is an error that names what stayed. Its walk goes through the extended-length prefix on
Windows, so that entries beyond 260 characters are listed on a machine without long-path support too.

Elsewhere than on Windows the rights of a folder decide whether what it holds can be removed: a tree made read-only
(a module cache, a build system's outputs) was not removed and a folder of it lost its rights on the way (an
artifact with such a tree could not be deleted, 2026-11-26). Such a tree is removed, a folder that cannot be listed
too, and what stays keeps the rights it had.

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import stat
import sys

import pytest

from cmeta.utils import files

WINDOWS = sys.platform == 'win32'
ROOT = hasattr(os, 'geteuid') and os.geteuid() == 0


def tree(root, folders = ('a/b/c/d', 'k/l', 'x/y/z', 'p'), per_folder = 3):
    for sub in folders:
        os.makedirs(os.path.join(root, *sub.split('/')), exist_ok = True)
        for n in range(per_folder):
            with open(os.path.join(root, *sub.split('/'), f'f{n}.txt'), 'w') as f:
                f.write('x')


def entries(root):
    base = files._to_extended_path(root)
    return sorted(os.path.relpath(os.path.join(d, n), base).replace(os.sep, '/')
                  for d, ds, fs in os.walk(base) for n in fs + ds)


HELD = 'held.bin'


class Kept:
    """A file that this process cannot remove while the object lives. On Windows it is held open (no delete sharing).
    Elsewhere nothing a test can make refuses its owner - a file of another account would, and only root makes one -
    so the system's removal of a file of this name is stood in for by one that refuses it, as the system does for
    such a file (refuse_held)."""

    def __init__(self, path):
        assert os.path.basename(path) == HELD
        self.path = path
        with open(path, 'w') as f:
            f.write('x')
        self.handle = open(path, 'r') if WINDOWS else None

    def release(self):
        if self.handle:
            self.handle.close()


def refuse_held(monkeypatch):
    """Not on Windows: os.unlink refuses a file named held.bin with "Operation not permitted"."""
    if WINDOWS:
        return
    real = os.unlink

    def unlink(path, *args, **kwargs):
        if os.path.basename(os.fspath(path)) == HELD:
            raise PermissionError(1, 'Operation not permitted', os.fspath(path))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(os, 'unlink', unlink)


def test_everything_in_the_folder_goes_and_the_folder_stays(tmp_path):
    root = str(tmp_path / 'r')
    tree(root)
    read_only = os.path.join(root, 'p', 'f0.txt')
    os.chmod(read_only, stat.S_IREAD)                    # git's objects are read-only: Windows refuses to delete them

    r = files.remove_files_and_dirs_in_path(root)

    assert r == {'return': 0}
    assert os.path.isdir(root) and entries(root) == []


def test_a_pattern_and_the_names_to_ignore_as_before(tmp_path):
    root = str(tmp_path / 'r')
    os.makedirs(os.path.join(root, 'sub'))
    for name in ('one.log', 'keep.log', 'two.txt', os.path.join('sub', 'three.log')):
        with open(os.path.join(root, name), 'w') as f:
            f.write('x')

    r = files.remove_files_and_dirs_in_path(root, pattern = '*.log', ignore = ['keep.log'])

    assert r == {'return': 0}
    assert entries(root) == ['keep.log', 'sub', 'two.txt']


def test_an_entry_that_cannot_be_removed_does_not_keep_the_others(tmp_path, monkeypatch):
    monkeypatch.setattr(files.time, 'sleep', lambda seconds: None)
    refuse_held(monkeypatch)
    root = str(tmp_path / 'r')
    tree(root)
    kept = Kept(os.path.join(root, 'k', 'l', 'held.bin'))
    try:
        r = files.remove_files_and_dirs_in_path(root)
        after = entries(root)
    finally:
        kept.release()

    # the file, and the two folders above it
    assert r['return'] == 1
    assert after == ['k', 'k/l', 'k/l/held.bin']
    assert not any(e.startswith(('a', 'x', 'p')) for e in after), after

    # what stayed is named as it was given - no extended-length prefix, and no folder that only holds it
    assert all(os.path.normcase(p).startswith(os.path.normcase(os.path.join(root, 'k', 'l'))) for p in r['left'])
    assert os.path.join(root, 'k') not in r['left'] and os.path.join(root, 'k', 'l') not in r['left']
    assert ('1 entry of' in r['error']) == (len(r['left']) == 1)
    assert r['left'][0] in r['error'] and '?' not in r['left'][0]


def test_many_entries_that_stay_are_not_each_waited_for(tmp_path, monkeypatch):
    # a short lock (antivirus, an indexer) is waited for: five tries with a pause between them - for the first three
    # entries that stay only, then one try each: a tree of another account's files took 1.5 s a file otherwise
    slept = []
    monkeypatch.setattr(files.time, 'sleep', lambda seconds: slept.append(seconds))
    refuse_held(monkeypatch)
    root = str(tmp_path / 'r')
    held = []
    try:
        for n in range(10):
            os.makedirs(os.path.join(root, f'd{n}'))
            held.append(Kept(os.path.join(root, f'd{n}', 'held.bin')))
        r = files.remove_files_and_dirs_in_path(root)
    finally:
        for k in held:
            k.release()

    assert r['return'] == 1 and len(r['left']) == 10
    assert '10 entries of' in r['error']
    assert len(slept) == 3 * 4


@pytest.mark.skipif(WINDOWS or ROOT, reason = 'the rights of a folder decide a removal elsewhere than on Windows, and not for root')
def test_a_tree_made_read_only_is_removed(tmp_path):
    # a module cache, a build system's outputs: every folder without the right to write, every file read-only
    root = str(tmp_path / 'r')
    tree(root)
    for d, ds, fs in os.walk(root, topdown = False):
        for n in fs:
            os.chmod(os.path.join(d, n), 0o444)
        if d != root:
            os.chmod(d, 0o555)

    r = files.remove_files_and_dirs_in_path(root)

    assert r == {'return': 0}
    assert entries(root) == []


@pytest.mark.skipif(WINDOWS or ROOT, reason = 'the rights of a folder decide a removal elsewhere than on Windows, and not for root')
def test_a_folder_that_cannot_be_listed_is_removed_with_what_it_holds(tmp_path):
    root = str(tmp_path / 'r')
    tree(root)
    os.chmod(os.path.join(root, 'k', 'l'), 0o000)        # not to be read, entered or written
    os.chmod(os.path.join(root, 'x', 'y'), 0o300)        # not to be read

    r = files.remove_files_and_dirs_in_path(root)

    assert r == {'return': 0}
    assert entries(root) == []


def test_the_folder_of_an_artifact_with_read_only_entries_is_deleted(tmp_path):
    # git's objects are read-only files (Windows refuses to delete them); a build system's outputs are read-only
    # folders too (elsewhere nothing of them could be removed)
    root = str(tmp_path / 'artifact')
    tree(root)
    for d, ds, fs in os.walk(root, topdown = False):
        for n in fs:
            os.chmod(os.path.join(d, n), stat.S_IREAD)
        if not WINDOWS and not ROOT:
            os.chmod(d, 0o555)

    r = files.safe_delete_directory(root)

    assert r['return'] == 0, r
    assert not os.path.exists(root)


@pytest.mark.skipif(WINDOWS or ROOT, reason = 'the rights of a folder decide a removal elsewhere than on Windows, and not for root')
def test_the_folder_of_an_artifact_with_a_folder_that_cannot_be_listed_is_deleted(tmp_path):
    root = str(tmp_path / 'artifact')
    tree(root)
    os.chmod(os.path.join(root, 'a', 'b', 'c'), 0o000)

    r = files.safe_delete_directory(root)

    assert r['return'] == 0, r
    assert not os.path.exists(root)


@pytest.mark.skipif(ROOT, reason = 'root is refused nothing')
def test_what_stays_keeps_the_rights_it_had(tmp_path, monkeypatch):
    monkeypatch.setattr(files.time, 'sleep', lambda seconds: None)
    refuse_held(monkeypatch)
    root = str(tmp_path / 'r')
    folder = os.path.join(root, 'k', 'l')
    os.makedirs(folder)
    kept = Kept(os.path.join(folder, HELD))
    with open(os.path.join(folder, 'other.txt'), 'w') as f:
        f.write('x')

    # the file read-only; elsewhere than on Windows its folder too (there a folder's rights refuse nothing)
    os.chmod(kept.path, stat.S_IREAD)
    if not WINDOWS:
        os.chmod(folder, 0o555)
    before = (stat.S_IMODE(os.stat(kept.path).st_mode), stat.S_IMODE(os.stat(folder).st_mode))
    try:
        r = files.remove_files_and_dirs_in_path(root)
        after = (stat.S_IMODE(os.stat(kept.path).st_mode), stat.S_IMODE(os.stat(folder).st_mode))
        left = entries(root)
    finally:
        kept.release()
        os.chmod(folder, 0o755)
        os.chmod(kept.path, stat.S_IWRITE | stat.S_IREAD)

    # its neighbour went (from a read-only folder, elsewhere than on Windows), the file stays as it was
    assert r['return'] == 1 and left == ['k', 'k/l', 'k/l/' + HELD]
    assert after == before


def test_paths_beyond_260_characters(tmp_path):
    root = str(tmp_path / 'r')
    deep = os.path.join(root, *['a-folder-name-of-forty-characters-0123456'] * 7)
    os.makedirs(files._to_extended_path(deep))
    with open(files._to_extended_path(os.path.join(deep, 'file.txt')), 'w') as f:
        f.write('x')
    assert len(os.path.join(deep, 'file.txt')) > 260

    r = files.remove_files_and_dirs_in_path(root)

    assert r == {'return': 0}
    assert entries(root) == []


def test_the_path_of_a_message_without_the_prefix():
    back = files._from_extended_path
    assert back('/home/u/x') == '/home/u/x'
    assert back('C:' + chr(92) + 'x') == 'C:' + chr(92) + 'x'
    extended = chr(92) * 2 + '?' + chr(92)
    assert back(extended + 'C:' + chr(92) + 'x') == 'C:' + chr(92) + 'x'
    assert back(extended + 'UNC' + chr(92) + 'server' + chr(92) + 'share') == chr(92) * 2 + 'server' + chr(92) + 'share'
