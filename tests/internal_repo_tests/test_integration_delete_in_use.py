"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

An artifact whose folder is in use is not deleted half on Windows (2026-11-21): a program with its working directory
in the folder (a server started there, a terminal, a Far panel) or a file of it open made the deletion take the files
and leave the folder and its index record ("artifact already exists" at the next add). Now Windows refuses it whole -
the folder, its files and the index as they were - and --ignore_in_use deletes what can be deleted, as before. Linux
and macOS delete such a folder whole, as they always did.
"""

import os

import pytest

from test_integration_move_in_use import access, cm, hold, listing, make, release  # noqa: F401  (cm is a fixture)


@pytest.mark.parametrize('what', ['cwd', 'file'])
def test_an_artifact_in_use_is_deleted_whole_or_not_at_all(cm, tmp_path, what):
    folder = make(cm, 'held')
    before = listing(folder)
    p = hold(tmp_path, folder, what)
    try:
        r = access(cm, category='log', command='delete', arg1='held', force=True)
        if os.name == 'nt':
            assert r['return'] > 0 and 'in use - nothing was deleted' in r['error'] and r.get('in_use'), r
            assert listing(folder) == before
            assert access(cm, category='log', command='find', arg1='held')['artifacts']
        else:
            assert r['return'] == 0, r
            assert not os.path.exists(folder)
            assert not access(cm, category='log', command='find', arg1='held').get('artifacts')
    finally:
        release(p)

    if os.name == 'nt':
        # once the program is gone: deleted whole
        r = access(cm, category='log', command='delete', arg1='held', force=True)
        assert r['return'] == 0 and not os.path.exists(folder), r
        assert not access(cm, category='log', command='find', arg1='held').get('artifacts')


@pytest.mark.skipif(os.name != 'nt', reason='Windows only: elsewhere a folder in use is deleted whole anyway')
def test_on_windows_ignore_in_use_deletes_what_can_be_deleted(cm, tmp_path):
    folder = make(cm, 'held')
    p = hold(tmp_path, folder, 'cwd')
    try:
        r = access(cm, category='log', command='delete', arg1='held', force=True, ignore_in_use=True)
        assert 'nothing was deleted' not in str(r.get('error', '')), r
        assert not os.path.exists(os.path.join(folder, 'notes.txt'))      # the files went, as before 2026-11-21
    finally:
        release(p)


def test_several_artifacts_one_of_them_in_use_none_is_deleted_on_windows(cm, tmp_path):
    free = make(cm, 'free-one')
    held = make(cm, 'held-one')
    p = hold(tmp_path, held, 'cwd')
    try:
        r = access(cm, category='log', command='delete', arg1='*-one', force=True)
    finally:
        release(p)
    if os.name == 'nt':
        assert r['return'] > 0 and 'held-one' in r['error'] and os.path.isdir(free) and os.path.isdir(held), r
    else:
        assert r['return'] == 0 and not os.path.exists(free) and not os.path.exists(held), r
