"""
СMeta core class and functions

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import json
import logging
import os
import sys
import time
import inspect

from typing import Dict, Any, List, Optional
from pathlib import Path

from . import config
from . import utils
from .repos import Repos
from .packages import Packages
from .version import __version__

control_params_desc = config.params_desc + config.params_command2_desc + config.params_command_desc + config.params_init_desc

class CMeta:
    """A common meta system to manage and reuse common artifacts and their automations."""
    
    ###################################################################################################
    def __init__(
        self,
        home: Optional[str] = None,  # Path to cMeta home directory.
        debug: Optional[bool] = None,  # If True, sets log_level to "DEBUG" (overrides log_level parameter).
        fail_on_error: Optional[bool] = None,  # If True, raise error instead of returning dictionary with error
        log_level: Optional[str] = None,  # Logging level as string (case-insensitive).
        log_file: Optional[str] = None,  # Path to log file. If provided and not empty, logs will be written to this file.
        log_format: Optional[str] = None,  # Logging format string.
        pause_if_error: Optional[bool] = None,  # If True, pause before exiting after errors.
        package_allow_install: Optional[bool] = True,  # If True, allow automatic Python package installation.
        package_timeout: Optional[float] = None,  # Default timeout for package installation and checks, in seconds.
        print_host_info: Optional[bool] = False,  # If True, print host system information during access calls.
    ):

        """
            Initialize CMeta with repositories

            Args:
                home (Optional[str]): Path to cMeta home directory.
                debug (Optional[bool]): If True, sets log_level to "DEBUG" (overrides log_level parameter).
                fail_on_error (Optional[bool]): If True, raise error instead of returning dictionary with error
                log_level (Optional[str]): Logging level as string (case-insensitive).
                log_file (Optional[str]): Path to log file. If provided and not empty, logs will be written to this file.
                log_format (Optional[str]): Logging format string.
                pause_if_error (Optional[bool]): If True, pause before exiting after errors.
                package_allow_install (Optional[bool]): If True, allow automatic Python package installation.
                package_timeout (Optional[float]): Default timeout for package installation and checks, in seconds.
                print_host_info (Optional[bool]): If True, print host system information during access calls.
            Returns:
                None: This is a constructor that initializes the CMeta instance.

            Raises:
                FileExistsError: If there's a race condition when creating the home directory.
                OSError: If there's an error creating the home directory due to permissions or other OS-level issues.
                PermissionError: If the process lacks permissions to create the home directory.
                Exception: For any other unexpected errors during directory creation or initialization.
        """

        ###################################################################################################
        # Initialize logging
        self.config = config
        self.cfg = self.config.cfg
        cfg = self.cfg

        self.__version__ = __version__

        r = config.check_init_vars_from_env()
        if r['return'] > 0: 
            raise Exception(f"cMeta init failed: {r['error']}")

        cmeta_init = r['init']

        # Setup logger and vars from environment if not explicitly set
        cmeta_init_forced = {}

        if home is not None: cmeta_init_forced['home'] = home
        if debug is not None: cmeta_init_forced['debug'] = debug
        if fail_on_error is not None: cmeta_init_forced['fail_on_error'] = fail_on_error
        if log_level is not None: cmeta_init_forced['log_level'] = log_level
        if log_file is not None: cmeta_init_forced['log_file'] = log_file
        if log_format is not None: cmeta_init_forced['log_format'] = log_format
        if pause_if_error is not None: cmeta_init_forced['pause_if_error'] = pause_if_error

        r = self.config.update_init_and_setup_logger(__name__, cmeta_init, cmeta_init_forced)
        if r['return'] > 0: 
            raise Exception(f"cMeta init failed: {r['error']}")

        self.logger = r['logger']
        init = r['init']

        self.debug = init['debug']
        self.fail_on_error = init['fail_on_error']
        self.pause_if_error = init.get('pause_if_error', False)

        self.logger.debug("Initializing CMeta class ...")

        self.home_path = Path(init['home'])
        self.repos_path = self.home_path / cfg["repos_dir"]
        self.repos_config_path = self.home_path / cfg["repos_config_filename"]
        self.index_path = self.home_path / cfg["index_dir"]
        
        self.path = os.path.dirname(__file__)

        paths_list = _list_paths(self)
        for log_path in paths_list:
            self.logger.info(log_path)

        self._error = utils.common._error
        self.check_params = utils.common.check_params

        self.module_cache = {}

        # Some debug functions
        self.j = utils.common.safe_print_json
        self.jj = utils.common.safe_print_json_with_enter
        self.jv = utils.common.print_module_vars
        self.js = utils.common.safe_print_json_to_str
        self.q = utils.files.quote_path
        self.qq = utils.files.quote_path2
        self.utils = utils


        self.print_host_info = print_host_info

        #################################################################################
        # Create directory if it doesn't exist (thread/process safe)
        for path in [self.home_path]: #, self.repos_path, self.index_path]:
            try:
                path.mkdir(parents=True, exist_ok=True)
            except FileExistsError:
                # Another process created it, that's fine
                pass
            except Exception as e:
                self.logger.error(f"Error creating home directory: {e}")
                raise
        
        #################################################################################
        # Initialize package manager
        self.packages = Packages(
            cfg=self.cfg,
            logger=self.logger,
            fail_on_error=self.fail_on_error,
            allow_install=package_allow_install,
            timeout=package_timeout,
            add_install_args=os.environ.get(cfg['env_var_pip_install_args']), 
        )

        #################################################################################
        # Initialize repositories manager
        self.repos = Repos(
            cfg=self.cfg,
            home_path=self.repos_path,
            index_path=self.index_path,
            repos_config_path=self.repos_config_path,
            logger=self.logger,
            fail_on_error=self.fail_on_error,
            match_version_func=self.packages.match_version
        )

    ###################################################################################################
    def error(
        self,
        error_msg,  # Error message text.
        return_code = 1,  # Numeric return code.
        exception = None,  # Exception object associated with the error.
        fail16 = False,  # If True, treat return code 16 as a fatal error.
        fail_on_error = None,  # If True, raise exceptions instead of returning error dictionaries.
        extra = {},
    ):
        """
            Create or raise a cMeta error using framework-level defaults.

            Args:
                error_msg: Error message text.
                return_code: Numeric return code.
                exception: Exception object associated with the error.
                fail16: If True, treat return code 16 as a fatal error.
                fail_on_error: If True, raise exceptions instead of returning error dictionaries.
                extra (dict): Additional fields to include in the returned error dictionary.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        if not fail_on_error: 
            fail_on_error = self.fail_on_error

        return utils.common._error(error_msg, return_code, exception, fail_on_error=fail_on_error, fail_on_16 = fail16, extra = extra)

    ###################################################################################################
    def catch_error(
        self,
        r,  # cMeta access return dict
        fail16 = False,  # If True, treat return code 16 as a fatal error.
    ):
        """
            Catches error and creates return dictionary or raise exception based on fail_on_error flag.

            Args:
                r: cMeta access return dict
                fail16: If True, treat return code 16 as a fatal error.
            Returns:
                dict: Dictionary with 'return' and 'error' keys.

            Raises:
                Exception: If fail_on_error is True and return_code != 16.

            Example:
                if self.cm.catch_error(r): return r
        """

        ret = r['return']

        if r.get('return',0)>0:
            rr = self._error(r.get('error'), ret, exception = None, fail_on_error = self.fail_on_error, fail_on_16 = fail16)

            r['error'] = rr['error']
        
        return ret != 0 and (ret !=16 or fail16)

    ###################################################################################################
    def catch_error_and_halt(
        self,
        r,  # cMeta return dictionary.
        fail16 = False,  # If True, treat return code 16 as a fatal error.
    ):
        """
            Raise or print an error and terminate execution when needed.

            Args:
                r (dict): cMeta return dictionary.
                fail16 (bool): If True, treat return code 16 as a fatal error.
            Returns:
                dict: Original input dictionary.

            Raises:
                Exception: Propagated runtime errors, if any.
        """
        if self.catch_error(r, fail16):
            self.halt(r)
        return r


    ############################################################
    def halt(
        self,
        r,  # output from CM function with "return" and "error"
    ):
        """
            If r['return']>0: print error and halt

            Args:
                r (dict): output from CM function with "return" and "error"
            Returns:
               (dict): r

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        import sys

        if r['return']>0:
            error_text = self.cfg['con_error_prefix'] + r['error'] + '!'

            sys.stderr.write('\n' + error_text)

        sys.exit(r['return'])

    ############################################################
    def dump(
        self,
        filename,  # File name or path string.
        meta,  # Metadata dictionary to persist.
        wait = False,  # If True, wait for interactive confirmation after writing data.
    ):
        """
            Write metadata to a file and optionally wait for user confirmation.

            Args:
                filename: File name or path string.
                meta: Metadata dictionary to persist.
                wait: If True, wait for interactive confirmation after writing data.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        r = utils.files.write_file(filename, meta)
        if self.catch_error(r): return r

        if wait:
            print ('')
            print (f'Data was dumped to "{filename}"')
            print ('')
            input ('Press Enter to continue:')

        return r



    ###################################################################################################
    def outdated(
        self,
        path, 
        meta
    ):
        """Print a warning when a category API version is outdated.

        Args:
            path: Path to the category API being loaded.
            meta (dict): Category metadata, optionally containing ``last_api_version``.

        Returns:
            dict: A successful cMeta return dictionary.
        """

        msg = f'WARNING: API version 1 is outdated in {path}.'

        last_api_ver = meta.get('last_api_version')
        if last_api_ver:
            msg += f' The last one is {last_api_ver}.'

        print ('*'*80)
        print (msg)

        return {'return':0}

    ###################################################################################################
    def access(
        self,
        request: Dict[str, Any],  # Dictionary containing the request data
    ) -> Dict[str, Any]:
        """
            Access common meta framework in a unified way

            Args:
                request (Dict[str, Any]): Dictionary containing the request data
            Returns:
                Dictionary with {"return": 0, ...} for success or {"return": >0, "error": "error text"} for errors

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        self_time_start = time.perf_counter()

        if self.print_host_info:
            utils.sys.get_min_host_info(only_memory=True, con=True, line=80)

        # Manual override of global self.debug and self.fail_on_error
        self_fail_on_error = self.fail_on_error
        self_debug = self.debug

        # Log where this call is coming from if debug
        if self_debug:
            self.logger.debug(60*'=')
            self.logger.debug(f'ACCESS({self.js(request, indent=2)})')

            stack = inspect.stack()
            if len(stack) > 1:
                caller_frame = stack[1]
                caller_filename = caller_frame.filename
                abs_path = os.path.abspath(caller_filename)
                self.logger.debug(f'ACCESS is from "{abs_path}"')

            r = utils.sys.get_min_host_info()
            if r['return'] == 0:
                self.logger.debug(r['string'])

        # Make shallow copy of top keys to avoid altering original input keys
        # It's relatively fast in comparison with deep copy 
        # particularly for nested calls with a large "ctx" ...
        params = request.copy()

        # Prepare context and origin if first run ...
        if 'ctx' not in params:
            params['ctx'] = {}
        ctx = params.get('ctx', {})

        cur_dir = os.getcwd()

        # If origin(al) call is not in the context, add it for further
        # reuse, debugging and reproducibility
        if 'origin' not in ctx:
            origin = {}

            # This helps deep scripts get original directory 
            # (useful for various automations)
            origin['pwd'] = cur_dir

            if '_cli' in params:
                origin['cli'] = params['_cli']
                del(params['_cli'])

            origin['params'] = request

            ctx['origin'] = origin

        inside_cli = 'cli' in ctx.get('origin',{})

        # Check nested call
        if 'nested_call' not in ctx:
            nested_call = 0
        else:
            nested_call = ctx['nested_call'] + 1

        self.logger.debug(f'ACCESS nested call: {nested_call}')
        ctx['nested_call'] = nested_call

        # Check and extract control params
        r = utils.check_params(params, control_params_desc, fail_on_error=self_fail_on_error)
        if self.catch_error(r): return r

        # remaining params are command params
        command_params = r['remaining_params']

        control_params = r['checked_params']

        saved_control = ctx.get('control')
        ctx['control'] = control_params

        # Continue processing request
        con = control_params.get('con', False)

        # Force con in control_params to simplify APIs
        control_params['con'] = con

        repro = control_params.get('repro', False)

        result = {'return':0}

        ###########################################################################################
        if repro:
            for x in ['repro_input_file', 'repro_input_file_rt', 'repro_output_file']:
                if os.path.isfile(self.cfg[x]):
                    r = utils.files.remove_files_and_dirs_in_path(self.cfg[x])
                    if self.catch_error(r): return r

            request_copy = request.copy()

            # Clean repro request to avoid overwriting reproducibility files
            x_cmd = request_copy.get('_cli', {}).get('cmd',{})
            if x_cmd:
                for x in ['r', 'repro']:
                    if x in request_copy:
                        del(request_copy[x])
                    for x1 in ['-', '--']:
                        x2 = x1 + x
                        if x2 in x_cmd:
                            x_cmd.remove(x2)

            r = utils.files.write_file(self.cfg['repro_input_file'], request_copy)
            if self.catch_error(r): return r

            ctx_repro = ctx.setdefault('repro', {})


        ###########################################################################################
        category_obj = control_params.get('category')

        # Check if runs for the first time (there is no repos.json and index)
        if 'verbose' not in control_params and config.is_on(os.environ.get(self.cfg['env_var_cmeta_verbose'])):
            control_params['verbose'] = True
        verbose = control_params.get('verbose', False)

        if 'control' not in ctx['origin']:
            ctx['origin']['control'] = control_params

        r = self.repos.init(con=con, verbose=verbose)
        if self.catch_error(r): return r

        if category_obj is None:
            if params.get('version', False) or params.get('V', False):
                from .version import __version__
                result['version'] = __version__

                if con:
                    print (self.cfg['name'] + f' version {__version__}')

                    print ('')
                    print (self.cfg['copyright'])

                if con:
                    print ('')

                    paths_list = _list_paths(self)
                    for log_path in paths_list:
                        print (log_path)

                # How this cMeta was installed decides how it is updated: `uv tool`,
                # uv or pip in an environment, from PyPI or from git, or a checkout
                install = utils.sys.cmeta_install_info()
                result['install'] = install

                if con:
                    print ('')
                    print (f'Installed as: {install["label"]}')
                    for c in install['update']:
                        print (f'Update with:  {c}')
                    if install.get('note'):
                        print (f'              ({install["note"]})')

                # Check latest version
                r = utils.net.access_api(url = self.cfg['default_ctuning_api'],
                                         params = {'command':'get-last-cmeta-version'},
                                         timeout = 3)

                if r['return'] == 0:
                    rr = r['response']
                    if rr['return'] == 0:
                        last_cmeta_version = rr['last_cmeta_version']
                        result['last_cmeta_version'] = last_cmeta_version

                        r = utils.common.compare_versions(last_cmeta_version, __version__)
                        if r['return'] == 0:
                            if r['comparison'] == '>':
                                result['requires_update'] = True
                                if con:
                                    print ('')
                                    print (f'WARNING: Your cMeta version ({__version__}) is outdated.')
                                    print (f'         Latest version: {last_cmeta_version}')
                                    for c in install['update'] or ['see docs/installation.md, "Updating cMeta"']:
                                        print (f'         Update with: {c}')
                            else:
                                if con:
                                    print ('')
                                    print (f'Your cMeta version is up-to-date!')
                else:
                    return self.error(f'Accessing latest version info failed: {r["error"]}')

            elif control_params.get('reindex', False):
                r = self.repos.reindex(con=con, verbose=verbose)
                if self.catch_error(r): return r

            else:
                return self.error('"category" is not defined')

        else:
            # Prepare to search for category record as artifact (category_name -> artifact_name, category_name = "category")!
            r = utils.names.parse_cmeta_obj(category_obj, key = "artifact", fail_on_error = self_fail_on_error)
            if self.catch_error(r): return r

            cmeta_ref_parts = r['obj_parts']
            cmeta_ref_parts['category_alias'] = 'category'
            cmeta_ref_parts['category_uid'] = 'dd9ea50e7f76467f'

            r = self.repos.find(cmeta_ref_parts)
            if self.catch_error(r, fail16=True): return r

            category_artifacts = r['artifacts']

            if len(category_artifacts) == 0 or len(category_artifacts)>1:
                if len(category_artifacts) == 0:
                    return self.error(f'category "{category_obj}" not found', 8)
                else:
                    err = f'Ambiguity for category "{category_obj}" - please specify the full name:'
                    for c in category_artifacts:
                        r = utils.names.restore_cmeta_obj(c['cmeta_ref_parts'], key='artifact', fail_on_error = self_fail_on_error)
                        if r['return']>0: return r
                        category_str = r['obj']
                        err += f"\n* {category_str} ({c['path']})"
                    return self.error(err, 8)


            # Prepare command
            command = control_params.get('command', None)

            if command is None:
                command = ''
            else:
                command = command.strip().lower().replace('-', '_')

            if command.endswith('_'):
                return self.error(f"command shouldn't end with _ ({command})")

            ctx['command'] = command

            # Unique category found - check meta and code
            category_artifact = category_artifacts[0]
            category_meta = category_artifact['cmeta']
            category_uid = category_artifact['cmeta_ref_parts']['artifact_uid']

            # Update context with some duplication for simplicity of further use ...
            ctx['category_artifact'] = category_artifact
            ctx['category_cmeta'] = category_meta
            ctx['category'] = category_artifact['cmeta_ref_parts']

            ###################################################################################################
            # Initialize main and base categories for API unless already in cache
            base_command = control_params.get('base', False)
            category_api_ver = control_params.get('api', None)

            category_api_module_ver = '1'
            base_category_api_module_ver = '1'

            str_category_api_ver = None if category_api_ver is None else str(category_api_ver)

            if base_command:
                if category_meta.get('skip_base_category_commands', False):
                    return self.error('this category doesn\'t use base commands')

                if str_category_api_ver is not None:
                    base_category_api_module_ver = str_category_api_ver
                elif 'base_category_last_api_version' in self.cfg:
                    base_category_api_module_ver = self.cfg['base_category_last_api_version']

            else:
                if category_api_ver is not None:
                    category_api_module_ver = str_category_api_ver
                elif 'last_api_version' in category_meta:
                    category_api_module_ver = str(category_meta['last_api_version'])

                if not category_meta.get('skip_base_category_commands', False):
                    if category_meta.get('base_category_default_api_versions', {}).get(category_api_module_ver) is not None:
                        base_category_api_module_ver = str(category_meta['base_category_default_api_versions'][category_api_module_ver])
                    elif category_meta.get('base_category_default_api_version') is not None:
                        base_category_api_module_ver = str(category_meta['base_category_default_api_version'])

            # Check min cMeta versions
            category_min_cmeta_version = category_meta.get('min_cmeta_version_api')

            if category_min_cmeta_version is None and category_api_module_ver is not None:
                category_min_cmeta_version = category_meta.get('min_cmeta_version',{}).get(str(category_api_module_ver))

            if category_min_cmeta_version is not None:
                from .version import __version__
                r = utils.common.compare_versions(category_min_cmeta_version, __version__)
                if self.catch_error(r): return r
                if r['comparison'] == '>':
                    return self.error(f'this category requires min cMeta version "{category_min_cmeta_version}" but "{__version__}" is installed')

            if repro: 
                ctx_repro['api'] = str(category_api_module_ver)

            # Prepare paths to APIs
            category_apis = []

            if not base_command and category_api_module_ver is not None:
                category_api_path = os.path.join(category_artifact['path'], 'api', f'v{category_api_module_ver}.py')

                if os.path.isfile(category_api_path):
                    category_apis.append({'path':category_api_path, 'suffix': category_uid, 'api_version': category_api_module_ver})
                elif category_api_ver is not None or category_api_module_ver != '1':
                    return self.error(f'couldn\'t find category API "{category_api_path}"')

            # Either base command or API file doesn't 
            if base_category_api_module_ver is not None and not category_meta.get('skip_base_category_commands', False):
                category_api_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f'category_api_v{base_category_api_module_ver}.py')
                if not os.path.isfile(category_api_path):
                    return self.error(f'couldn\'t find category API "{category_api_path}"')

                category_apis.append({'path':category_api_path, 'base':True, 'api_version': base_category_api_module_ver})

            # Load categories
            for category_api in category_apis:
                # category api path should be resolved by now
                suffix = category_api.get('suffix')

                r = utils.sys.load_module(category_api['path'], 
                                          self.module_cache, 
                                          fail_on_error = self_fail_on_error, 
                                          init_class = "Category", 
                                          cmeta = self, 
                                          suffix = suffix, 
                                          self_meta = category_meta,
                )
                if self.catch_error(r): return r

                category_api['code'] = r['cache']['initialized_class']
                category_api['code'].api_version = category_api['api_version']
                category_api['full_module_name'] = r['cache']['full_module_name']

            ###################################################################################################
            # If empty command, print help
            if command == '':
                if params.get('version', False) or params.get('V', False):
                    if con:
                        category_version = category_meta.get('version', None)
                        result['version'] = category_version
                        print (f'Category version: {category_version}')

                        category_copyright = category_meta.get('copyright', None)
                        result['copyright'] = category_copyright
                        print (f'Category copyright: {category_copyright}')

                        print ('')
                        from .version import __version__
                        result['cmeta_version'] = __version__

                        print (self.cfg['name'] + f' version: {__version__}')
                        print (self.cfg['name'] + ' copyright: ' + self.cfg['copyright'])

                else:

                    caller = params.get('_cli', {}).get('caller')
                    if caller is None:
                        caller = os.path.basename(sys.executable) + f" -m {__package__}"

                    if not con:
                        return self.error(f'"command" key is missing in the request {request}')

                    else:
                        if not control_params.get('help', False):
                            print(self.cfg['con_error_prefix'] + '<command> is missing after <category>!')
                            print('')

                        print(f'{caller} {category_obj} <command> --help | <flags>')

                        for category_api in category_apis:
                            names = []

                            category_api_code = category_api['code']

                            x1 = ''
                            x2 = ''
                            if category_api.get('base', False):
                                x1 = ' base (common)'
                                x2 = ' for all categories'

                            for name in sorted(dir(category_api_code)):
                                if callable(getattr(category_api_code, name)) and not name.startswith('_'):
                                    nname = name

                                    if name.endswith('___'):
                                        nname = name[:-3]
                                    elif name.endswith('__'):
                                        nname = name[:-2]
                                    elif name.endswith('_'):
                                        nname = name[:-1]

                                    r = utils.sys.find_func_definition(category_api_code, name)
                                    if self.catch_error(r): return r

                                    filename = r['filename']
                                    start_line = r['start_line']
                                    end_line = r['end_line']
                                    short_func_desc = r['short_func_desc']

                                    short_func_desc += f'    ({filename}:{start_line}-{end_line})'

                                    # Check aliases
                                    nname_aliases = []
                                    for where in [category_artifact['cmeta'], self.cfg]:
                                        command_aliases = where.get('command_aliases',{})
                                        for command_alias in command_aliases:
                                            real_command = command_aliases[command_alias]
                                            if real_command == nname:
                                                nname_aliases.append(command_alias)

                                    if len(nname_aliases)>0:
                                        nname += ' (' + '|'.join(nname_aliases) + ')'

                                    names.append((f'{nname}', short_func_desc))

                            if len(names)>0:
                                longest_name = max((len(item[0]) for item in names), default=0)

                                print ('')
                                print(f"Available{x1} commands{x2}:")

                                for name in names:
                                    print(f'   {name[0]:<{longest_name}}    {name[1]}')

            ###################################################################################################
            else:
                func = None
                command_func_name = None

                # Check command aliases:
                command_alias = command

                #   First in meta
                for where in [category_artifact['cmeta'], self.cfg]:
                    tmp_command_alias = where.get('command_aliases',{}).get(command)
                    if tmp_command_alias != None and tmp_command_alias != '':
                        command_alias = tmp_command_alias
                        break

                if self_debug:
                    self.logger.debug(f'Resolved command alias: {command_alias}')

                for category_api in category_apis:
                    category_api_code = category_api['code']

                    # Select which function to use (we check names with __ to differentiate from internal Python names if needed)
                    r = utils.sys.find_command_func(category_api_code, command_alias)
                    if self.catch_error(r): return r

                    func = r['func']

                    if func is not None:
                        command_func_name = r['func_name']
                        break

                if func is None:
                    x = command
                    if command_alias != command:
                        x += f' ({command_alias})'
                    # Shouldn't fail in debug since it's used to check multiple functions ...
                    return self.error(f'command "{x}" doesn\'t exist in category API "{category_api_path}"', 32, fail_on_error=False)

                if control_params.get('help', False):
                    r = utils.names.restore_cmeta_obj(cmeta_ref_parts, key='artifact', fail_on_error = self_fail_on_error)
                    if self.catch_error(r): return r
                    category_str = r['obj']

                    r = utils.sys.get_api_info(category_api_code, command_func_name, f'{category_str} {command}', control_params_desc, category_apis=category_apis)
                    if self.catch_error(r): return r

                    help_text = r['api_info']

                    if con:
                        print (help_text)

                    result['help'] = help_text

                else:
                    if self_debug:
                        r = utils.sys.find_func_definition(category_api_code, command_func_name)
                        if self.catch_error(r): return r

                        filename = r['filename']
                        start_line = r['start_line']
                        end_line = r['end_line']

                        self.logger.debug(f'Calling {command_func_name}() @ {filename}:{start_line}-{end_line}')
                        self.logger.debug(f'  with parameters {command_params} ...')

                    try:
                        command_params['ctx'] = ctx
                        if command_func_name.endswith('_') and not command_func_name.endswith('__'):
                            result = func(**command_params)
                        else:
                            result = func(command_params)

                    except TypeError as te:
                        if self_fail_on_error:
                            raise

                        ste = str(te)

#                        j = ste.find('unexpected ')
#                        if j>0:
#                            ste = ste[j:]

                        r = utils.names.restore_cmeta_obj(cmeta_ref_parts, key='artifact', fail_on_error = self_fail_on_error)
                        if self.catch_error(r): return r
                        category_str = r['obj']

                        extra_flags_help = category_meta.get('extra_flags_help', '')

                        err = f'API call "{category_str} {command}" failed - {ste}.\n\nRerun with {extra_flags_help}--help to view API usage and options'

#                        if '() got an unexpected keyword argument' in ste:
#                            r = utils.sys.get_api_info(category_api_code, command_func_name, f'{category_str} {command}', control_params_desc)
#                            if r['return'] > 0: return r
#
#                            err += '\n\nSee ' + r['api_info']

                        return self.error(err)

        # Get self timing
        self_time = time.perf_counter() - self_time_start
        ctx['last_self_time'] = self_time

        ctx['nested_call'] -= 1

        if saved_control:
            ctx['control'] = saved_control
        else:
            del(ctx['control'])

        # Timer for debugging
        if self_debug:
            self.logger.debug('')
            self.logger.debug(f'SELF TIME: {self_time:.3f} sec.')
            self.logger.debug('')

        # Save reproducibility info (similar to json_file but with fixed file)
        if repro:
            r = utils.files.write_file(self.cfg['repro_input_file_rt'], ctx_repro)
            if self.catch_error(r): return r

            r = utils.files.write_file(self.cfg['repro_output_file'], result)
            if self.catch_error(r): return r

        # Finalize call
        if control_params.get('json', False):
            print (60*'-')
            utils.common.safe_print_json(result)

            if result['return']>0:
                result['skip_print_error'] = True

        json_file = control_params.get('json_file')
        if json_file is not None and json_file!='':
            r = utils.files.write_file(json_file, result)
            if self.catch_error(r): return r

        if control_params.get('dump', False):
            cur_dir2 = os.getcwd()
            os.chdir(cur_dir)

            r = utils.files.write_file(self.cfg['dump_ctx_output_file'], ctx)
            if self.catch_error(r): return r

            os.chdir(cur_dir2)

        if control_params.get('pause_at_the_end', False):
            print ('')
            input ('Press Enter to finish the command!')

        return result

def _list_paths(
    cmeta,  # CMeta instance.
):
    """
        Generate a list of formatted path strings for CMeta configuration.

        Args:
            cmeta: CMeta instance.
        Returns:
            list: List of formatted path strings for logging/display.

        Raises:
            Exception: Propagated runtime errors, if any.
    """

    import sys

    paths_list = []

    paths_list.append(f"cMeta home path:           {cmeta.home_path}")
    paths_list.append(f"cMeta repositories path:   {cmeta.repos_path}")
    paths_list.append(f"cMeta repositories config: {cmeta.repos_config_path}")
    paths_list.append(f"cMeta index path:          {cmeta.index_path}")
    paths_list.append("")
    paths_list.append(f"cMeta python path:         {sys.executable}")
    paths_list.append(f"cMeta package path:        {cmeta.path}")

    return paths_list
