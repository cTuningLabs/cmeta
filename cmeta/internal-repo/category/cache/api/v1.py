"""
cMeta cache functions

The cache category holds the entries of the task engine (cmeta-aops): the files a task downloaded or built,
its result (RESULT_FILE) and, while an attempt runs, who runs it (RUNNING_FILE). The state of an entry is
derived from its tags, its files and the lock of its folder (see `classify`): the task engine reuses, resumes
or waits for an entry by that state, `show` prints it, `clean` removes entries by it.

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import json

from cmeta.category import InitCategory

# The files the task engine of cmeta-aops writes into an entry (the names are a contract between the two)
RESULT_FILE = 'cmeta-task-cached-result.json'      # the result of the last attempt (return 0 = usable)
CTX_FILE = 'cmeta-task-cached-ctx.json'             # the context of a finished attempt (beside the result)
RUNNING_FILE = 'cmeta-task-running.json'            # who runs the current attempt (pid, host, started, request)

STATES = ('ok', 'running', 'crashed', 'failed', 'broken')


def entry_state(
    path: str,  # The folder of the entry.
    cmeta: dict,  # Its meta.
    probe_lock: bool = True,  # If True, the lock of the folder is probed (a held lock = an attempt is running).
):
    """
        The state of a cache entry and what it rests on:

        - `running`: the lock of the entry's folder is held (an attempt of the task engine, or a delete);
        - `crashed`: the `tmp` tag of an attempt that is not running any more (its process died);
        - `failed`: the `failed` tag (the last attempt ended with an error), or a result file with `return > 0`;
        - `broken`: a result file that cannot be read, a result file missing from an entry the task engine's
          cache flow made (its request record, or the ctx file of a finished attempt, is there), or the
          recorded `tool_path` (or `git_path`) is gone;
        - `ok`: everything else - a result with `return 0` and the recorded paths present, or a cache
          artifact that never carries a result (a program's build workspace, a folder used as storage).

        Returns:
            dict: {'state', 'locked' (bool), 'holder' (the note of the lock holder or ''), 'running' (the content
                  of RUNNING_FILE or None), 'result_return' (int or None), 'why' (one line)}.
    """
    from cmeta.utils import files

    tags = cmeta.get('tags', []) or []
    params = cmeta.get('params', {}) or {}

    info = {'state': 'ok', 'locked': False, 'holder': '', 'running': None, 'result_return': None, 'why': ''}

    running_file = os.path.join(path, RUNNING_FILE)
    if os.path.isfile(running_file):
        try:
            with open(running_file, 'r', encoding='utf-8') as f:
                info['running'] = json.load(f)
        except Exception:
            info['running'] = {}

    if probe_lock and os.path.isdir(path):
        lock_file = files._get_lockfile_path(path)
        lock = files.PathLock(lock_file)
        try:
            lock.acquire(timeout=0)
            lock.release()
        except TimeoutError:
            info['locked'] = True
            info['holder'] = files.PathLock.read_note(lock_file)
        except Exception:
            pass

    if info['locked']:
        info['state'] = 'running'
        info['why'] = info['holder'] or 'the folder is locked by another process'
        return info

    if 'tmp' in tags:
        info['state'] = 'crashed'
        r = info['running'] or {}
        info['why'] = f"an attempt that is not running any more (pid {r.get('pid')} on {r.get('host')} since {r.get('started')})" if r else 'an attempt that is not running any more'
        return info

    # The result lives in the entry's own folder, or in the path the entry was made for (--path)
    result_dir = cmeta.get('path') or path
    result_file = os.path.join(result_dir, RESULT_FILE)
    result = None
    if os.path.isfile(result_file):
        try:
            with open(result_file, 'r', encoding='utf-8') as f:
                result = json.load(f)
        except Exception:
            result = None

    if isinstance(result, dict) and 'return' in result:
        try:
            info['result_return'] = int(result['return'])
        except Exception:
            info['result_return'] = None

    if 'failed' in tags or (info['result_return'] is not None and info['result_return'] > 0):
        info['state'] = 'failed'
        err = result.get('error', '') if isinstance(result, dict) else ''
        info['why'] = f'the last attempt failed ({err})' if err else 'the last attempt failed'
        return info

    if info['result_return'] is None:
        if os.path.isfile(result_file):
            info['state'] = 'broken'
            info['why'] = 'the result file is not a result'
            return info
        # No result file: broken only for an entry the task engine's cache flow made (its request record
        # since cmeta-aops 0.45, or the ctx file of a finished attempt). Other cache artifacts never carry
        # a result - a program's build workspace (compile-and-run-program runs with cache: False and keeps
        # its tmp folders in one), a folder used as storage - and are not broken (a `clean --broken` must
        # not remove the 32 build workspaces of a developer's home).
        if cmeta.get('request_params') is not None or os.path.isfile(os.path.join(result_dir, CTX_FILE)):
            info['state'] = 'broken'
            info['why'] = 'no readable result file'
            return info
        info['why'] = 'no result file (a cache artifact without a task result)'
        return info

    for key in ('tool_path', 'git_path'):
        p = params.get(key)
        if p and not (os.path.isfile(p) or os.path.isdir(p)):
            info['state'] = 'broken'
            info['why'] = f'the recorded {key} is gone: {p}'
            return info

    return info


class Category(InitCategory):
    """
    """

    def __init__(
        self,
        *args,  # Positional argument value.
        **kwargs,  # Value for kwargs.
    ):
        """
        __init__ function.

        Args:
            *args: Positional argument value.
            **kwargs: Value for kwargs.

        Returns:
            dict: Operation result.

        Raises:
            Exception: Propagated runtime errors, if any.
        """
        super().__init__(*args, module_file_path = __file__, **kwargs)


    ############################################################
    def test_(
        self,
        ctx: dict,  # cMeta context.
        arg1: str = None,  # Test argument 1.
        flag1: bool = False,  # Test flag 1.
    ):
        """
            Test function.

            Args:
                ctx (dict): cMeta context.
                arg1 (str | None): Test argument 1.
                flag1 (bool): Test flag 1.

            Returns:
                dict: Dictionary with 'return': 0.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        self.logger.debug("RUNNING API v1 test_")

        print (f'arg1={arg1}')
        print (f'flag1={flag1}')

        return {'return':0}

    ############################################################
    def test2(
        self,
        params: dict,  # cMeta parameters.
    ):
        """
            Test function 2.

            Args:
                params (dict): cMeta parameters.

            Returns:
                dict: Dictionary with 'return': 0.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        self.logger.debug("RUNNING API v1 test2")

        import json
        print (json.dumps(params, indent=2))

        return {'return':0}

    ############################################################
    def classify_(
        self,
        ctx: dict,  # cMeta context.
        arg1: str = None,  # Artifact alias or UID filter (when `artifacts` is not given).
        tags: str = None,  # Comma-separated tags to match (when `artifacts` is not given).
        match: dict = None,  # Additional key-value match filter (when `artifacts` is not given).
        artifacts: list = None,  # The entries to classify, as `find` returns them (found here otherwise).
        probe_locks: bool = True,  # If True, the lock of every entry's folder is probed to tell running from crashed.
    ):
        """
            The state of cache entries: `ok`, `running`, `crashed`, `failed` or `broken` (see `entry_state`).
            The task engine asks this for the entries that match a cache query; `show` and `clean` use it.

            Args:
                ctx (dict): cMeta context.
                arg1 (str | None): Artifact alias or UID filter.
                tags (str | None): Comma-separated tags to match.
                match (dict | None): Additional key-value match filter.
                artifacts (list | None): The entries to classify; found with the filters above otherwise.
                probe_locks (bool): Probe the folder locks (False: a held lock is not detected, no file is opened).

            Returns:
                dict: {'return': 0, 'artifacts': [...], 'states': {uid: {'state': ..., ...}}}.

            Raises:
                Exception: Propagated runtime errors, if any.
        """
        if artifacts is None:
            p = {'category':ctx['category'],
                 'command':'find',
                 'arg1':arg1,
                 'tags':tags,
                 'match':match}

            r = self.cm.access(p)
            if r['return']>0:
                if r['return'] != 16: return r
                artifacts = []
            else:
                artifacts = r.get('artifacts', [])

        states = {}
        for a in artifacts:
            uid = a['cmeta_ref_parts']['artifact_uid']
            states[uid] = entry_state(a['path'], a.get('cmeta', {}), probe_lock = probe_locks)

        return {'return':0, 'artifacts': artifacts, 'states': states}

    ############################################################
    def show_(
        self,
        ctx: dict,  # cMeta context.
        arg1: str = None,  # Artifact alias or UID filter.
        tags: str = None,  # Comma-separated tags to match.
        sort: bool = None,  # If True, request sorted lookup from find.
        match: dict = None,  # Additional key-value match filter.
        sort_keys: list = None,  # Keys used to sort displayed artifacts.
        show_tags: bool = False,  # If True, print artifact tags in output.
        skip_uids: bool = False,  # If True, omit UIDs from printed entries.
        state: str = None,  # Show only the entries in these states (comma-separated: ok, running, crashed, failed, broken).
    ):
        """
            Show cache entries with their state (ok, running, crashed, failed, broken) and parameters.

            Args:
                ctx (dict): cMeta context.
                arg1 (str): Artifact alias or UID filter.
                tags (str): Comma-separated tags to match.
                sort (bool): If True, request sorted lookup from find.
                match (dict): Additional key-value match filter.
                sort_keys (list): Keys used to sort displayed artifacts.
                show_tags (bool): If True, print artifact tags in output.
                skip_uids (bool): If True, omit UIDs from printed entries.
                state (str): Show only the entries in these states (comma-separated).

            Returns:
                dict: Dictionary with 'return': 0, 'artifacts' (the entries shown) and 'states'.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        self.logger.debug("RUNNING cache show API v1")

        con = ctx['control'].get('con', False)

        wanted = None
        if state:
            wanted = [s.strip().lower() for s in str(state).split(',') if s.strip()]
            unknown = [s for s in wanted if s not in STATES]
            if unknown:
                return {'return':1, 'error': f"unknown cache state(s) {', '.join(unknown)} - the states are {', '.join(STATES)}"}

        # Call base find function to find an artifact with a website
        p = {'category':ctx['category'],
             'command':'find',
             'arg1':arg1,
             'tags':tags,
             'sort':sort,
             'match':match}

        r = self.cm.access(p)
        if r['return']>0:
            if r['return'] != 16 or wanted is None: return r
            r['artifacts'] = []

        artifacts = r.get('artifacts', [])

        r = self.classify_(ctx, artifacts = artifacts)
        if r['return']>0: return r
        states = r['states']

        if wanted is not None:
            artifacts = [a for a in artifacts if states[a['cmeta_ref_parts']['artifact_uid']]['state'] in wanted]

        xsort_keys = sort_keys if sort_keys else ["@cmeta.params.name", "@cmeta.params.version-", "@cmeta.params.tag-"]

        artifacts = sorted(
            artifacts,
            key=lambda a: self.cm.utils.common.build_sort_key(a, xsort_keys)
        )

        num_artifacts = len(artifacts)
        index = 1
        for n in range(num_artifacts):
            a = artifacts[n]
            if con:
                cmeta_ref_parts = a['cmeta_ref_parts']
                cmeta = a['cmeta']
                path = a['path']

                name = cmeta.get('name', '')
                alias = cmeta_ref_parts['artifact_alias']
                uid = cmeta_ref_parts['artifact_uid']

                x = name if name != '' else alias

                xtags = '[' + ','.join(cmeta.get('tags', [])) + '] ' if show_tags else ''

                xuid = f'({uid})' if not skip_uids else ''

                text = f'{index}) {x} {xtags}{xuid}'

                info = states[uid]
                why = f" - {info['why']}" if info.get('why') and info['state'] != 'ok' else ''
                text += f"\n      * state = {info['state']}{why}"

                xparams = {}
                for cmeta_params_key in ['params', 'tags', 'path']:
                    if cmeta_params_key in cmeta:
                        uparams = cmeta[cmeta_params_key]
                        if type(uparams) == dict:
                            for p in sorted(uparams):
                                xparams[cmeta_params_key+'.'+p] = str(uparams[p])
                        elif type(uparams) == list:
                            xparams[cmeta_params_key] = ','.join(uparams)
                        else:
                            xparams[cmeta_params_key] = str(uparams)

                if len(xparams)>0:
                    for p in sorted(xparams):
                        v = xparams[p]
                        text += f'\n      * {p} = {v}'

                print (text)

                if n != num_artifacts-1:
                    print ('')

            index += 1

        return {'return':0, 'artifacts': artifacts, 'states': states}

    ############################################################
    def clean(
        self,
        params: dict,  # cMeta parameters.
    ):
        """
            Remove cache entries by state: the crashed ones (an attempt whose process died - the `tmp` tag
            without a running attempt) by default; `--failed` adds the entries whose last attempt failed,
            `--broken` those without a usable result or whose recorded paths are gone, `--unfinished` all
            three. A running entry is never removed (its process holds the folder's lock); `--all` with
            `--force` removes every entry that is not running. `arg1`, `tags` and `match` narrow the
            selection as for `find`.

            Args:
                params (dict): cMeta parameters.

            Returns:
                dict: Dictionary with 'return': 0, 'removed' (the uids removed), 'skipped' (uid: why).

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        # p will be deep copied from params
        p = self._prepare_input_from_params(params, base = True)

        ctx = params['ctx']
        con = ctx['control'].get('con', False)

        wanted = set()
        if p.pop('crashed', False): wanted.add('crashed')
        if p.pop('failed', False): wanted.add('failed')
        if p.pop('broken', False): wanted.add('broken')
        if p.pop('unfinished', False): wanted.update(('crashed', 'failed', 'broken'))
        if p.pop('all', False): wanted.update(('crashed', 'failed', 'broken', 'ok'))
        if not wanted:
            wanted = {'crashed'}

        if 'ok' in wanted and not (p.get('force') or p.get('f')):
            return {'return':1, 'error': 'removing the usable entries too (--all) needs --force'}

        r = self.classify_(ctx, arg1 = p.get('arg1'), tags = p.get('tags'), match = p.get('match'))
        if r['return']>0: return r

        removed = []
        skipped = {}

        for a in r['artifacts']:
            uid = a['cmeta_ref_parts']['artifact_uid']
            alias = a['cmeta_ref_parts'].get('artifact_alias', uid)
            info = r['states'][uid]

            if info['state'] == 'running':
                skipped[uid] = f'running ({info["why"]})'
                if con:
                    print (f'skipping {alias}: an attempt is running ({info["why"]})')
                continue

            if info['state'] not in wanted:
                continue

            rr = self.cm.access({'category': ctx['category'],
                                 'command': 'delete',
                                 'arg1': '*:' + uid,
                                 'force': True,
                                 'con': False})
            if rr['return']>0:
                skipped[uid] = rr.get('error', 'delete failed')
                if con:
                    print (f'could not remove {alias}: {rr.get("error")}')
                continue

            removed.append(uid)
            if con:
                print (f'removed {alias} ({info["state"]})')

        if con and not removed:
            print (f'nothing to remove (states: {", ".join(sorted(wanted))})')

        return {'return':0, 'removed': removed, 'skipped': skipped}

    ############################################################
    def delete(
        self,
        params: dict,  # cMeta parameters.
    ):
        """
            Args:
                params (dict): cMeta parameters.

            Returns:
                dict: Dictionary with 'return': 0.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        # p will be deep copied from params
        p = self._prepare_input_from_params(params, base = True)

        arg1 = p.get('arg1', '')
        if arg1 is None: arg1 = ''

        if ':' not in arg1:
            arg1 = 'local:' + arg1

        p['arg1'] = arg1

        return self.cm.access(p)
