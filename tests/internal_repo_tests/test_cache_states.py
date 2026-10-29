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
        t0 = time.monotonic()
        r = cm.access({'category': CATEGORY, 'command': 'delete', 'arg1': uid, 'force': True, 'con': False},
                      )
        elapsed = time.monotonic() - t0
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


def twin(cm, stem, uid, params, tags=('task', 'd'), **more):
    """
    A usable entry named as the task engine names its entries - `<stem><uid>` - with a UID of the test's
    choice, so that the order of the aliases is known. The pause makes the next entry newer on every clock
    (Windows before Python 3.13 ticks every 15 ms).
    """
    folder, made_uid = make_entry(cm, f'{stem}{uid},{uid}', tags=list(tags), result={'return': 0}, params=params, **more)
    assert made_uid == uid, made_uid

    time.sleep(0.05)

    return folder, uid


def installed_tool(cm, stem, uid, name):
    """A usable entry of a tool installed into the entry itself: its `tool_path` is inside its own folder."""
    folder, uid = twin(cm, stem, uid, {'name': name, 'version': '2'}, tags=('task', 't'))

    tool = os.path.join(folder, 'content', 'bin', name)
    os.makedirs(os.path.dirname(tool))
    with open(tool, 'w') as f:
        f.write('tool')

    r = cm.access({'category': CATEGORY, 'command': 'update', 'arg1': uid, 'meta': {'params': {'tool_path': tool}}, 'con': False})
    assert r['return'] == 0, r.get('error')

    return folder, uid


def stamped_tool(cm, alias, saved=None, tool_path=None):
    """An entry with a tool installed into its own folder and the result as the task engine saves it: the folder it
    was saved in (`_cmeta_entry_path`, default its own) and the recorded `tool_path` (default the tool there)."""
    folder, uid = make_entry(cm, alias)
    tool = os.path.join(folder, 'content', 'bin', 'tool')
    os.makedirs(os.path.dirname(tool))
    with open(tool, 'w') as f:
        f.write('tool')
    with open(os.path.join(folder, RESULT), 'w', encoding='utf-8') as f:
        json.dump({'return': 0, '_cmeta_entry_path': saved or folder, 'path': tool_path or tool}, f)
    r = cm.access({'category': CATEGORY, 'command': 'update', 'arg1': uid, 'meta': {'params': {'tool_path': tool_path or tool}}, 'con': False})
    assert r['return'] == 0, r.get('error')
    return folder, uid, tool


def test_a_moved_entry_keeps_its_tool(cm, tmp_path):
    """
    cx cache move (or a repository synced or mounted elsewhere): the recorded tool_path still names the folder the
    entry was saved in - the entry was "broken" and its tool installed again. The result's `_cmeta_entry_path` says
    which folder that was, and the same path under the entry's current folder counts.
    """
    folder, uid, tool = stamped_tool(cm, 'task--t--moved')
    assert state_of(cm, uid)['state'] == 'ok'

    r = cm.access({'category': CATEGORY, 'command': 'move', 'arg1': uid, 'arg2': 'task--t--moved-here', 'con': False})
    assert r['return'] == 0, r.get('error')
    here = os.path.join(os.path.dirname(folder), 'task--t--moved-here')
    assert not os.path.exists(tool) and os.path.isfile(os.path.join(here, 'content', 'bin', 'tool'))
    assert state_of(cm, uid)['state'] == 'ok', state_of(cm, uid)

    # without the stamp (an entry saved before it existed) the old rule holds; so it does when the file is gone
    with open(os.path.join(here, RESULT), 'w', encoding='utf-8') as f:
        json.dump({'return': 0}, f)
    s = state_of(cm, uid)
    assert s['state'] == 'broken' and 'tool_path is gone' in s['why'], s
    with open(os.path.join(here, RESULT), 'w', encoding='utf-8') as f:
        json.dump({'return': 0, '_cmeta_entry_path': folder}, f)
    os.remove(os.path.join(here, 'content', 'bin', 'tool'))
    assert state_of(cm, uid)['state'] == 'broken'


def test_a_path_saved_on_windows_is_relocated_on_any_os(cm, tmp_path):
    """The folder an entry was saved in on Windows (another case, the other separator) relocates on any OS."""
    saved = 'C:\\Users\\Someone\\CMETA\\repos\\local\\cache\\task--t--win'
    folder, uid, tool = stamped_tool(cm, 'task--t--win', saved=saved,
                                     tool_path='c:\\users\\someone\\cmeta\\repos\\local\\cache\\TASK--T--WIN\\content\\bin\\tool')
    assert state_of(cm, uid)['state'] == 'ok', state_of(cm, uid)


def test_duplicates_are_the_usable_entries_that_answer_the_same_requests(cm, tmp_path):
    params = {'name': 'd', 'version': '1', 'with': {'compute': ['cpu']}}

    # Three entries of one configuration, named as the task engine names them (the UID at the end). The order
    # of their aliases - 1111, 5555, ffff - says nothing: the time of creation orders them
    oldest, oldest_uid = twin(cm, 'task--d--', '5555555555555555', params)
    middle, middle_uid = twin(cm, 'task--d--', '1111111111111111', params)
    newest, newest_uid = twin(cm, 'task--d--', 'ffffffffffffffff', params)

    # Not duplicates of them: another version, other tags, another path, a failed attempt of the same configuration
    other_version, other_version_uid = twin(cm, 'task--d--', '2222222222222222', dict(params, version='2'))
    other_tags, other_tags_uid = twin(cm, 'task--d--', '3333333333333333', params, tags=('task', 'e'))
    elsewhere, elsewhere_uid = twin(cm, 'task--d--', '4444444444444444', params, path=str(tmp_path / 'elsewhere'))
    failed, failed_uid = make_entry(cm, 'task--d--6666666666666666,6666666666666666', tags=['task', 'd', 'failed'],
                                    result={'return': 1, 'error': 'boom'}, params=params)

    # Nor is an entry with a name of its own, whatever its tags and parameters: it is found by that name. The
    # build workspaces of two programs have the same tags and no parameters, and they are two things (a first
    # version of the rule called the 20 workspaces of a real home duplicates of each other)
    named, named_uid = make_entry(cm, 'task--d--workspace', tags=['task', 'd'], result={'return': 0}, params=params)
    program_one, program_one_uid = make_entry(cm, 'task--program--one', tags=['task', 'program'])
    program_two, program_two_uid = make_entry(cm, 'task--program--two', tags=['task', 'program'])

    # A tool installed twice, each into its own entry: the same thing although the recorded paths differ
    tool_old, tool_old_uid = installed_tool(cm, 'task--t--', 'aaaaaaaaaaaaaaaa', 'tool')
    tool_new, tool_new_uid = installed_tool(cm, 'task--t--', '0a0a0a0a0a0a0a0a', 'tool')

    r = cm.access({'category': CATEGORY, 'command': 'show', 'duplicates': True, 'con': False})
    assert r['return'] == 0, r.get('error')

    # Group by group (by the alias of the entry that stays), the newest first in each
    assert r['duplicates'] == [[newest_uid, middle_uid, oldest_uid], [tool_new_uid, tool_old_uid]], r['duplicates']
    assert [a['cmeta_ref_parts']['artifact_uid'] for a in r['artifacts']] == [newest_uid, middle_uid, oldest_uid, tool_new_uid, tool_old_uid]

    # Narrowed like every find
    r = cm.access({'category': CATEGORY, 'command': 'show', 'duplicates': True, 'tags': 'd', 'con': False})
    assert r['return'] == 0 and r['duplicates'] == [[newest_uid, middle_uid, oldest_uid]], r

    # clean --duplicates: the newest of each group stays, nothing else goes (not even the failed entry)
    r = cm.access({'category': CATEGORY, 'command': 'clean', 'duplicates': True, 'con': False})
    assert r['return'] == 0 and set(r['removed']) == {middle_uid, oldest_uid, tool_old_uid}, r

    assert aliases_in_index(tmp_path) == {'task--d--ffffffffffffffff', 'task--d--2222222222222222', 'task--d--3333333333333333',
                                          'task--d--4444444444444444', 'task--d--6666666666666666', 'task--d--workspace',
                                          'task--program--one', 'task--program--two', 'task--t--0a0a0a0a0a0a0a0a'}
    assert not os.path.isdir(oldest) and not os.path.isdir(middle) and not os.path.isdir(tool_old)
    assert os.path.isdir(newest) and os.path.isdir(tool_new) and os.path.isdir(failed)
    assert os.path.isdir(named) and os.path.isdir(program_one) and os.path.isdir(program_two)

    # Nothing left to remove
    r = cm.access({'category': CATEGORY, 'command': 'show', 'duplicates': True, 'con': False})
    assert r['return'] == 0 and r['duplicates'] == [] and r['artifacts'] == []
    r = cm.access({'category': CATEGORY, 'command': 'clean', 'duplicates': True, 'con': False})
    assert r['return'] == 0 and r['removed'] == []

    # A plain clean still removes the crashed entries only, and a state flag goes with --duplicates
    more, more_uid = twin(cm, 'task--d--', '7777777777777777', params)
    r = cm.access({'category': CATEGORY, 'command': 'clean', 'con': False})
    assert r['return'] == 0 and r['removed'] == []
    r = cm.access({'category': CATEGORY, 'command': 'clean', 'duplicates': True, 'failed': True, 'con': False})
    assert r['return'] == 0 and set(r['removed']) == {newest_uid, failed_uid}, r
    assert os.path.isdir(more) and not os.path.isdir(newest)


def test_a_running_entry_is_no_duplicate_and_what_show_prints(cm, tmp_path, capsys):
    params = {'name': 'r', 'version': '1'}

    # A cache without any entry has no duplicates: an answer, not the "not found" of a plain show
    r = cm.access({'category': CATEGORY, 'command': 'show', 'duplicates': True, 'con': False})
    assert r['return'] == 0 and r['duplicates'] == [] and r['artifacts'] == [], r
    r = cm.access({'category': CATEGORY, 'command': 'clean', 'duplicates': True, 'con': False})
    assert r['return'] == 0 and r['removed'] == [], r

    older, older_uid = twin(cm, 'task--r--', '1111111111111111', params, tags=('task', 'r'))
    newer, newer_uid = twin(cm, 'task--r--', 'eeeeeeeeeeeeeeee', params, tags=('task', 'r'))

    # The newer one is being rebuilt by another process: it is not usable now, so the older one has no duplicate
    holder = hold(files._get_lockfile_path(os.path.normpath(newer)), 'task run r by pid 4242 on h since t')
    try:
        r = cm.access({'category': CATEGORY, 'command': 'show', 'duplicates': True, 'con': False})
        assert r['return'] == 0 and r['duplicates'] == [], r

        r = cm.access({'category': CATEGORY, 'command': 'clean', 'duplicates': True, 'con': False})
        assert r['return'] == 0 and r['removed'] == [] and newer_uid in r['skipped'], r
        assert os.path.isdir(older) and os.path.isdir(newer)
    finally:
        stop(holder)

    # With the console: each entry says its place in its group, the last line what a clean would do
    capsys.readouterr()
    r = cm.access({'category': CATEGORY, 'command': 'show', 'duplicates': True, 'con': True})
    assert r['return'] == 0 and r['duplicates'] == [[newer_uid, older_uid]]

    out = capsys.readouterr().out
    assert 'duplicate = group 1, 1 of 2, made 20' in out and 'the newest: the one a request takes' in out, out
    assert 'duplicate = group 1, 2 of 2, made 20' in out and 'older: "clean --duplicates" removes it' in out, out
    assert '1 group(s) of entries that answer the same requests' in out and 'removes the other 1' in out, out
    assert out.index('task--r--eeeeeeeeeeeeeeee') < out.index('task--r--1111111111111111'), out

    r = cm.access({'category': CATEGORY, 'command': 'clean', 'duplicates': True, 'con': True})
    assert r['return'] == 0 and r['removed'] == [older_uid]
    assert 'removed task--r--1111111111111111 (a duplicate of task--r--eeeeeeeeeeeeeeee)' in capsys.readouterr().out

    r = cm.access({'category': CATEGORY, 'command': 'show', 'duplicates': True, 'con': True})
    assert r['return'] == 0 and 'no duplicates among the usable entries' in capsys.readouterr().out


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
