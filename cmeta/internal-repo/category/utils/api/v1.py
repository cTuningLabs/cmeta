"""
cMeta misc utilities

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
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
            arg1 = input('Enter CID: ')

        if web and arg1.startswith('cmeta:///?'):
            arg1 = arg1[10:]

            from urllib.parse import unquote
            arg1 = unquote(arg1)

        if arg1 is None:
            arg1 = '*'

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
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """
        self.logger.debug("running utils.find_by_cid_smart")

        con = ctx['control'].get('con', False)

        if ask:
            arg1 = input('Enter complex CID: ')

        if web and arg1.startswith('cmeta:///?'):
            cid = arg1[10:]

            from urllib.parse import unquote
            cid = unquote(cid)
        elif cid is not None:
            cid = common._extract_category_artifact(cid) 
        elif arg1 is not None:
            cid = common._extract_category_artifact(arg1) 
        else:
            return {'return':1, 'error': 'CID is not specified'}

        if self.cm.debug:
            self.logger.debug(f"extracted_cid={cid}")

        if cid is None:
            return {'return':1, 'error':f'Could not extract CID from the input string (arg1)'}

        r = self.find_by_cid_(
              ctx,
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

                # Save back to the same file
                r = self.cm.utils.files.safe_write_file(cmeta_file, merged_data)
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

        start_time = time.time()

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

        elapsed_time = time.time() - start_time

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
            Create artifact with date

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

        from datetime import datetime
        yyyymmdd = datetime.now().strftime("%Y%m%d")

        p = self._prepare_input_from_params(params, base = True)

        # Check config if need to do something with a path, i.e. open it with some application
        r = self.cm.access({'category': self.cmeta['uses_categories']['config'],
                            'command': 'get',
                            'arg1': self.cm.cfg['default_config_name']})
        if r['return'] > 0: return r

        config_cmeta = r['config_cmeta']

        key = f'{category_alias}'.replace('.','_') + '_create_cmd'
        key2 = f'{category_alias}'.replace('.','_') + '_create_repo'

        # Parse cMeta obj
        arg1 = p.get('arg1')

        r = self.cm.utils.names.parse_cmeta_obj(arg1)
        if r['return'] > 0: return r

        arg1_obj_parts = r['obj_parts']

        alias = arg1_obj_parts.get('alias')
        
        if alias is None:
            if con:
                alias = input(f'Enter {category_alias} name: ')
                alias = alias.strip()

        if alias is None or alias == '':
            alias = yyyymmdd
        else:
            if not (len(alias) >= 8 and alias[:8].isdigit()):
                alias = yyyymmdd + '.' + alias

        arg1_obj_parts['alias'] = alias

        # Check target repo
        repo_alias = arg1_obj_parts.get('repo_alias')
        if repo_alias is None:
            repo_alias = config_cmeta.get(key2)
            if repo_alias is not None and repo_alias != '':
                arg1_obj_parts['repo_alias'] = repo_alias

        # Restore cMeta obj
        r = self.cm.utils.names.restore_cmeta_obj(arg1_obj_parts)
        if r['return'] > 0: return r

        p['category'] = from_category
        p['command'] = 'get'
        p['arg1'] = r['obj']
        p['con'] = False
        del(p['from_category'])

        # Create artifact
        r = self.cm.access(p)
        if r['return'] > 0: return r

        path = r['artifact']['path']

        if con:
            print (f'Path to {category_alias}s: {path}')
        
        cmd = config_cmeta.get(key)

        if cmd is not None and cmd != '':
            cmd = cmd.replace('{path}', path)
            if con:
                print (f'Executing: {cmd}')
            
            os.system(cmd)

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
