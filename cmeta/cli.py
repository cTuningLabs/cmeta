"""
СMeta core class and functions

cMeta author and developer: (C) 2025 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import logging
import os
import sys
import copy

from . import config
from . import utils

cmeta_init = None
logger = None
cmeta = None
fail_on_error = False

caller = None

cli_params_desc = config.params_desc + config.params_command_desc
cli_init_params_desc = config.params_init_desc
params_command2_desc = config.params_command2_desc

def process(
        cmd: list
):
    """Process command line arguments and execute CMeta operations.
    
    This function parses command-line arguments, initializes the CMeta framework,
    and executes the requested category command. It handles global flags, category
    detection, and command routing.
    
    Args:
        cmd (list): Command line arguments as a list of strings. The original list is not modified.
        
    Returns:
        dict: A CMeta dictionary with the following keys:
            - return (int): 0 for success, >0 for error codes.
            - error (str): Error message if return > 0.
            - Other keys depend on the executed command.
    """

    global caller, cmeta_init, fail_on_error, logger, cmeta

    # Get pre-init from environment variables
    if cmeta_init is None:
        r = config.check_init_vars_from_env()
        if r['return'] > 0: return r

        cmeta_init = r['init']

        fail_on_error = cmeta_init.get('fail_on_error', False)

        for key in ['--fail-on-error', '--fail_on_error', '--debug']:
            if key in cmd:
                fail_on_error = True

    # Parse CMD
    r = utils.parse_cmd(cmd, fail_on_error=fail_on_error)
    if r['return'] > 0: return r
    # Note that '-' in root keys will be replaced to '_' 
    # to be able to map them into Python variables ...

    params = r['params']

    # Process known flags to initialize cMeta
    r = utils.check_params(params, cli_init_params_desc, fail_on_error=fail_on_error)
    if r['return'] > 0: return r

    params = r['remaining_params']
    cmeta_init_forced_from_cmd = r['checked_params']

    # Process init flags only during first run
    if logger is None:
        # Setup logger and cMeta init vars from either cmd or environment
        
        # Force our format in CLI
        cmeta_init['log_format'] = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

        r = config.update_init_and_setup_logger(__name__, cmeta_init, cmeta_init_forced_from_cmd)
        if r['return']>0: return r

        # Check if raise on error
        logger = r['logger']
        cmeta_init = r['init']

        # Update utils fail_on_error
        fail_on_error = cmeta_init.get('fail_on_error', False)
 
    # Logger is now initialized
    # Use lazy formatting for performance to log original command
    logger.debug('Calling "cli" with command "{}" ...'.format(cmd))

    args = params.get('args', [])

    # If positional arguments are not present, check first level params
    if len(args) == 0 and (params.get('help', False) or params.get('h', False) or len(params)==0):
        print ('Common Meta Framework Usage:')
        print('')
        print(f'   {caller} [<category>] [<command>] [<args>] [<flags>]')
        print(f'   {caller} category list')
        print(f'   {caller} <category> (--help)')
        print(f'   {caller} <category> <command> --help')
        print('')

        print ('Global flags:')
        print('')
        r = utils.print_params_help(cli_params_desc)
        if r['return'] >0: return r
        print (r['params_info'])

        print ('Global initalization flags for the framework:')
        r = utils.print_params_help(cli_init_params_desc)
        if r['return'] >0: return r
        print (r['params_info'])
        print('')

        print ('Common flags for all categories:')
        r = utils.print_params_help(params_command2_desc)
        if r['return'] >0: return r
        print (r['params_info'])

        return {'return':0}

    # Initialize cMeta engine
    if cmeta is None:
        from .core import CMeta
        cmeta = CMeta(**cmeta_init)

    # Check args
    artifact_repo_name = None
    artifact_name = None

    if len(args) >0:
        category_obj = args.pop(0)

        if category_obj == '.':

            r = utils.common.detect_cid_in_the_current_directory(cmeta, 
                  debug = cmeta_init.get('debug', False), 
                  logger = logger)
            if r['return'] >0: return r

            artifact_repo_name = r['artifact_repo_name']
            artifact_path = r['artifact_path']

            category_alias = r['category_alias']
            category_uid = r['category_uid']
            category_obj = r['category_obj']

            artifact_alias = r['artifact_alias']
            artifact_uid = r['artifact_uid']
            artifact_name = r['artifact_name']
    
            if category_obj is None and len(args) >0:
                category_obj = args.pop(0)

        if category_obj is not None:
            params['category'] = category_obj

    command = None
    if len(args) >0:
        command = args.pop(0)
        params['command'] = command

    # Check if some info is automatically detected from the current directory when category_obj is "."
    if artifact_name is not None:
        arg0 = artifact_name
        if artifact_repo_name is not None:
            arg0 = artifact_repo_name + ':' + arg0

        args.insert(0, arg0)

        if command is None:
            params['command'] = 'info'

    elif artifact_repo_name is not None:
        if len(args) > 0:
            if ':' not in args[0]:
                args[0] = artifact_repo_name + ':' + args[0]
        else:
            args.insert(0, artifact_repo_name + ':')

    if len(args) >0:
        for i, value in enumerate(args, start=1):
            key = f"arg{i}"
            if key not in params:
                params[key] = value        

    if 'args' in params:
        del(params['args'])

    if 'con' not in params:
        params['con'] = True

    # Adding some extra info from CLI to save to the state origin
    # for further debugging and reproducibility
    if '_cli' not in params:
        params['_cli'] = {}

    params['_cli']['cmd'] = cmd
    params['_cli']['caller'] = caller

    if cmeta_init.get('debug', False):
        params['_cli']['cmeta_init'] = cmeta_init

    result = cmeta.access(params)

    if type(result) != dict:
        return {'return':99, 'error': f'Internal error in a category API implementation - command did not return cMeta dict ({result})'}

    if result['return']>0 and cmeta_init.get('pause_if_error', False):
        result['pause_if_error'] = True

    return result



def catch(
        result: dict  # Result dictionary from CMeta operation
):
    """
    Check result dictionary for errors and exit if error is found.
    
    Args:
        result (dict): Dictionary that must contain a "return" key
        
    Raises:
        SystemExit: If return code is greater than 0, exits with that code
    """

    global logger, cmeta_init

    pause_if_error = result.pop('pause_if_error', False)

    if not isinstance(result, dict):
        if logger is not None:
            logger.debug(f"CLI Result is not dictionary: {result}")
        result = {"return":99, "error": f"Result must be a dictionary"}
    
    if "return" not in result:
        if logger is not None:
            logger.debug(f"CLI  Result doesn't have 'return' key: {result}")
        result = {"return":99, "error": f"Result dictionary must contain 'return' key"}
    
    return_code = result.get("return", 0)

    if return_code > 0:
        error_msg = result.get("error", f"Unknown error (return code: {return_code})")
        error_text = config.cfg['con_error_prefix'] + error_msg + '!'

        if cmeta_init is not None and cmeta_init.get('fail_on_error', False):
            raise Exception(error_text)

        print(error_text, file=sys.stderr)

        if pause_if_error:
            print ('')
            utils.sys.flush_input()
            input ('Press Enter to finish execution ...')

        sys.exit(return_code)

    return return_code

def set_fail_on_error(
        value: bool  # Boolean value for fail_on_error flag
):
    """Set the global fail_on_error flag for error handling behavior.
    
    Args:
        value (bool): Boolean value to set for fail_on_error flag.
    """
    global fail_on_error
    fail_on_error = value

def main_cmeta() -> int:
    """Entry point for the 'cmeta' command-line interface.
    
    Returns:
        int: Exit code (0 for success, non-zero for errors).
    """
    global caller
    caller = "cmeta"
    return main()

def main_meta() -> int:
    """Entry point for the 'meta' command-line interface.
    
    Returns:
        int: Exit code (0 for success, non-zero for errors).
    """
    global caller
    caller = "meta"
    return main()

def main_cx() -> int:
    """Entry point for the 'cx' command-line interface.
    
    Returns:
        int: Exit code (0 for success, non-zero for errors).
    """
    global caller
    caller = "cx"
    return main()

def main_cserver() -> int:
    """Entry point for the 'cserver' command-line interface.
    
    Returns:
        int: Exit code (0 for success, non-zero for errors).
    """

    args = ['app', 'run', 'cserver'] + sys.argv[1:]

    return main(args = args)

def main(args = None) -> int:
    """Main function for CLI entry point. Processes sys.argv and calls CMeta.
    
    Parses command-line arguments from sys.argv, processes them through the CMeta
    framework, and handles the results including error checking and exit codes.
    
    Returns:
        int: Exit code (0 for success, non-zero for errors).
    """
    global caller
    if caller is None:
        caller = os.path.basename(sys.executable) + f" -m {__package__}"

    if args is None:
        args = sys.argv[1:]

    result = process(args)

    result_code = catch(result)

    return result_code
