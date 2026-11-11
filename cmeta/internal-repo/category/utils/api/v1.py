"""
cMeta misc utilities

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import re
from cmeta.category import InitCategory

from cmeta.utils import names

# Aliased - this category has its own "common" module next to it
from cmeta.utils import common as utils_common

from . import common

class Category(InitCategory):
    """
    Various Utils
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

    def native_host_install_(self, ctx, arg1=None, apply=False):
        """Register a native messaging host declared by a cMeta artifact."""
        from . import native_host
        try:
            return native_host.install(self.cm, arg1, apply=apply)
        except Exception as exc:
            return self.cm.error(str(exc))

    def native_host_check_(self, ctx, arg1=None):
        """Check native messaging transport and the artifact's declared requests."""
        from . import native_host
        try:
            return native_host.check(self.cm, arg1)
        except Exception as exc:
            return self.cm.error(str(exc))

    def native_host_run_(self, ctx, arg1=None):
        """Serve one framed native message using cx's active cMeta home."""
        from . import native_host
        return native_host.serve(self.cm, arg1)

    ############################################################
    def test(
        self,
        params,  # Input dictionary used by this function.
    ):

        """
        test function.

        Args:
            params: Input dictionary used by this function.

        Returns:
            dict: Operation result.

        Raises:
            Exception: Propagated runtime errors, if any.
        """
        print ('Params:')
        self.cm.j(params)

        print (f'__name__ = {__name__}')
        print (f'__file__ = {__file__}')

        return {'return':0}

    ############################################################
    def uid_(
        self,
        ctx,  # cMeta context object.
        clipboard = True,
    ):
        """
            Generate a 16-character cMeta UID.

            Args:
                ctx (dict): cMeta context object.
                clipboard (bool): If True, copy the generated UID to the clipboard.

            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        self.logger.debug("running utils.uid")

        con = ctx['control'].get('con', False)

        uid = names.generate_cmeta_uid()

        if con:
            print (uid)

        if clipboard:
            self.copy_text_to_clipboard_(ctx, uid)

        return {'return':0, 'uid':uid}

    ############################################################
    def uuid_(
        self,
        ctx,  # cMeta context
        clipboard = True,
    ):
        """
            Generate a UUID4 string.

            Args:
                ctx (dict): cMeta context.
                clipboard (bool): If True, copy the generated UUID to the clipboard.

            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        import uuid

        self.logger.debug("running utils.uuid")

        con = ctx['control'].get('con', False)

        uuid = str(uuid.uuid4())

        if con:
            print (uuid)

        if clipboard:
            self.copy_text_to_clipboard_(ctx, uuid)

        return {'return':0, 'uuid':uuid}

    ############################################################
    def api_key_(
        self,
        ctx,  # cMeta context object.
        arg1 = 1,  # How many keys to generate.
        nbytes = 24,  # Random bytes per key (24 -> 192 bits, a 32-character string).
        config = 'cserver',  # Config artifact named in the ready-to-paste command.
        key = 'api_keys',  # Config key named in the ready-to-paste command.
        bare = False,  # Print the keys alone, for scripts.
        clipboard = False,  # Copy the keys to the clipboard.
    ):
        """
            Generate API keys for a cMeta config (for example the `api_keys` list of the `cserver` web app).

            A key is only a random string: the server compares what a request carries against the list in the
            config. These come from `secrets.token_urlsafe`, so they are safe to use as bearer tokens.

                cx utils api_key                     one key, with the line to paste
                cx utils api_key 3                   three keys, ready for a device each
                cx utils api_key --bare              the key alone, for a script
                cx utils api_key --nbytes=32         a longer key

            Args:
                ctx (dict): cMeta context object.
                arg1 (int): How many keys to generate.
                nbytes (int): Random bytes per key (24 -> 192 bits, a 32-character string).
                config (str): Config artifact named in the ready-to-paste command.
                key (str): Config key named in the ready-to-paste command.
                bare (bool): Print the keys alone, for scripts.
                clipboard (bool): Copy the keys to the clipboard.

            Returns:
                dict: Operation result with `api_keys` (a list) and `api_key` (the first one).
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        import secrets

        self.logger.debug("running utils.api_key")

        con = ctx['control'].get('con', False)

        try:
            count = max(1, int(arg1 or 1))
        except (TypeError, ValueError):
            return self.cm.error('the number of keys must be an integer')

        try:
            nbytes = int(nbytes or 24)
        except (TypeError, ValueError):
            return self.cm.error('nbytes must be an integer')
        if nbytes < 16:
            return self.cm.error('use at least 16 bytes - a shorter key is guessable')

        keys = [secrets.token_urlsafe(nbytes) for _ in range(count)]

        if con:
            if bare:
                for k in keys:
                    print (k)
            else:
                print ('')
                for k in keys:
                    print (k)
                print ('')
                print (f'cx config set {config} --meta.{key},=' + ','.join(keys))
                print ('')
                print ('The comma in "--meta.%s,=" is what makes it a list. Restart the server afterwards.' % key)
                print ('A key travels in the URL, so it reaches the access log and the shell history: treat it')
                print ('like a password and give one per device, so a single key can be replaced on its own.')
                print ('')

        if clipboard:
            self.copy_text_to_clipboard_(ctx, ','.join(keys))

        return {'return':0, 'api_keys':keys, 'api_key':keys[0]}

    ############################################################
    def hash_password_(
        self,
        ctx,  # cMeta context object.
        arg1 = '',  # Password to hash. Asked for without echo when omitted.
        config = 'cserver',  # Config artifact named in the ready-to-paste command.
        key = 'password_sha256',  # Config key named in the ready-to-paste command.
        bare = False,  # Print the digest alone, for scripts.
        clipboard = False,  # Copy the digest to the clipboard.
    ):
        """
            Hash a password for a cMeta config, so the plain text is not stored on disk.

            The shipped use is the shared password of the `cserver` web app, which accepts either
            `password` (plain) or `password_sha256` (this digest, which takes precedence):

                cx utils hash_password                     # asks without echo, then confirms
                cx utils hash_password "my passphrase"     # left in the shell history - avoid
                cx utils hash_password --bare               # the digest alone

            Args:
                ctx (dict): cMeta context object.
                arg1 (str): Password to hash. Asked for without echo when omitted.
                config (str): Config artifact named in the ready-to-paste command.
                key (str): Config key named in the ready-to-paste command.
                bare (bool): Print the digest alone, for scripts ("quiet" is a reserved cMeta flag).
                clipboard (bool): Copy the digest to the clipboard.

            Returns:
                dict: Operation result with `sha256`.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        import getpass
        import hashlib

        self.logger.debug("running utils.hash_password")

        con = ctx['control'].get('con', False)

        password = arg1 if arg1 is not None else ''
        from_cli = password != ''

        if not from_cli:
            try:
                password = getpass.getpass('Password: ')
                again = getpass.getpass('Repeat: ')
            except (EOFError, KeyboardInterrupt):
                return self.cm.error('no password was given')

            if password != again:
                return self.cm.error('the two passwords do not match')

        if password == '':
            return self.cm.error('the password is empty')

        digest = hashlib.sha256(password.encode('utf-8')).hexdigest()

        if con:
            if bare:
                print (digest)
            else:
                print ('')
                print (digest)
                print ('')
                print (f'cx config set {config} --meta.{key}={digest}')
                print ('')
                if from_cli:
                    print ('The password was typed on the command line, so it is in your shell history.')
                    print ('Run the command without it next time and it is asked for without echo.')
                    print ('')

        if clipboard:
            self.copy_text_to_clipboard_(ctx, digest)

        return {'return':0, 'sha256':digest}

    ############################################################
    def ai_context_(
        self,
        ctx: dict,  # cMeta context.
        names = None,  # Template aliases (comma-separated), artifact aliases or cRefs (";"-separated) to resolve; none: the list.
        purpose: str = 'ai_uses',  # The key under `template` in an artifact's meta.
    ):
        """
            The AI contexts declared in the meta of artifacts (template: <purpose>: {alias, title, sort}),
            sorted, from one index query - and with `names`, their full cRefs by the rule of
            `cx <category> add <artifact> -ai=<names>` (run-ai's --context and the pages use it).
            Returns:
                dict: {'return', 'entries': [{'alias', 'title', 'sort', 'cref', 'path'}], 'crefs': [...] (with names)}
        """
        from cmeta.category_api_v1 import ai_context_entries, resolve_ai_context

        con = ctx.get('control', {}).get('con', False)
        r = ai_context_entries(self.cm, purpose)
        if r['return']>0: return r
        out = {'return':0, 'entries': r['entries']}
        if names is not None and names is not True and names != '':
            r = resolve_ai_context(self.cm, names, r['entries'])
            if r['return']>0: return r
            out['crefs'] = r['crefs']
            if con:
                for c in r['crefs']:
                    print (c)
        elif con:
            if not out['entries']:
                print ('No AI context template is declared (template: ' + purpose + ': {alias, title, sort} in an artifact\'s meta).')
            width = max([len(e['alias']) for e in out['entries']] + [1])
            for e in out['entries']:
                print (f"{e['alias'].ljust(width)}  {e['cref']}  {e['title']}")
        return out

    ############################################################
    def view_cref_(
        self,
        ctx,  # Execution context dictionary with category, command, and control data.
        arg1 = '',  # The cRef: <category>::<artifact> (alias, UID or alias,UID), {{{...}}}/<file> too; "." or nothing = the artifact of the current directory.
        url = '',  # The cMeta server a browser reaches: http://host:port (default: cserver_url of the config "default", else http://127.0.0.1:<port of the cserver config, 8004>).
        browser = '',  # The browser: a name Python's webbrowser knows (chrome, firefox, safari), or the command or path of one ("%s" = the address); default: browser of the config "default", else the system's.
        print_only: bool = False,  # Only print the address: open nothing.
        copy: bool = False,  # Copy the address to the clipboard too.
    ):
        """
        Open the page of an artifact (/cref/<cRef>) on this machine's cMeta server in a browser, started detached -
        on Windows, macOS and Linux alike (2026-11-10).

            cx utils view_cref work::20261104.add x                     the page of that artifact
            cx utils view_cref "{{{work::my work,0123456789abcdef}}}/README.md"   a file of it, in the reader
            cx utils view_cref .                                        the artifact of the current directory
            cx utils view_cref . --print_only                           the address alone
            cx config set default --meta.cserver_url=http://my-laptop:8004        where the server is (the hub's name
                                                                                   when its pages are read from other
                                                                                   machines); http://127.0.0.1:8004 by default
            cx config set default --meta.browser=firefox                 a browser that is not the system's default
        """
        import shlex
        import subprocess
        import sys
        import urllib.parse
        import webbrowser

        con = ctx.get('control', {}).get('con', False)
        spec = str(arg1 or '').strip()

        # the artifact: "." (or nothing) = the one of the current directory, as "cx ." finds it; else the cRef as
        # given, the braces of a text taken off, a path after them kept
        path = ''
        if spec in ('', '.'):
            r = utils_common.detect_cid_in_the_current_directory(self.cm)
            if r['return'] > 0:
                return r
            if r.get('artifact_name'):
                cref = '%s::%s' % (r['category_obj'], r['artifact_name'])
            elif r.get('category_alias'):
                cref = 'category::%s' % r['category_alias']          # a category's folder: the category's own page
            else:
                return {'return': 1, 'error': 'no artifact in the current directory (a repository, but no category folder in it)'}
        else:
            if spec.startswith('{{{'):
                end = spec.find('}}}')
                if end < 0:
                    return {'return': 1, 'error': 'the braces of %r do not close' % spec}
                cref, path = spec[3:end].strip(), spec[end + 3:].strip()
            else:
                cref = spec
            if '::' not in cref:
                return {'return': 1, 'error': '%r is not a cRef: <category>::<artifact> (or "." for the artifact of this folder)' % spec}
        # the artifact as alias,UID when it is here (a page that follows a rename); as named when it is not (the page says so)
        cat, _sep, art = cref.partition('::')
        r = self.cm.access({'category': cat.strip(), 'command': 'find', 'arg1': art.strip(), 'con': False})
        found = (r.get('artifacts') or []) if r.get('return', 1) == 0 else []
        if len(found) == 1:
            p = found[0].get('cmeta_ref_parts') or {}
            if p.get('artifact_alias') and p.get('artifact_uid'):
                cref = '%s::%s,%s' % (p.get('category_alias') or cat.strip(), p['artifact_alias'], p['artifact_uid'])

        # where the server is
        base = str(url or '').strip()
        cfg = {}
        if not base or not browser:
            rc = self.cm.access({'category': 'config,cc6bfe174be847ed', 'command': 'read', 'arg1': 'default',
                                 'con': False})
            cfg = (rc.get('config_cmeta') or {}) if rc.get('return', 1) == 0 else {}
        if not base:
            base = str(cfg.get('cserver_url') or '').strip()
        if not base:
            rs = self.cm.access({'category': 'config,cc6bfe174be847ed', 'command': 'read', 'arg1': 'cserver',
                                 'con': False})
            port = (((rs.get('config_cmeta') or {}) if rs.get('return', 1) == 0 else {}).get('param') or {}).get('port') or 8004
            base = 'http://127.0.0.1:%s' % port
        base = base.rstrip('/')
        if base.lower().endswith('/cref'):
            base = base[:-5]
        if not base.lower().startswith(('http://', 'https://')):
            base = 'http://' + base
        address = base + '/cref/' + urllib.parse.quote(cref + path, safe=':,()-_./@+=')

        if con:
            print(address)
        if copy:
            utils_common.copy_text_to_clipboard(address, do_not_fail=True)
        out = {'return': 0, 'url': address, 'cref': cref, 'opened': False}
        if print_only:
            return out

        # the browser, detached: the system's default (webbrowser: os.startfile on Windows, open on macOS, xdg-open or
        # the one found on Linux - none waits for the browser), a name webbrowser knows, or a command of one's own
        which = str(browser or cfg.get('browser') or '').strip()
        known = None
        if which and re.fullmatch(r'[A-Za-z0-9_.-]+', which):
            try:
                known = webbrowser.get(which)                        # chrome, firefox, safari ... as webbrowser names them
            except webbrowser.Error:
                known = None
        if not which:
            ok = webbrowser.open(address, new=2)
        elif known is not None:
            ok = known.open(address, new=2)
        else:
            # a command or a path of one's own: started here, detached - never through webbrowser, whose GenericBrowser
            # waits for the command to end
            if True:
                words = shlex.split(which, posix=(sys.platform != 'win32'))
                if not words:
                    return {'return': 1, 'error': 'browser: a name or a command is expected'}
                argv = [w.replace('%s', address) for w in words] if any('%s' in w for w in words) else words + [address]
                flags = {'creationflags': getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)} \
                    if sys.platform == 'win32' else {'start_new_session': True}
                try:
                    subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     close_fds=True, **flags)
                except OSError as e:
                    return {'return': 1, 'error': 'the browser %s did not start: %s' % (argv[0], e)}
                ok = True
        if not ok:
            return {'return': 1, 'error': 'no browser opened %s (cx config set default --meta.browser=<name or command> names one)' % address}
        out['opened'] = True
        return out

    ############################################################
    def find_by_cid_(
        self,
        ctx,  # cMeta context.
        arg1 = None,  # Standard CID.
        tags = None,  # Comma-separated string or iterable of tags to match ("-tag" excludes).
        far = False,  # If True, open FAR manager in found artifact path.
        web = False,  # If True, decode web-style `cmeta:///?` CID input.
        ask = False,  # If True, ask for CID in console.
        skip_non_indexed = False,  # If True, skip non-indexed repositories.
        match = None,  # Value for match.
        match_empty_version = False,  # Value for match empty version.
        match_empty_values = False,  # Match when queried values or keys are empty.
        all_tags = None,  # Value for all tags.
        smart_match = None,  # Comma-separated values - keep artifacts holding any of them under any meta key.
        search_text = None,  # Space-separated texts - keep artifacts whose files contain any of them.
        search_files = None,  # Comma-separated globs naming those files (default "*info*.md"; "**" recurses).
        search_file_names = None,  # Space-separated strings that must ALL appear in a file name (recursive).
        after_date = None,  # Keep artifacts dated on or after this (ISO or YYYY[MM[DD[-HHMM]]]).
        before_date = None,  # Keep artifacts dated on or before this (same formats).
    ):
        """
            Find artifacts by standard CID

            Args:
                ctx (dict): cMeta context.
                arg1 (str): Standard CID.
                tags (str): Comma-separated string or iterable of tags to match ("-tag" excludes).
                far (bool): If True, open FAR manager in found artifact path.
                web (bool): If True, decode web-style `cmeta:///?` CID input.
                ask (bool): If True, ask for CID in console.
                skip_non_indexed (bool): If True, skip non-indexed repositories.
                match (dict): Value for match.
                match_empty_version (bool): Value for match empty version.
                match_empty_values (bool): Match when queried values or keys are empty.
                all_tags (str): Value for all tags.
                smart_match (str | list): Comma-separated values - keep artifacts holding
                                          any of them under any meta key.
                search_text (str | list): Space-separated texts - keep artifacts whose
                                          files contain any of them.
                search_files (str | list): Comma-separated globs naming those files
                                           (default "*info*.md"; "**" recurses).
                search_file_names (str | list): Space-separated strings that must ALL
                                               appear in a file name. Always recursive,
                                               and replaces search_files when given.
                after_date (str): Keep artifacts dated on or after this. Full ISO, or
                                  YYYY / YYYYMM / YYYYMMDD / YYYYMMDD-HHMM and the
                                  dashed variants. The date is taken from the artifact
                                  name when it starts with one, else from
                                  last_update_timestamp, else from creation_timestamp.
                before_date (str): Keep artifacts dated on or before this, same formats.

            Returns:
                dict: Operation result. When search_text or search_file_names was
                      given, "files" holds the full paths of every matching file
                      and those are printed instead of the artifact directories.
            Raises:
                Exception: Propagated runtime errors, if any.
        """
        self.logger.debug("running utils.find_by_cid")

        con = ctx['control'].get('con', False)

        if ask:
            r = self.cm.utils.common.ask('Enter CID: ', how='the CID as an argument instead of --ask')
            if r['return'] > 0: return r
            arg1 = r['answer']

        if web and arg1.startswith('cmeta:///?'):
            arg1 = arg1[10:]

            from urllib.parse import unquote
            arg1 = unquote(arg1)

        if arg1 is None:
            arg1 = '*'

        # a {{{cRef}}} as `cx info` prints it (and `cx utils cref` takes it)
        if isinstance(arg1, str) and arg1.strip().startswith('{{{') and arg1.strip().endswith('}}}'):
            arg1 = arg1.strip()[3:-3].strip()

        if '::' not in arg1:
            arg1 = '*::' + arg1

        r = names.parse_cmeta_ref(arg1, fail_on_error = self.fail_on_error)
        if r['return']>0: return r

        artifact_ref_parts = r['ref_parts']

        if self.cm.debug:
            self.logger.debug(f"artifact_ref_parts={artifact_ref_parts}")

        r = self.cm.repos.find(
              artifact_ref_parts,
              tags = tags,
              skip_non_indexed = skip_non_indexed,
              match = match,
              match_empty_version = match_empty_version,
              match_empty_values = match_empty_values,
              all_tags = all_tags,
           )
        if r['return']>0: return r

        artifacts = r['artifacts']

        # Prune further: keep only artifacts whose meta holds any of these
        # values under any key. "find" narrows by CID, tags and named keys -
        # this catches the case where the key is not known in advance.
        if smart_match is not None:
            r2 = utils_common.normalize_tags(smart_match, fail_on_error = self.fail_on_error)
            if r2['return']>0: return r2

            smart_match_values = r2['tags']

            artifacts = [a for a in artifacts
                         if common._matches_any_value(a.get('cmeta', {}), smart_match_values)]

            # Pruning everything away is an empty result, not a failure -
            # the same 16 that "find" itself answers with
            if len(artifacts) == 0:
                return {'return':16, 'error':f'artifacts matching "{smart_match}" not found'}

            r['artifacts'] = artifacts

        # Prune further still: keep only artifacts with a file matching
        # "search_files" that contains any of the "search_text" words. Without
        # search_text no file is opened at all - the whole stage is skipped.
        #
        # The matching files themselves are collected into "files": having
        # searched inside files, the files are the answer, so a caller can
        # open them directly instead of re-deriving them from the artifacts.
        # Prune by date before touching the file system: this only reads the
        # artifact name and meta already in hand, so it makes the file stage
        # below cheaper rather than more expensive.
        if (after_date is not None and str(after_date).strip() != '') or \
           (before_date is not None and str(before_date).strip() != ''):

            after = common._parse_date_value(after_date)
            if after is None and after_date is not None and str(after_date).strip() != '':
                return {'return':1, 'error':f'could not read after_date "{after_date}"'}

            before = common._parse_date_value(before_date)
            if before is None and before_date is not None and str(before_date).strip() != '':
                return {'return':1, 'error':f'could not read before_date "{before_date}"'}

            dated_artifacts = []

            for a in artifacts:
                when = common._artifact_date(a['path'], a.get('cmeta', {}))

                # No date to judge by means it cannot be shown to be in range
                if when is None:
                    continue

                if after is not None and when < after:
                    continue

                if before is not None and when > before:
                    continue

                dated_artifacts.append(a)

            if len(dated_artifacts) == 0:
                return {'return':16, 'error':'no artifacts in that date range'}

            artifacts = dated_artifacts
            r['artifacts'] = artifacts

        files = []

        def _split_values(value):
            if value is None:
                return []
            values = value if isinstance(value, list) else str(value).split()
            return [v for v in values if str(v).strip() != '']

        search_text_values = _split_values(search_text)
        search_file_names_values = _split_values(search_file_names)

        if len(search_text_values) > 0 or len(search_file_names_values) > 0:
            # Which files are candidates. Naming parts of a file name is itself
            # a name-based selector, so it replaces the glob patterns and always
            # recurses; otherwise the "search_files" globs pick the candidates.
            if len(search_file_names_values) > 0:
                def _candidates(path):
                    return common._files_matching_name_parts(path, search_file_names_values)
            else:
                if search_files is None or str(search_files).strip() == '':
                    search_files = common.DEFAULT_SEARCH_FILES

                r2 = utils_common.normalize_tags(search_files, fail_on_error = self.fail_on_error)
                if r2['return']>0: return r2

                search_files_patterns = r2['tags']

                def _candidates(path):
                    return common._files_matching_patterns(path, search_files_patterns)

            matched_artifacts = []

            for a in artifacts:
                a_files = _candidates(a['path'])

                # The text filter narrows whatever the name filter selected
                if len(search_text_values) > 0:
                    a_files = common._files_containing_any_text(a_files, search_text_values)

                if len(a_files) > 0:
                    matched_artifacts.append(a)
                    files.extend(a_files)

            if len(matched_artifacts) == 0:
                what = []
                if len(search_text_values) > 0:
                    what.append(f'"{search_text}"')
                if len(search_file_names_values) > 0:
                    what.append(f'file names "{search_file_names}"')

                return {'return':16, 'error':f'artifacts with {" and ".join(what)} not found'}

            artifacts = matched_artifacts

            r['artifacts'] = artifacts
            r['files'] = files

        # if no artifact found, "find" function will return error
        # we need to check >1 for ambiguity
        #
        # Searching inside files answers with the files that matched; without
        # a file search the artifact directories are still the answer
        if con:
            for line in (files if len(files) > 0 else
                         [a['path'] for a in artifacts]):
                print (line)

        path = artifacts[0]['path']

        if far:
            os.system(f'start far {path}')

        return r

    ############################################################
    def smart_find_by_cid_(
        self,
        ctx,  # cMeta context.
        arg1 = None,  # CID that can be wrapped with some text.
        far = False,  # If True, open FAR in found artifact.
        web = False,  # If True, remove cmeta:///? from CID (web request).
        ask = False,  # If True, ask for CID in console.
        cid = None,  # Direct CID to use.
        tags = None,  # Comma-separated string or iterable of tags to match ("-tag" excludes).
        match = None,  # Value for match.
        match_empty_version = False,  # Value for match empty version.
        match_empty_values = False,  # Match when queried values or keys are empty.
        all_tags = None,  # Value for all tags.
        smart_match = None,  # Comma-separated values - keep artifacts holding any of them under any meta key.
        search_text = None,  # Space-separated texts - keep artifacts whose files contain any of them.
        search_files = None,  # Comma-separated globs naming those files (default "*info*.md"; "**" recurses).
        search_file_names = None,  # Space-separated strings that must ALL appear in a file name (recursive).
        after_date = None,  # Keep artifacts dated on or after this (ISO or YYYY[MM[DD[-HHMM]]]).
        before_date = None,  # Keep artifacts dated on or before this (same formats).
    ):
        """
            Find artifacts by wrapped CID

            The text may also hold a {{{cRef}}}, a "/<path>" right after the cRef or the CID
            ({{{cRef}}}/!AI, <category>::<alias>,<UID>/!AI/memory) or a path to an existing
            file or folder. A path inside the artifact is printed instead of the artifact,
            a plain path as it is.

            Args:
                ctx (dict): cMeta context.
                arg1 (str): CID that can be wrapped with some text.
                far (bool): If True, open FAR in found artifact.
                web (bool): If True, remove cmeta:///? from CID (web request).
                ask (bool): If True, ask for CID in console.
                cid (str): Direct CID to use.
                tags (str): Comma-separated string or iterable of tags to match ("-tag" excludes).
                match (dict): Value for match.
                match_empty_version (bool): Value for match empty version.
                match_empty_values (bool): Match when queried values or keys are empty.
                all_tags (str): Value for all tags.
                smart_match (str | list): Comma-separated values - keep artifacts holding
                                          any of them under any meta key.
                search_text (str | list): Space-separated texts - keep artifacts whose
                                          files contain any of them.
                search_files (str | list): Comma-separated globs naming those files
                                           (default "*info*.md"; "**" recurses).
                search_file_names (str | list): Space-separated strings that must ALL
                                               appear in a file name. Always recursive,
                                               and replaces search_files when given.
                after_date (str): Keep artifacts dated on or after this. Full ISO, or
                                  YYYY / YYYYMM / YYYYMMDD / YYYYMMDD-HHMM and the
                                  dashed variants. The date is taken from the artifact
                                  name when it starts with one, else from
                                  last_update_timestamp, else from creation_timestamp.
                before_date (str): Keep artifacts dated on or before this, same formats.

            Returns:
                dict: Operation result. With a path in the text, "path" holds the place
                      found and "paths" every one (one per artifact found); a plain path
                      comes back with no artifacts and no filter applied.
            Raises:
                Exception: Propagated runtime errors, if any.
        """
        self.logger.debug("running utils.find_by_cid_smart")

        con = ctx['control'].get('con', False)

        if ask:
            r = self.cm.utils.common.ask('Enter complex CID: ', how='the CID as an argument instead of --ask')
            if r['return'] > 0: return r
            arg1 = r['answer']

        sub_path = None

        if web and arg1.startswith('cmeta:///?'):
            cid = arg1[10:]

            from urllib.parse import unquote
            cid = unquote(cid)
        elif cid is not None or arg1 is not None:
            # A {{{cRef}}} or a CID with the /<path> after it, or a plain path
            found = common._extract_cid_and_path(cid if cid is not None else arg1)

            if found is not None and 'path' in found:
                path = found['path']

                if con:
                    print (path)

                if far:
                    os.system(f'start "" far "{path}"')

                return {'return':0, 'path':path, 'paths':[path], 'artifacts':[]}

            if found is not None and found.get('missing_path') is not None:
                return {'return':16, 'error':f'path "{found["missing_path"]}" not found'}

            cid = found['cid'] if found is not None else None
            sub_path = found['sub_path'] if found is not None else None
        else:
            return {'return':1, 'error': 'CID is not specified'}

        if self.cm.debug:
            self.logger.debug(f"extracted_cid={cid} sub_path={sub_path}")

        if cid is None:
            return {'return':1, 'error':f'Could not extract CID from the input string (arg1)'}

        # A path inside the artifact is printed instead of the artifact itself,
        # so the artifacts are found without printing them
        find_ctx = ctx
        if sub_path is not None and con:
            find_ctx = dict(ctx)
            find_ctx['control'] = dict(ctx['control'], con = False)

        r = self.find_by_cid_(
              find_ctx,
              cid,
              tags = tags,
              match = match,
              match_empty_version = match_empty_version,
              match_empty_values = match_empty_values,
              all_tags = all_tags,
              smart_match = smart_match,
              search_text = search_text,
              search_files = search_files,
              search_file_names = search_file_names,
              after_date = after_date,
              before_date = before_date,
           )
        if r['return']>0: return r

        artifacts = r['artifacts']

        path = artifacts[0]['path']

        if sub_path is not None:
            # The files of a file search stay the answer; otherwise the place
            # inside each artifact that has it
            paths = list(r.get('files', []))
            if len(paths) == 0:
                for a in artifacts:
                    p = common._longest_existing_path(sub_path, a['path'])
                    if p is not None:
                        paths.append(p)

            if len(paths) == 0:
                shown = sub_path.split()[0].rstrip(common.PATH_END_CHARS + '.:')
                return {'return':16, 'error':f'"{shown}" not found in {path}'}

            if con:
                for p in paths:
                    print (p)

            path = paths[0]
            r['path'] = path
            r['paths'] = paths

            if far:
                os.system(f'start "" far "{path}"')

            return r

        if far:
            os.system(f'start far {path}')

        return r

    ############################################################
    def _detect_in_directory(
        self,
        arg1,  # Directory to inspect. If None, use the current directory.
        command,  # Calling command name, for debug logging.
    ):
        """
            Shared detection behind detect_category and detect_repo.

            Normalizes the directory and runs the same detection as
            `cx . <command>`. Being outside any plugged repository is reported
            as "nothing detected" (`detected` is None), not as an error - only
            a bad directory is an error.

            Args:
                arg1 (str): Directory to inspect. If None, use the current directory.
                command (str): Calling command name, for debug logging.

            Returns:
                dict: Operation result with the normalized `path`, the raw
                      `detected` dictionary (or None) and any `detect_error`.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        self.logger.debug(f"running utils.{command}")

        if arg1 is None:
            path = os.getcwd()
        else:
            path = arg1

        path = os.path.normpath(os.path.abspath(path))

        if not os.path.isdir(path):
            return {'return':1, 'error':f'directory not found: {path}'}

        r = self.cm.utils.common.detect_cid_in_the_current_directory(
                self.cm, path = path, debug = self.cm.debug, logger = self.logger)

        if r['return']>0:
            # Outside any plugged repository - not detected rather than broken
            self.logger.debug(f"utils.{command}: {r.get('error','')}")

            return {'return':0, 'path':path, 'detected':None,
                    'detect_error': r.get('error')}

        return {'return':0, 'path':path, 'detected':r, 'detect_error':None}

    ############################################################
    def detect_category_(
        self,
        ctx,  # cMeta context.
        arg1 = None,  # Directory to inspect. If None, use the current directory.
        fail_if_not_found = False,  # If True, return an error when nothing is detected.
    ):
        """
            Detect the cMeta category of the current (or a given) directory

            Uses the same detection as `cx . <command>`: locate the plugged
            repository that contains the directory, then report the category
            (and the artifact, when standing inside one).

            Prints the category as `alias,UID`, or as just the alias when the
            UID is not known - such as when standing in the category directory
            itself rather than inside one of its artifacts. Prints nothing when
            no category can be detected.

            Detecting nothing is not an error: the command returns 0 with
            `category` set to None, so callers can fall back to a wider search.
            Pass `fail_if_not_found` to turn it into an error instead.

            Args:
                ctx (dict): cMeta context.
                arg1 (str): Directory to inspect. If None, use the current directory.
                fail_if_not_found (bool): If True, return an error when nothing is detected.

            Returns:
                dict: Operation result with `category` (str or None),
                      `category_alias`, `category_uid`, `artifact_name`,
                      `artifact_repo_name` and the inspected `path`.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        con = ctx['control'].get('con', False)

        r = self._detect_in_directory(arg1, 'detect_category')
        if r['return']>0: return r

        path = r['path']
        detected = r['detected']

        result = {'return':0,
                  'path': path,
                  'category': None,
                  'category_alias': None,
                  'category_uid': None,
                  'artifact_name': None,
                  'artifact_repo_name': None}

        if detected is None:
            if fail_if_not_found:
                return {'return':16, 'error':f'no cMeta category detected in {path}'}

            result['detect_error'] = r['detect_error']

            return result

        result['category'] = detected.get('category_obj')
        result['category_alias'] = detected.get('category_alias')
        result['category_uid'] = detected.get('category_uid')
        result['artifact_name'] = detected.get('artifact_name')
        result['artifact_repo_name'] = detected.get('artifact_repo_name')

        if result['category'] is None and fail_if_not_found:
            return {'return':16, 'error':f'no cMeta category detected in {path}'}

        if con and result['category'] is not None:
            print (result['category'])

        return result

    ############################################################
    def detect_repo_(
        self,
        ctx,  # cMeta context.
        arg1 = None,  # Directory to inspect. If None, use the current directory.
        fail_if_not_found = False,  # If True, return an error when nothing is detected.
    ):
        """
            Detect the cMeta repository of the current (or a given) directory

            The counterpart of `detect_category`, using the same detection as
            `cx . <command>`: find which plugged repository contains the
            directory.

            Prints the repository as `alias,UID`, or as just the alias or UID
            when only one of them is known. Prints nothing when the directory
            is outside every plugged repository.

            Detecting nothing is not an error: the command returns 0 with
            `repo` set to None, so callers can fall back to a wider search.
            Pass `fail_if_not_found` to turn it into an error instead.

            Args:
                ctx (dict): cMeta context.
                arg1 (str): Directory to inspect. If None, use the current directory.
                fail_if_not_found (bool): If True, return an error when nothing is detected.

            Returns:
                dict: Operation result with `repo` (str or None), `repo_alias`,
                      `repo_uid`, `artifact_path` (the path relative to the
                      repository root) and the inspected `path`.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        con = ctx['control'].get('con', False)

        r = self._detect_in_directory(arg1, 'detect_repo')
        if r['return']>0: return r

        path = r['path']
        detected = r['detected']

        result = {'return':0,
                  'path': path,
                  'repo': None,
                  'repo_alias': None,
                  'repo_uid': None,
                  'artifact_path': None}

        if detected is None:
            if fail_if_not_found:
                return {'return':16, 'error':f'no cMeta repository detected in {path}'}

            result['detect_error'] = r['detect_error']

            return result

        result['repo'] = detected.get('artifact_repo_name')
        result['repo_alias'] = detected.get('artifact_repo_alias')
        result['repo_uid'] = detected.get('artifact_repo_uid')
        result['artifact_path'] = detected.get('artifact_path')

        if result['repo'] is None and fail_if_not_found:
            return {'return':16, 'error':f'no cMeta repository detected in {path}'}

        if con and result['repo'] is not None:
            print (result['repo'])

        return result

    ############################################################
    def copy_text_to_clipboard_(
        self,
        ctx,  # cMeta context object.
        arg1 = '',  # Text to copy to clipboard.
        add_quotes = False,  # Add quotes to the text if True.
        do_not_fail = True,  # Do not fail on error if True.
    ):
        """
            Copy text to clipboard

            Args:
                ctx (dict): cMeta context object.
                arg1 (str): Text to copy to clipboard.
                add_quotes (bool): Add quotes to the text if True.
                do_not_fail (bool): Do not fail on error if True.

            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        return self.cm.utils.common.copy_text_to_clipboard(arg1, add_quotes)

    ############################################################
    def copy_date_to_clipboard_(
        self,
        ctx,  # cMeta context object.
        do_not_fail = True,  # Do not fail on error if True.
    ):
        """
            Copy text to clipboard

            Args:
                ctx (dict): cMeta context object.
                arg1 (str): Text to copy to clipboard.
                add_quotes (bool): Add quotes to the text if True.
                do_not_fail (bool): Do not fail on error if True.

            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        from datetime import datetime

        arg1 = datetime.now().strftime("%Y%m%d") + '.'

        return self.cm.utils.common.copy_text_to_clipboard(arg1)

    ############################################################
    def copy_date_time_to_clipboard_(
        self,
        ctx,  # cMeta context object.
        do_not_fail = True,  # Do not fail on error if True.
    ):
        """
            Copy text to clipboard

            Args:
                ctx (dict): cMeta context object.
                arg1 (str): Text to copy to clipboard.
                add_quotes (bool): Add quotes to the text if True.
                do_not_fail (bool): Do not fail on error if True.

            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        from datetime import datetime

        arg1 = datetime.now().strftime("%Y%m%d-%H%M%S") + '.'

        return self.cm.utils.common.copy_text_to_clipboard(arg1)

    ############################################################
    def copy_date_time_iso_to_clipboard_(
        self,
        ctx,  # cMeta context object.
        do_not_fail = True,  # Do not fail on error if True.
    ):
        """
            Copy text to clipboard

            Args:
                ctx (dict): cMeta context object.
                arg1 (str): Text to copy to clipboard.
                add_quotes (bool): Add quotes to the text if True.
                do_not_fail (bool): Do not fail on error if True.

            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        from datetime import datetime

        arg1 = datetime.now().isoformat().replace('-','').replace(':','').replace('T','-').replace('.','-') + '.'

        return self.cm.utils.common.copy_text_to_clipboard(arg1)

    ############################################################
    def json2yaml_(
        self,
        ctx,  # cMeta context.
        arg1,  # Input JSON file.
        arg2 = None,  # Output YAML file (if None, use {input file without ext}.yaml).
        force = False,  # If True and output file exists, overwrite it.
        f = False,  # If True and output file exists, overwrite it.
        sort_keys = False,  # Sort keys in output if True.
    ):
        """
            Convert JSON file to YAML file

            Args:
                ctx (dict): cMeta context.
                arg1 (str): Input JSON file.
                arg2 (str): Output YAML file (if None, use {input file without ext}.yaml).
                force (bool): If True and output file exists, overwrite it.
                f (bool): If True and output file exists, overwrite it.
                sort_keys (bool): Sort keys in output if True.

            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        self.logger.debug("running utils json2yaml")

        con = ctx['control'].get('con', False)

        r = self.cm.utils.files.safe_read_file(arg1)
        if r['return'] > 0: return r

        data = r['data']

        if arg2 is None:
            arg2 = f"{os.path.splitext(arg1)[0]}.yaml"

        if os.path.isfile(arg2) and not (force or f):
            return {'return':1, 'error':f'Output file already exists (use --force or --f option to overwrite): {arg2}'} 

        r = self.cm.utils.files.safe_write_file(arg2, data, sort_keys=sort_keys)
        if r['return'] > 0: return r

        return {'return':0}


    ############################################################
    def yaml2json_(
        self,
        ctx,  # cMeta context.
        arg1,  # Input YAML file.
        arg2 = None,  # Output JSON file (if None, use {input file without ext}.json).
        force = False,  # If True and output file exists, overwrite it.
        f = False,  # If True and output file exists, overwrite it.
        sort_keys = False,  # Sort keys in output if True.
    ):
        """
            Convert YAML file to JSON file

            Args:
                ctx (dict): cMeta context.
                arg1 (str): Input YAML file.
                arg2 (str): Output JSON file (if None, use {input file without ext}.json).
                force (bool): If True and output file exists, overwrite it.
                f (bool): If True and output file exists, overwrite it.
                sort_keys (bool): Sort keys in output if True.

            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        self.logger.debug("running utils yaml2json")

        con = ctx['control'].get('con', False)

        r = self.cm.utils.files.safe_read_file(arg1)
        if r['return'] > 0: return r

        data = r['data']

        if arg2 is None:
            arg2 = f"{os.path.splitext(arg1)[0]}.json"

        if os.path.isfile(arg2) and not (force or f):
            return {'return':1, 'error':f'Output file already exists (use --force or --f option to overwrite): {arg2}'} 

        r = self.cm.utils.files.safe_write_file(arg2, data, sort_keys=sort_keys)
        if r['return'] > 0: return r

        return {'return':0}


    ############################################################
    def pkl2json(
        self,
        params,  # Input parameters dictionary.
    ):
        """
            @self.pickle2json_

            Args:
                params: Input parameters dictionary.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        return self.pickle2json_(**params)


    ############################################################
    def pickle2json_(
        self,
        ctx,  # cMeta context.
        arg1,  # Pickle file.
        arg2 = None,  # JSON file (if not specified, use base of pickle file with .json).
        sort_keys = False,  # Sort keys in output if True.
    ):
        """
            Convert pickle file to JSON file

            Args:
                ctx (dict): cMeta context.
                arg1 (str): Pickle file.
                arg2 (str): JSON file (if not specified, use base of pickle file with .json).
                sort_keys (bool): Sort keys in output if True.

            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        import os
        import pickle
        import json

        con = ctx['control'].get('con', False)

        # Check if pickle file exists
        if not os.path.isfile(arg1):
            return {'return':1, 'error':f'Pickle file not found: {arg1}'}

        # Set default json filename if not provided
        if arg2 is None:
            base = os.path.splitext(arg1)[0]
            arg2 = f"{base}.json"

        # Load pickle file
        try:
            with open(arg1, 'rb') as f:
                data = pickle.load(f)
        except Exception as e:
            return {'return':1, 'error':f'Failed to load pickle file: {e}'}

        # Save to json file
        try:
            with open(arg2, 'w') as f:
                json.dump(data, f, sort_keys=sort_keys, indent=2)
                f.write('\n')
        except Exception as e:
            return {'return':1, 'error':f'Failed to save JSON file: {e}'}

        if con:
            print (f'Successfully converted {arg1} to {arg2}')

        return {'return':0, 'json_file': arg2}

    ############################################################
    def json2pickle_(
        self,
        ctx,  # cMeta context.
        arg1,  # JSON file.
        arg2 = None,  # Pickle file (if not specified, use base of json file with .pkl).
    ):
        """
            Convert JSON file to pickle file

            Args:
                ctx (dict): cMeta context.
                arg1 (str): JSON file.
                arg2 (str): Pickle file (if not specified, use base of json file with .pkl).

            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        import os
        import pickle
        import json

        con = ctx['control'].get('con', False)

        # Check if json file exists
        if not os.path.isfile(arg1):
            return {'return':1, 'error':f'JSON file not found: {arg1}'}

        # Set default pickle filename if not provided
        if arg2 is None:
            base = os.path.splitext(arg1)[0]
            arg2 = f"{base}.pkl"

        # Load json file
        try:
            with open(arg1, 'r') as f:
                data = json.load(f)
        except Exception as e:
            return {'return':1, 'error':f'Failed to load JSON file: {e}'}

        # Save to pickle file
        try:
            with open(arg2, 'wb') as f:
                pickle.dump(data, f)
        except Exception as e:
            return {'return':1, 'error':f'Failed to save pickle file: {e}'}

        if con:
            print (f'Successfully converted {arg1} to {arg2}')

        return {'return':0, 'pickle_file': arg2}

    ############################################################
    def utf8sig_to_utf8_(
        self,
        ctx,  # cMeta context.
        arg1,  # Input file (UTF-8 with BOM).
        arg2 = None,  # Output file (if None, overwrites input file and creates .bak backup).
    ):
        """
            Convert UTF-8 with BOM (utf-8-sig) file to standard UTF-8

            Args:
                ctx (dict): cMeta context.
                arg1 (str): Input file (UTF-8 with BOM).
                arg2 (str): Output file (if None, overwrites input file and creates .bak backup).

            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        import os
        import shutil

        con = ctx['control'].get('con', False)

        # Check if input file exists
        if not os.path.isfile(arg1):
            return {'return':1, 'error':f'Input file not found: {arg1}'}

        # Read file with utf-8-sig encoding (strips BOM automatically)
        try:
            with open(arg1, 'r', encoding='utf-8-sig') as f:
                content = f.read()
        except Exception as e:
            return {'return':1, 'error':f'Failed to read file: {e}'}

        # Determine output file
        if arg2 is None:
            # Create backup of original file
            backup_file = f"{arg1}.bak"
            try:
                shutil.copy2(arg1, backup_file)
                if con:
                    print(f'Created backup: {backup_file}')
            except Exception as e:
                return {'return':1, 'error':f'Failed to create backup: {e}'}
            arg2 = arg1

        # Write file with standard utf-8 encoding (without BOM)
        try:
            with open(arg2, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)
        except Exception as e:
            return {'return':1, 'error':f'Failed to write file: {e}'}

        if con:
            print(f'Successfully converted {arg1} to UTF-8 (without BOM)')
            if arg2 != arg1:
                print(f'Output saved to: {arg2}')

        return {'return':0, 'output_file': arg2}


    ############################################################
    def convert_old_entries_(
        self,
        ctx,  # cMeta context.
        arg1 = '.',  # Path to search for entries to convert.
        meta = {},  # Merge this meta with existing _cmeta files.
    ):
        """
            Convert legacy CK/CM/CMX entries in a path (arg1) by merging _cmeta.json or _cmeta.yaml with meta

            Args:
                ctx (dict): cMeta context.
                arg1 (str): Path to search for entries to convert.
                meta (dict): Merge this meta with existing _cmeta files.

            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        import os

        con = ctx['control'].get('con', False)

        # Check if path exists
        if not os.path.exists(arg1):
            return {'return':1, 'error':f'Path not found: {arg1}'}

        converted_count = 0
        error_count = 0
        errors = []

        # Recursively walk through all subdirectories
        for root, dirs, files in os.walk(arg1):
            # Look for _cmeta.json or _cmeta.yaml
            cmeta_file = None
            if '_cmeta.json' in files:
                cmeta_file = os.path.join(root, '_cmeta.json')
            elif '_cmeta.yaml' in files:
                cmeta_file = os.path.join(root, '_cmeta.yaml')

            if cmeta_file:
                if con:
                    print(f'Processing: {cmeta_file}')

                # Load existing meta file
                r = self.cm.utils.files.safe_read_file(cmeta_file)
                if r['return'] > 0:
                    error_msg = f"Failed to read {cmeta_file}: {r.get('error', 'Unknown error')}"
                    errors.append(error_msg)
                    error_count += 1
                    if con:
                        print(f'  ERROR: {error_msg}')
                    continue

                existing_data = r['data']

                # Merge with provided meta (meta takes precedence)
                merged_data = {**existing_data, **meta}

                # Save back to the same file (a YAML file keeps its text: only the merged keys are rewritten)
                r = self.cm.utils.files.safe_write_file(cmeta_file, merged_data, preserve=True)
                if r['return'] > 0:
                    error_msg = f"Failed to write {cmeta_file}: {r.get('error', 'Unknown error')}"
                    errors.append(error_msg)
                    error_count += 1
                    if con:
                        print(f'  ERROR: {error_msg}')
                    continue

                converted_count += 1
                if con:
                    print(f'  Successfully converted')
            
            else:
                # Check for legacy _cm.yaml or _cm.json files
                cm_yaml_file = os.path.join(root, '_cm.yaml') if '_cm.yaml' in files else None
                cm_json_file = os.path.join(root, '_cm.json') if '_cm.json' in files else None
                
                if cm_yaml_file or cm_json_file:
                    if con:
                        print(f'Processing legacy files in: {root}')
                    
                    merged_data = {}
                    
                    # First, try to read _cm.yaml
                    if cm_yaml_file:
                        if con:
                            print(f'  Reading: {cm_yaml_file}')
                        r = self.cm.utils.files.safe_read_file(cm_yaml_file)
                        if r['return'] > 0:
                            error_msg = f"Failed to read {cm_yaml_file}: {r.get('error', 'Unknown error')}"
                            errors.append(error_msg)
                            error_count += 1
                            if con:
                                print(f'  ERROR: {error_msg}')
                            continue
                        merged_data = r['data']
                    
                    # Then, try to read and merge _cm.json
                    if cm_json_file:
                        if con:
                            print(f'  Reading: {cm_json_file}')
                        r = self.cm.utils.files.safe_read_file(cm_json_file)
                        if r['return'] > 0:
                            error_msg = f"Failed to read {cm_json_file}: {r.get('error', 'Unknown error')}"
                            errors.append(error_msg)
                            error_count += 1
                            if con:
                                print(f'  ERROR: {error_msg}')
                            continue
                        merged_data = {**merged_data, **r['data']}
                    
                    # Finally, merge with provided meta (meta takes precedence)
                    merged_data = {**merged_data, **meta}

                    if 'artifact' not in merged_data and 'uid' in merged_data:
                        merged_data['artifact'] = merged_data['uid']

                    # Save to _cmeta.json
                    output_file = os.path.join(root, '_cmeta.json')
                    if con:
                        print(f'  Writing: {output_file}')
                    
                    r = self.cm.utils.files.safe_write_file(output_file, merged_data)
                    if r['return'] > 0:
                        error_msg = f"Failed to write {output_file}: {r.get('error', 'Unknown error')}"
                        errors.append(error_msg)
                        error_count += 1
                        if con:
                            print(f'  ERROR: {error_msg}')
                        continue
                    
                    converted_count += 1
                    if con:
                        print(f'  Successfully converted legacy files to _cmeta.json')

        if con:
            print(f'\nConversion complete:')
            print(f'  Files converted: {converted_count}')
            print(f'  Errors: {error_count}')

        result = {
            'return': 0 if error_count == 0 else 1,
            'converted_count': converted_count,
            'error_count': error_count
        }

        if errors:
            result['errors'] = errors

        return result

    ############################################################
    def artifacts_(
        self,
        ctx,  # Execution context dictionary with category, command, and control data.
        arg1 = None,  # First positional argument from command input.
        arg2 = None,  # Second positional argument from command input.
        skip_categories = None,  # Input parameter used by this function.
        func = None,  # Input parameter used by this function.
        func_params = {},  # Input parameter used by this function.
    ):
        """
            Analyze all artifacts for all categories

            arg1: categories
            arg2: artifacts
            top_num: number of top artifacts to show in rankings (default: 30)
            slow: if False (default), use cached results when artifact hasn't changed; if True, always perform deep analysis

            @base.find_

            Args:
                ctx: Execution context dictionary with category, command, and control data.
                arg1: First positional argument from command input.
                arg2: Second positional argument from command input.
                skip_categories: Input parameter used by this function.
                func: Input parameter used by this function.
                func_params: Input parameter used by this function.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        import time
        from datetime import datetime

        start_time = time.monotonic()

        con = ctx.get('control',{}).get('con', False)

        if skip_categories is None:
            skip_categories = ['repo', 'log', 'result', 'cache']

        # First, find all categories
        p = {'category': self.cmeta['uses_categories']['category'],
             'command':'find',
             'arg1': arg1}     
        
        r = self.cm.access(p)
        if r['return']>0: return r

        categories = r.get('artifacts', [])
        
        if con:
            print (f'Found {len(categories)} categories')
            print ('')

        all_artifacts = []
        num = 0

        # Process artifacts for each category
        for category in categories:
            category_cmeta = category['cmeta']
            category_cmeta_ref_parts = category['cmeta_ref_parts']
            
            category_alias = category_cmeta_ref_parts.get('artifact_alias')
            category_uid = category_cmeta_ref_parts['artifact_uid']

            if category_alias in skip_categories:
                continue

            if con:
                print ('-'*50)
                print (f'Processing category: {category_alias},{category_uid}')
                print ('')

            p = {'category':category_uid,
                 'command': 'find',
                 'arg1': arg2}
            
            r = self.cm.access(p)
            if r['return']==0:

                artifacts = r.get('artifacts', [])
                if len(artifacts)>0:
                    all_artifacts.extend(artifacts)

                    for artifact in artifacts:
                        num += 1
                        path = artifact['path']

                        if os.path.isdir(path):

                            mtime = os.path.getmtime(path)
                            modified_dt = datetime.fromtimestamp(mtime)

                            if con:
                                print ('='*80)
                                print (f' Artifact:      {num}')
                                print (f' Path:          {path}')
                                print (f' Last modified: {modified_dt}')


                            if func is not None:
                                r = func(artifact, num, func_params)
                                if r['return']>0: return r

                                add = r.get('add_to_artifact', {})
                                if len(add)>0:
                                    artifact['add'] = add 

                    if con and num > 0:
                        print ('')

        elapsed_time = time.monotonic() - start_time

        if con:
            print ('*'*80)
            print (f'Total artifacts: {num}')
            print (f'Elasped time:    {elapsed_time:.1f} seconds')

        return {'return':0, 'artifacts': all_artifacts, 'elapsed_time': elapsed_time}


    ############################################################
    def create_artifact_with_date(
        self,
        params,  # Input parameters dictionary.
    ):
        """
            Create an artifact with the date in front of its alias: the create that the dated categories
            (work, note, journal, experiment, research and others) called until 0.38.8, kept for the categories
            of repositories written then, whose `create` still calls it with `from_category`. Since 0.38.9 it is
            the base `get` of that category with `dt` (the alias dated by _alias_with_date: today's date in front
            of an alias that starts with none, the date alone for no alias, nothing added to a dated alias), and
            answers as before (the artifact read, `created`). The key `<category>_create_repo` of the default
            config is read by every create now; `<category>_create_cmd` is no longer read.

            @base.create_

            Args:
                params: Input parameters dictionary.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        from_category = params['from_category']

        category_alias = from_category['artifact_alias']

        self.logger.debug(f"From category: {category_alias}")

        con = params['ctx']['control'].get('con', False)

        p = self._prepare_input_from_params(params, base = True)

        p['category'] = from_category
        p['command'] = 'get'
        p['con'] = False
        del(p['from_category'])

        if p.get('dt') in (None, False, ''):
            p['dt'] = True

        # Create artifact
        r = self.cm.access(p)
        if r['return'] > 0: return r

        if con:
            print (f'Path to {category_alias}s: {r["artifact"]["path"]}')
            # what -ai, --connect and --ct did to the _desc.yaml files (the create above ran without printing)
            for line in r.get('desc_changes') or []:
                print (line)

        return r



    ############################################################
    def access_ctuning_server_(
        self,
        ctx,  # Execution context dictionary with category, command, and control data.
        query = {},  # Input parameter used by this function.
        headers = {},  # Input parameter used by this function.
        timeout = 30,  # Timeout value in seconds.
        url = None,  # Input parameter used by this function.
        api_key = None,  # Input parameter used by this function.
        files = {},  # Input parameter used by this function.
    ):
        """
            Access cTuning server

            Args:
                ctx: Execution context dictionary with category, command, and control data.
                query: Input parameter used by this function.
                headers: Input parameter used by this function.
                timeout: Timeout value in seconds.
                url: Input parameter used by this function.
                api_key: Input parameter used by this function.
                files: Input parameter used by this function.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        import copy

        con = ctx['control'].get('con', False)

        # Check config if need to do something with a path, i.e. open it with some application
        r = self.cm.access({'category': self.cmeta['uses_categories']['config'],
                            'command': 'get',
                            'arg1': 'ctuning_server'})
        if r['return'] > 0: return r

        config_cmeta = r['config_cmeta']

        if url is None or url == '':
            url = config_cmeta.get('url')
            if url is None or url == '':
                url = self.cm.cfg['default_ctuning_api']

        if api_key is None or api_key == '':
            api_key = config_cmeta.get('api_key')
        if api_key is not None and api_key != '':
            headers = copy.deepcopy(headers)
            headers['x-api-key'] = api_key

        if len(files)>0:
            r = self.cm.utils.files.files_encode(files)
            if r['return']>0: return r

            query['files_base64'] = r['files_base64']

        if con:
            print (f'Sending request to {url} ...')

        r = self.cm.utils.net.access_api(url, query, headers, timeout)
        if r['return']>0: return r

        if con:
            print ('')
            import json
            print (json.dumps(r, indent=2))

        return r

    ############################################################
    def x(
        self,
        params,  # Input parameters dictionary.
    ):
        """
            @self.access_ctuning_server_

            Args:
                params: Input parameters dictionary.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """
        return self.access_ctuning_server_(**params)

    ############################################################
    def test_public_server(
        self,
        params,  # Input parameters dictionary.
    ):
        """
            @self.access_ctuning_server_

            Args:
                params: Input parameters dictionary.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        tmp_params = params.copy()

        if 'url' not in tmp_params:
            tmp_params['url'] = self.cm.cfg['default_ctuning_api']

        if 'query' not in tmp_params:
           tmp_params['query'] = {'command':'test-api'}

        return self.access_ctuning_server_(**tmp_params)

    ############################################################
    def select_artifact(
        self,
        params,  # Input parameters dictionary.
    ):
        """
            Args:
                params: Input parameters dictionary.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        from . import common

        return common.select_artifact_(self, **params)

    ############################################################
    def get_datetime_(
        self,
        ctx,  # Execution context dictionary with category, command, and control data.
    ):
        """
            Args:
                ctx: Execution context dictionary with category, command, and control data.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        from datetime import datetime, timezone

        con = ctx['control'].get('con', False)

        # UTC time WITH timezone (+00:00)
        utc_with_tz = datetime.now(timezone.utc).isoformat()

        # UTC time WITHOUT timezone (naive datetime)
        utc_without_tz = datetime.utcnow().isoformat()

        # Local time with timezone
        local_with_tz = datetime.now().astimezone().isoformat()

        if con:
            print("UTC ISO with timezone :", utc_with_tz)
            print("UTC ISO without tz   :", utc_without_tz)
            print("Local ISO with tz    :", local_with_tz)


        return {'return':0}
