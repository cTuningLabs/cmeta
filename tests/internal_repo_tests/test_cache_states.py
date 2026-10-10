"""
Tests of the cache category's states (`entry_state`, `cx cache classify`, `show --state`, `clean` by state) and
of the deletion of an artifact under the lock of its folder: an entry whose folder is locked by another process
(an attempt of the task engine) is `running`, is skipped by `clean`, and a `delete` of it fails as a whole
instead of removing the record and leaving the folder.

Each test runs against a fresh <CMETA_HOME> in tmp_path so it does not touch the user's real cMeta state.

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import json
import os
import pickle
import subprocess
import sys
import time

import pytest

from cmeta import CMeta
from cmeta import repos as cmeta_repos
from cmeta.utils import files

CATEGORY = 'cache'
RESULT = 'cmeta-task-cached-result.json'
RUNNING = 'cmeta-task-running.json'


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX',
                'CMETA_DEBUG', 'CMETA_VERBOSE', 'CMETA_FAIL_ON_ERROR', 'CMETA_INDEX_LOCK_TIMEOUT', 'CMETA_LOCK_TIMEOUT'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    monkeypatch.setattr(cmeta_repos, '_migrated_notices', set())
    return CMeta(home=str(tmp_path))


def make_entry(cm, alias, tags=(), result=None, params=None, path=None, running=None, request_params=None, ctx=False):
    """A cache entry with the files of a task attempt as the task engine leaves them (`request_params`: the
    request record of an entry made since cmeta-aops 0.45; `ctx`: the ctx file of a finished attempt)."""
    meta = {'params': dict(params or {})}
    if path is not None:
        meta['path'] = path
    if request_params is not None:
        meta['request_params'] = dict(request_params)
    r = cm.access({'category': CATEGORY, 'command': 'create', 'arg1': f'local:{alias}', 'tags': list(tags),
                   'meta': meta, 'con': False})
    assert r['return'] == 0, r.get('error')
    folder = r['path']
    where = path or folder
    os.makedirs(where, exist_ok=True)
    if result is not None:
        with open(os.path.join(where, RESULT), 'w', encoding='utf-8') as f:
            json.dump(result, f)
    if ctx:
        with open(os.path.join(where, 'cmeta-task-cached-ctx.json'), 'w', encoding='utf-8') as f:
            json.dump({'tasks': {}}, f)
    if running is not None:
        with open(os.path.join(folder, RUNNING), 'w', encoding='utf-8') as f:
            json.dump(running, f)
    return folder, r['meta']['artifact']


def state_of(cm, uid):
    r = cm.access({'category': CATEGORY, 'command': 'classify', 'arg1': uid, 'con': False})
    assert r['return'] == 0, r.get('error')
    return r['states'][uid]


def aliases_in_index(home):
    with open(home / 'index' / f'{CATEGORY}.pkl', 'rb') as f:
        data = pickle.load(f)
    return set(data['lowercase_aliases'])


HOLDER = r'''
import sys, time
from cmeta.utils import files
lock = files.PathLock(sys.argv[1]).acquire(timeout=60, note=sys.argv[2])
print('LOCKED', flush=True)
time.sleep(float(sys.argv[3]))
lock.release()
'''


def hold(lock_file, note, seconds=60):
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    p = subprocess.Popen([sys.executable, '-c', HOLDER, str(lock_file), note, str(seconds)], env=env,
                         stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    line = p.stdout.readline().decode('utf-8', 'replace')
    assert 'LOCKED' in line, line
    return p


def stop(p):
    p.kill()
    p.communicate()


def test_the_states_of_cache_entries(cm, tmp_path):
    ok, ok_uid = make_entry(cm, 'task--x--ok', result={'return': 0, 'x': 1})
    failed_tag, failed_tag_uid = make_entry(cm, 'task--x--failed', tags=['failed'], result={'return': 1, 'error': 'boom'})
    failed_result, failed_result_uid = make_entry(cm, 'task--x--failed-legacy', result={'return': 2, 'error': 'old'})
    crashed, crashed_uid = make_entry(cm, 'task--x--crashed', tags=['tmp'], running={'pid': 1, 'host': 'h', 'started': 't'})
    # a result missing from an entry the task engine made (its request record, or the ctx file of an earlier
    # attempt) is broken; a cache artifact that never carries a result (a program's build workspace) is not
    no_result, no_result_uid = make_entry(cm, 'task--x--broken-no-result', request_params={'name': 'x'})
    no_result_old, no_result_old_uid = make_entry(cm, 'task--x--broken-no-result-old', ctx=True)
    workspace, workspace_uid = make_entry(cm, 'task--program--x')
    bad_result, bad_result_uid = make_entry(cm, 'task--x--broken-bad-result')
    with open(os.path.join(bad_result, RESULT), 'w') as f:
        f.write('{not json')
    gone_tool, gone_tool_uid = make_entry(cm, 'task--x--broken-tool', result={'return': 0},
                                          params={'tool_path': str(tmp_path / 'no-such-tool')})
    elsewhere = tmp_path / 'elsewhere'
    with_path, with_path_uid = make_entry(cm, 'task--x--ok-path', result={'return': 0}, path=str(elsewhere))

    assert state_of(cm, ok_uid)['state'] == 'ok'
    assert state_of(cm, failed_tag_uid)['state'] == 'failed'
    assert state_of(cm, failed_result_uid)['state'] == 'failed'
    assert state_of(cm, failed_result_uid)['result_return'] == 2
    s = state_of(cm, crashed_uid)
    assert s['state'] == 'crashed' and 'pid 1' in s['why']
    assert state_of(cm, no_result_uid)['state'] == 'broken'
    assert state_of(cm, no_result_old_uid)['state'] == 'broken'
    assert state_of(cm, workspace_uid)['state'] == 'ok', 'a cache artifact without a task result is not broken'
    assert state_of(cm, bad_result_uid)['state'] == 'broken'
    assert 'no-such-tool' in state_of(cm, gone_tool_uid)['why'] and state_of(cm, gone_tool_uid)['state'] == 'broken'
    assert state_of(cm, with_path_uid)['state'] == 'ok', 'the result of an entry with a path lives in that path'

    # show --state filters; an unknown state is an error
    r = cm.access({'category': CATEGORY, 'command': 'show', 'state': 'failed,broken', 'con': False})
    assert r['return'] == 0
    assert {a['cmeta_ref_parts']['artifact_uid'] for a in r['artifacts']} == {failed_tag_uid, failed_result_uid, no_result_uid, no_result_old_uid, bad_result_uid, gone_tool_uid}
    r = cm.access({'category': CATEGORY, 'command': 'show', 'state': 'odd', 'con': False})
    assert r['return'] > 0 and 'unknown cache state' in r['error']

    # clean: crashed by default, the others by flag; the ok ones (the workspace included) stay
    r = cm.access({'category': CATEGORY, 'command': 'clean', 'con': False})
    assert r['return'] == 0 and r['removed'] == [crashed_uid], r
    r = cm.access({'category': CATEGORY, 'command': 'clean', 'failed': True, 'broken': True, 'con': False})
    assert r['return'] == 0 and set(r['removed']) == {failed_tag_uid, failed_result_uid, no_result_uid, no_result_old_uid, bad_result_uid, gone_tool_uid}, r
    assert aliases_in_index(tmp_path) == {'task--x--ok', 'task--x--ok-path', 'task--program--x'}
    assert not os.path.isdir(crashed) and not os.path.isdir(no_result) and os.path.isdir(ok) and os.path.isdir(workspace)

    # --all without --force is refused; with it everything that is not running goes
    r = cm.access({'category': CATEGORY, 'command': 'clean', 'all': True, 'con': False})
    assert r['return'] > 0 and 'force' in r['error']
    r = cm.access({'category': CATEGORY, 'command': 'clean', 'all': True, 'force': True, 'con': False})
    assert r['return'] == 0 and set(r['removed']) == {ok_uid, with_path_uid, workspace_uid}
    assert aliases_in_index(tmp_path) == set()


def test_a_locked_entry_is_running_and_is_neither_cleaned_nor_deleted(cm, tmp_path):
    folder, uid = make_entry(cm, 'task--y--building', tags=['tmp'], running={'pid': 4242, 'host': 'h', 'started': 't'})
    holder = hold(files._get_lockfile_path(os.path.normpath(folder)), 'task run y by pid 4242 on h since t')
    try:
        s = state_of(cm, uid)
        assert s['state'] == 'running' and s['locked'] and 'pid 4242' in s['holder'], s

        r = cm.access({'category': CATEGORY, 'command': 'clean', 'unfinished': True, 'con': False})
        assert r['return'] == 0 and r['removed'] == [] and uid in r['skipped'], r

        # A delete waits for the folder lock and then fails as a whole: the record stays with the folder
        t0 = time.time()
        r = cm.access({'category': CATEGORY, 'command': 'delete', 'arg1': uid, 'force': True, 'con': False},
                      )
        elapsed = time.time() - t0
        assert r['return'] > 0 and 'locked by another process' in r['error'], r
        assert os.path.isdir(folder)
        assert aliases_in_index(tmp_path) == {'task--y--building'}
        assert elapsed < 120
    finally:
        stop(holder)

    # Released (the holder gone): crashed, cleanable
    assert state_of(cm, uid)['state'] == 'crashed'
    r = cm.access({'category': CATEGORY, 'command': 'clean', 'con': False})
    assert r['return'] == 0 and r['removed'] == [uid]
    assert not os.path.isdir(folder) and aliases_in_index(tmp_path) == set()


def test_delete_holds_the_folder_lock_across_record_and_folder(cm, tmp_path):
    """safe_delete_directory with the caller's lock: the lock is used, not released, and the folder goes."""
    folder, uid = make_entry(cm, 'task--z--plain', result={'return': 0})
    lock = files.PathLock(files._get_lockfile_path(os.path.normpath(folder))).acquire(timeout=5)
    try:
        r = files.safe_delete_directory(folder, file_lock=lock)
        assert r['return'] == 0 and not os.path.isdir(folder)
        assert lock.is_locked, 'the caller keeps its lock'
    finally:
        lock.release()
    assert not os.path.exists(files._get_lockfile_path(os.path.normpath(folder)))
