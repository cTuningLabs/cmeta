"""
СMeta core class and functions

cMeta author and developer: (C) 2025 Grigori Fursin

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
    def __init__(self, 
                 home: Optional[str] = None,
                 debug: Optional[bool] = None,
                 fail_on_error: Optional[bool] = None,
                 log_level: Optional[str] = None,
                 log_file: Optional[str] = None,
                 log_format: Optional[str] = None,
                 pause_if_error: Optional[bool] = None,
                 package_allow_install: Optional[bool] = True,
                 package_timeout: Optional[float] = None,
                 print_host_info: Optional[bool] = False,
    ):

        """Initialize CMeta with repositories
        
        Args:
            home_path: Path to cmeta-repos.json config file. If None, will search in:
                              1. CMETA_HOME environment variable. If None or "", will search in:
                              2. $HOME/CMETA directory
            debug: If True, sets log_level to "DEBUG" (overrides log_level parameter).
                  If False, logging behavior depends on log_level parameter.
            fail_on_error: If True, raise error instead of returning dictionary with error
            log_level: Logging level as string (case-insensitive). 
                      Accepted values: "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
                      If None or empty string, logging is disabled.
            log_file: Path to log file. If provided and not empty, logs will be written to this file.
                     If None or empty string, logs will be written to console.
                         
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

        self.category_cache = {}

        # Some debug functions
        self.j = utils.common.safe_print_json
        self.js = utils.common.safe_print_json_to_str
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
        )


    ############################################################
    def halt(self, r):
        """
        If r['return']>0: print error and halt

        Args:
           r (dict): output from CM function with "return" and "error"

        Returns:
           (dict): r
        """

        import sys

        if r['return']>0:
            error_text = self.cfg['con_error_prefix'] + r['error'] + '!'

            sys.stderr.write('\n' + error_text)

        sys.exit(r['return'])

    ###################################################################################################
    def access(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Access common meta framework in a unified way
        
        Args:
            request: Dictionary containing the request data
            
        Returns:
            Dictionary with {"return": 0, ...} for success or {"return": >0, "error": "error text"} for errors
        """

        if self.print_host_info:
            utils.sys.get_min_host_info(only_memory=True, con=True)

        # Log where this call is coming from if debug
        if self.debug:
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
        # particularly for nested calls with a large "state" ...
        params = request.copy()

        # Prepare state and origin if first run ...
        if 'state' not in params:
            params['state'] = {}
        state = params.get('state', {})

        # If origin(al) call is not in the state, add it for further
        # reuse, debugging and reproducibility
        if 'origin' not in state:
            origin = {}

            if self.debug:
                origin['pwd'] = os.getcwd()

            if '_cli' in params:
                origin['cli'] = params['_cli']
                del(params['_cli'])

            origin['params'] = request

            state['origin'] = origin

        inside_cli = 'cli' in state.get('origin',{})

        # Check nested call
        if 'nested_call' not in state:
            nested_call = 0
        else:
            nested_call = state['nested_call'] + 1

        self.logger.debug(f'ACCESS nested call: {nested_call}')
        state['nested_call'] = nested_call

        # Check and extract control params
        r = utils.check_params(params, control_params_desc, fail_on_error=self.fail_on_error)
        if r['return'] > 0: return r

        # remaining params are command params
        command_params = r['remaining_params']

        control_params = r['checked_params']
        state['control'] = control_params

        # Continue processing request
        con = control_params.get('con', False)

        # Force con in control_params to simplify APIs
        control_params['con'] = con

        result = {'return':0}

        category_obj = control_params.get('category')

        # Check if runs for the first time (there is no repos.json and index)
        if 'verbose' not in control_params and config.is_on(os.environ.get(self.cfg['env_var_cmeta_verbose'])):
            control_params['verbose'] = True
        verbose = control_params.get('verbose', False)

        r = self.repos.init(con=con, verbose=verbose)
        if r['return'] >0: return r

        if category_obj is None:
            if control_params.get('version', False):
                from .version import __version__
                result['version'] = __version__

                if con:
                    print (self.cfg['name'] + f' version {__version__}')

                if con:
                    print ('')

                    paths_list = _list_paths(self)
                    for log_path in paths_list:
                        print (log_path)

                        
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
                                    print (f'         Update via: pip install -U cmeta')
                            else:
                                if con:
                                    print ('')
                                    print (f'Your cMeta version is up-to-date!')
                else:
                    return self._error(f'Accessing latest version info failed: {r["error"]}', 1, None, self.fail_on_error)

            elif control_params.get('reindex', False):
                r = self.repos.reindex(con=con, verbose=verbose)
                if r['return']>0: return r

            else:
                return self._error('"category" is not defined', 1, None, self.fail_on_error)

        else:
            # Prepare to search for category record as artifact (category_name -> artifact_name, category_name = "category")!
            r = utils.names.parse_cmeta_obj(category_obj, key = "artifact", fail_on_error = self.fail_on_error)
            if r['return'] >0: return r

            cmeta_ref_parts = r['obj_parts']
            cmeta_ref_parts['category_alias'] = 'category'
            cmeta_ref_parts['category_uid'] = 'dd9ea50e7f76467f'

            r = self.repos.find(cmeta_ref_parts)
            if r['return']>0: return r

            category_artifacts = r['artifacts']

            if len(category_artifacts) == 0 or len(category_artifacts)>1:
                if len(category_artifacts) == 0:
                    return self._error(f'category "{category_obj}" not found', 8, None, self.fail_on_error)
                else:
                    err = f'Ambiguity for category "{category_obj}" - please specify the full name:'
                    for c in category_artifacts:
                        r = utils.names.restore_cmeta_obj(c['cmeta_ref_parts'], key='artifact', fail_on_error = self.fail_on_error)
                        if r['return']>0: return r
                        category_str = r['obj']
                        err += f"\n* {category_str} ({c['path']})"
                    return self._error(err, 8, None, self.fail_on_error)


            # Prepare command
            command = control_params.get('command', None)

            if command is None:
                command = ''
            else:
                command = command.strip().lower().replace('-', '_')

            if command.endswith('_'):
                return {'return':1, 'error': f"command shouldn't end with _ ({command})"}

            state['command'] = command

            # Unique category found - check meta and code
            category_artifact = category_artifacts[0]
            category_meta = category_artifact['cmeta']
            category_uid = category_artifact['cmeta_ref_parts']['artifact_uid']

            # Update state with some duplication for simplicity of further use ...
            state['category_artifact'] = category_artifact
            state['category'] = category_artifact['cmeta_ref_parts']

            ###################################################################################################
            # Initialize main and base categories for API unless already in cache
            base_command = control_params.get('base', False)
            category_api_ver = control_params.get('api', None)

            category_api_module_ver = '1'
            base_category_api_module_ver = '1'

            str_category_api_ver = None if category_api_ver is None else str(category_api_ver)

            if base_command:
                if category_meta.get('skip_base_category_commands', False):
                    return {'return':1, 'error':'this category doesn\'t use base commands'}

                if category_api_ver is not None and str_category_api_ver != '0':
                    base_category_api_module_ver = str_category_api_ver
                elif inside_cli or str_category_api_ver == '0':
                    base_category_api_module_ver = str(self.cfg['base_category_last_api_version'])
            else:
                if category_api_ver is not None and str_category_api_ver != '0':
                    category_api_module_ver = str_category_api_ver
                elif inside_cli or str_category_api_ver == '0':
                    if category_meta.get('last_api_version') is not None:
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
                if r['return']>0: return r
                if r['comparison'] == '>':
                    return {'return':1, 'error': f'this category requires min cMeta version "{category_min_cmeta_version}" but "{__version__}" is installed'}


            # Prepare paths to APIs
            category_apis = []

            if not base_command and category_api_module_ver is not None:
                category_api_path = os.path.join(category_artifact['path'], 'api', f'v{category_api_module_ver}.py')

                if os.path.isfile(category_api_path):
                    category_apis.append({'path':category_api_path, 'suffix': category_uid})
                elif category_api_ver is not None or category_api_module_ver != '1':
                    return self._error(f'couldn\'t find category API "{category_api_path}"', 1, None, self.fail_on_error)

            # Either base command or API file doesn't 
            if base_category_api_module_ver is not None and not category_meta.get('skip_base_category_commands', False):
                category_api_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f'category_api_v{base_category_api_module_ver}.py')
                if not os.path.isfile(category_api_path):
                    return self._error(f'couldn\'t find category API "{category_api_path}"', 1, None, self.fail_on_error)

                category_apis.append({'path':category_api_path, 'base':True})

            # Load categories
            for category_api in category_apis:
                # category api path should be resolved by now
                suffix = category_api.get('suffix')

                r = utils.sys.load_module(category_api['path'], self.category_cache, fail_on_error = self.fail_on_error, category=True, cmeta=self, suffix=suffix)
                if r['return'] >0: return r

                category_api['code'] = r['cache']['initialized_class']
                category_api['full_module_name'] = r['cache']['full_module_name']

            ###################################################################################################
            # If empty command, print help
            if command == '':
                caller = params.get('_cli', {}).get('caller')
                if caller is None:
                    caller = os.path.basename(sys.executable) + f" -m {__package__}"

                if not con:
                    return {'return':1, 'error':f'"command" key is missing in the request {request}'}

                else:
                    print('<Command> is missing!')

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
                                if r['return']>0: return r

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

                if self.debug:
                    self.logger.debug(f'Resolved command alias: {command_alias}')

                for category_api in category_apis:
                    category_api_code = category_api['code']

                    # Select which function to use (we check names with __ to differentiate from internal Python names if needed)
                    r = utils.sys.find_command_func(category_api_code, command_alias)
                    if r['return']>0: return r

                    func = r['func']

                    if func is not None:
                        command_func_name = r['func_name']
                        break

                if func is None:
                    x = command
                    if command_alias != command:
                        x += f' ({command_alias})'
                    # Shouldn't fail in debug since it's used to check multiple functions ...
                    return self._error(f'command "{x}" doesn\'t exist in category API "{category_api_path}"', 32, None, False) # self.fail_on_error)

                if control_params.get('help', False):
                    r = utils.names.restore_cmeta_obj(cmeta_ref_parts, key='artifact', fail_on_error = self.fail_on_error)
                    if r['return']>0: return r
                    category_str = r['obj']

                    r = utils.sys.get_api_info(category_api_code, command_func_name, f'{category_str} {command}', control_params_desc, category_apis=category_apis)
                    if r['return'] > 0: return r

                    help_text = r['api_info']

                    print (help_text)

                    result['help'] = help_text

                else:
                    if self.debug:
                        r = utils.sys.find_func_definition(category_api_code, command_func_name)
                        if r['return']>0: return r

                        filename = r['filename']
                        start_line = r['start_line']
                        end_line = r['end_line']

                        self.logger.debug(f'Calling {command_func_name}() @ {filename}:{start_line}-{end_line}')
                        self.logger.debug(f'  with parameters {command_params} ...')

                    try:
                        command_params['state'] = state
                        if command_func_name.endswith('_') and not command_func_name.endswith('__'):
                            result = func(**command_params)
                        else:
                            result = func(command_params)

                    except TypeError as te:
                        if self.fail_on_error:
                            raise

                        ste = str(te)

#                        j = ste.find('unexpected ')
#                        if j>0:
#                            ste = ste[j:]

                        r = utils.names.restore_cmeta_obj(cmeta_ref_parts, key='artifact', fail_on_error = self.fail_on_error)
                        if r['return']>0: return r
                        category_str = r['obj']

                        err = f'API call "{category_str} {command}" failed - {ste}.\n\nAdd --help to view API usage and options'

#                        if '() got an unexpected keyword argument' in ste:
#                            r = utils.sys.get_api_info(category_api_code, command_func_name, f'{category_str} {command}', control_params_desc)
#                            if r['return'] > 0: return r
#
#                            err += '\n\nSee ' + r['api_info']

                        return {'return':1, 'error':err}

        # Finalize call
        if control_params.get('json', False):
            print (60*'-')
            utils.common.safe_print_json(result)

        json_file = control_params.get('json_file')
        if json_file is not None and json_file!='':
            r = utils.files.write_file(json_file, result)
            if r['return'] >0: 
                return self._error(r['error'], r['return'], None, self.fail_on_error)

        return result

def _list_paths(cmeta):
    """Generate a list of formatted path strings for CMeta configuration.
    
    Args:
        cmeta: CMeta instance.
        
    Returns:
        list: List of formatted path strings for logging/display.
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
