"""
Configuration class

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import logging
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

log_level_mapping = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'WARN': logging.WARNING,  # Common alias
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL,
    'FATAL': logging.CRITICAL  # Common alias
}

cfg = {
        "name": "cMeta",
        "capitalized_name": "CMETA",

        "log_format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",

        "con_error_prefix": "cMeta notice: ",

        "copyright": "Copyright (c) 2025-2026 Grigori Fursin and cTuning Labs",

        "env_var_home": "CMETA_HOME",
        "env_var_home2": "CMETA_HOME2",
        "env_var_virtual_env": "VIRTUAL_ENV",
        "env_var_virtual_env2": "CONDA_PREFIX",
        "env_var_cmeta_fail_on_error": "CMETA_FAIL_ON_ERROR",
        "env_cmeta_log": "CMETA_LOG",
        "env_cmeta_log_file": "CMETA_LOG_FILE",
        "env_var_cmeta_debug": "CMETA_DEBUG",
        "env_var_internal_repo_path": "CMETA_INTERNAL_REPO_PATH",
        "env_var_cmeta_verbose": "CMETA_VERBOSE",
        "env_var_cmeta_authors": "CMETA_AUTHORS",
        "env_var_cmeta_copyright": "CMETA_COPYRIGHT",
        "env_var_cmeta_generator": "CMETA_GENERATOR",
        "env_var_cmeta_server_info_url": "CMETA_SERVER_INFO_URL",
        "env_var_pip_install_args": "CMETA_PIP_INSTALL_ARGS",

        "repos_config_filename": "repos.json",
        "repos_dir": "repos",
        "repo_meta_desc": "_cmr.yaml",

        "repo_local_meta": {
           'artifact':'local,9a3280b14a4285c9',
           'permanent':True
        },

        "category_repo_uid": "f4f792ab40c7498f",

        "default_git": "https://github.com/",
        "default_git_repo": "ctuninglabs",
        "default_ctuning_api": "https://cTuning.ai/api/v1",
        "url_cserver_info": "http://127.0.0.1:8004/far?hcref=",
        "default_cmeta_repo_url": "https://cTuning.ai/project/cmeta/repos/files/cmr-",

        "index_dir": "index",

        "meta_filename_base": "_cmeta",

        "base_category_last_api_version": 1,

        "command_aliases": {
          "search": "find",
          "add": "create",
          "rm": "delete",
          "remove": "delete",
          "del": "delete",
          "ren": "move",
          "rename": "move",
          "mv": "move",
          "ls": "list",
          "load": "read",
          "cp": "copy",
        },

        "default_config_name": "default",

        "repro_input_file": "cmeta-repro-input.json",
        "repro_input_file_rt": "cmeta-repro-input2.json",
        "repro_output_file": "cmeta-repro-output.json",

        "dump_ctx_output_file": "cmeta-ctx.json",
}

params_desc = [
  {'key':'help', 'aliases':['h'], 'type': bool, 'desc': 'Show help' },
  {'key':'reindex', 'type': bool, 'desc': 'Reindex all artifacts'},
  {'key':'verbose', 'aliases':['v'], 'type': bool, 'desc': 'Use verbose output'},
  {'key':'quiet', 'aliases':['q'], 'type': bool, 'desc': 'Quetly select default answer to questions'},
  {'key':'repro', 'aliases':['r'], 'type': bool, 'desc': 'Save input and related into to cmeta-reproduce-input.json'},
]

params_command_desc = [
  {'key':'base', 'type': bool, 'desc': 'Call common commands from the base category', 'space_before':True },
  {'key':'api', 'type': int, 'desc': 'Choose category API version'},
]

params_command2_desc = [
  # The type in category is None - that's correct, otherwise will be always converted to string even if it can be dict from parsed nested calls
  # TBD: allow mixed types (str|dict)
  {'key':'category', 'types':[str,dict], 'desc': 'Category name (taken from the 1st argument from CLI)', 'skip_from_help':True },
  {'key':'command', 'type': str, 'desc': 'Command (taken from the 2st argument from CLI)', 'skip_from_help':True },
  {'key':'con', 'type': bool, 'desc': 'Force output to console', 'space_before':True },
  {'key':'json', 'aliases':['j'], 'type': bool, 'desc': 'Print command output as JSON' },
  {'key':'json_file', 'aliases':['json-file', 'jf'], 'type': str, 'desc': 'Specify json file to save command output' },
  {'key':'dump', 'type': bool, 'desc': 'Dump context to cmeta-ctx.json at the end of a command' },
  {'key':'pause_at_the_end', 'type': bool, 'desc': 'Pause at the end of a command' },
]

params_command3_desc = [
  {'key':'version', 'aliases':['V'], 'desc': 'Show version'},
  {'key':'print_home', 'aliases':['print-home'], 'type': bool, 'desc': 'Print the path of the cMeta home and nothing else (for scripts: no network, nothing set up)'},
]

params_init_desc = [
  {'key':'home', 'types':[str,bool], 'desc': 'Specify path with CMeta repositories', 'space_before':True },
  {'key':'debug', 'type': bool, 'desc': 'Enable debug mode (sets log_level to "DEBUG" and fail_on_error to True)'},
  {'key':'fail_on_error', 'aliases':['fail', 'fail-on-error'], 'type': bool, 'desc': 'Raise exception on first error for debugging'},
  {'key':'log_level', 'aliases':['log-level'], 'type': str, 'values': list(log_level_mapping.keys()), 'desc': 'Set logging level (e.g., debug, info, warning, error)'},
  {'key':'log_file', 'aliases':['log-file'], 'type': str, 'desc': 'Specify file for logging'},
  {'key':'pause_if_error', 'aliases':['pif'], 'type': bool, 'desc': 'Pause before exiting in case of errors' },
]


def is_on(
    value,  # String to check (case-insensitive). Can be None.
):
    """
        Check if a string value represents an "on" context.

        Args:
            value (str | bool | None): String to check (case-insensitive). Can be None.
        Returns:
            bool: True if value is "1", "on", "true" or "yes" (case-insensitive), False otherwise.
                  Returns False if value is None.

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    if value is None:
        return False
    
    if value is True:
        return True

    if not isinstance(value, str):
        return False
    
    return value.lower().strip() in ('1', 'on', 'true', 'yes')


def set_logging(
    name: str,  # Logger name.
    log_level: Optional[str] = None,  # Logging level as string (case-insensitive).
    log_file: Optional[str] = None,  # Path to log file. If provided and not empty, logs will be written to this file.
    log_format: Optional[str] = None,  # Format string for log messages.
) -> logging.Logger:
    """
        Set up logging configuration and return a logger.

        Args:
            name (str): Logger name.
            log_level (str | None): Logging level as string (case-insensitive).
            log_file (str | None): Path to log file. If provided and not empty, logs will be written to this file.
            log_format (str | None): Format string for log messages.
        Returns:
            logging.Logger: Configured logger instance.

        Raises:
            ValueError: If invalid log level is provided.
    """

    # Get or create logger
    logger = logging.getLogger(name)

    # Don't add multiple handlers if already configured from the caller ...
    logger_already_initialized = False
    if logger.handlers:
        for handler in logger.handlers:
            if handler.formatter:
                logger_already_initialized = True

    if not logger_already_initialized:
        if log_level and log_level.strip():
            # Convert string log level to logging constant
            log_level_upper = log_level.strip().upper()
            
            if log_level_upper in log_level_mapping:
                log_level_num = log_level_mapping[log_level_upper]
                
                # Set the logger level
                logger.setLevel(log_level_num)

                # Remove existing handlers to avoid duplicates
                for handler in logger.handlers[:]:
                    logger.removeHandler(handler)
                
                # Create and configure handler
                if log_file and log_file.strip():
                    # Create directory for log file if it doesn't exist
                    log_path = Path(log_file.strip())
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    handler = logging.FileHandler(str(log_path), mode='a')
                else:
                    # Console logging
                    handler = logging.StreamHandler()
                
                # Set formatter and add handler
                if log_format is None:
                    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                formatter = logging.Formatter(log_format)
                handler.setFormatter(formatter)

                handler.setLevel(log_level_num)
                logger.addHandler(handler)

                logger.propagate = False # avoid duplication in higher-level apps such as FastAPI
            else:
                # If invalid level provided, raise an error
                x = ', '.join(log_level_mapping.keys())
                return {'return':1, 'error': f"Invalid log level '{log_level}'. Accepted values: {x}"}
        else:
            # Disable logging if log_level is None or empty
            logger.setLevel(logging.CRITICAL + 1)

            # Remove all handlers
            for handler in logger.handlers[:]:
                logger.removeHandler(handler)
    
    return {'return':0, 'logger': logger}


def _home_candidates():
    """
        The folders the environment offers as the cMeta home, in the order of their priority, each with the
        name of the variable that gives it ('' for the default): CMETA_HOME, <VIRTUAL_ENV>/CMETA,
        <CONDA_PREFIX>/CMETA, CMETA_HOME2, ~/CMETA. Only the variables that are set are listed.

        Returns:
            list: [(home, variable, value of the variable), ...] - the default is always the last.
    """
    candidates = []

    home = os.environ.get(cfg['env_var_home'], '').strip()
    if home != '':
        candidates.append((home, cfg['env_var_home'], home))

    # A virtual environment keeps a home of its own: the first of the two that is set
    for variable in (cfg['env_var_virtual_env'], cfg['env_var_virtual_env2']):
        value = os.environ.get(variable, '')
        if value != '':
            candidates.append((os.path.join(value, cfg['capitalized_name']), variable, value))

    home = os.environ.get(cfg['env_var_home2'], '').strip()
    if home != '':
        candidates.append((home, cfg['env_var_home2'], home))

    candidates.append((str(Path.home() / cfg['capitalized_name']), '', ''))

    return candidates


def home_from_env():
    """
        The cMeta home as the environment gives it: `CMETA_HOME`; else `<VIRTUAL_ENV>/CMETA`; else
        `<CONDA_PREFIX>/CMETA`; else `CMETA_HOME2` as it is; else `~/CMETA`.

        Returns:
            tuple: (home, variable) - the folder and the name of the variable that chose it ('' for the default).
    """
    home, variable, _ = _home_candidates()[0]

    return home, variable


def home_choice(
    home,  # The home of a cMeta instance.
):
    """
        What chose `home` as the cMeta home, for a message: the variable of the environment that gives
        exactly this folder, or 'given' when none does (the `home` argument of CMeta, `--home`).

        Returns:
            dict: {'source': 'CMETA_HOME' | 'VIRTUAL_ENV' | 'CONDA_PREFIX' | 'CMETA_HOME2' | 'default' | 'given',
                   'value': the value of that variable ('' for the last two),
                   'text': the same in words, to follow "chosen by"}.
    """
    def same(a, b):
        return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))

    for candidate, variable, value in _home_candidates():
        if not same(candidate, home):
            continue

        if variable == '':
            return {'source': 'default', 'value': '', 'text': 'the default'}

        if variable == cfg['env_var_virtual_env']:
            return {'source': variable, 'value': value,
                    'text': f'{variable}={value} - a virtual environment keeps a home of its own'}

        if variable == cfg['env_var_virtual_env2']:
            return {'source': variable, 'value': value,
                    'text': f'{variable}={value} - a conda environment keeps a home of its own'}

        return {'source': variable, 'value': value, 'text': variable}

    return {'source': 'given', 'value': '', 'text': 'this run: --home or the home argument of CMeta'}


def _home_of_the_flag():
    """
        The home of a bare `--home` (`home=True`): CMETA_HOME, else CMETA_HOME2, else ~/CMETA - a virtual or
        conda environment is not asked.

        Returns:
            str: The folder.
    """
    home = os.environ.get(cfg['env_var_home'], '').strip()

    if home == '':
        home = os.environ.get(cfg['env_var_home2'], '').strip()

    if home == '':
        home = os.path.join(Path.home(), cfg['capitalized_name'])

    return home


def home_path(
    home = None,  # As `--home` or the `home` argument of CMeta gives it: a folder, True (a bare `--home`) or None.
):
    """
        The cMeta home that `CMeta(home=home)` uses, as an absolute path: `home` when it is a folder; for a bare
        `--home` (True) CMETA_HOME, else CMETA_HOME2, else ~/CMETA; without `home` the environment's choice
        (`home_from_env`: CMETA_HOME, <VIRTUAL_ENV>/CMETA, <CONDA_PREFIX>/CMETA, CMETA_HOME2, ~/CMETA).

        Nothing is created and nothing but the environment is read: the folder may not exist yet.
        `cx --print-home` prints it.

        Args:
            home (str | bool | None): A folder, True for a bare `--home`, or None for the environment's choice.
        Returns:
            str: The absolute path of the home.
    """
    if home is None:
        home = home_from_env()[0]
    elif is_on(home):
        home = _home_of_the_flag()

    return os.path.abspath(str(home))


def check_init_vars_from_env():
    """
        Load CMeta initialization parameters from environment variables.

        Checks various environment variables to determine the home directory,
        logging settings, and debug/fail-on-error flags for CMeta initialization.

        Returns:
            dict: A CMeta dictionary with the following keys:
                - return (int): Always 0 (success).
                - init (dict): Dictionary containing initialization parameters including
                  'home', 'fail_on_error', 'log_level', 'log_file', and 'debug'.

        Args:
            None.
        Raises:
            Exception: Propagated runtime errors, if any.
    """

    init = {}

    ENV_CMETA_LOG = cfg['env_cmeta_log']
    ENV_CMETA_LOG_FILE = cfg['env_cmeta_log_file']

    init['home'] = home_from_env()[0]

    if is_on(os.environ.get(cfg['env_var_cmeta_fail_on_error'])):
        init['fail_on_error'] = True

    if ENV_CMETA_LOG in os.environ:
        init['log_level'] = os.environ.get(ENV_CMETA_LOG)

    if ENV_CMETA_LOG_FILE in os.environ:
        init['log_file'] = os.environ.get(ENV_CMETA_LOG_FILE)

    if is_on(os.environ.get(cfg['env_var_cmeta_debug'])):
        init['debug'] = True
        if init.get('fail_on_error') is None:
            init['fail_on_error'] = True

    return {'return':0, 'init':init}

def update_init_and_setup_logger(
    name: str,  # Logger name (typically __name__ of the calling module).
    init: dict = {},  # Base initialization dictionary from environment.
    force_init: dict = {},  # Dictionary of parameters to forcibly override init values.
):
    """
        Setup CMeta initialization parameters and configure logger.

        Merges initialization parameters from environment with forced parameters,
        applies defaults and logical implications (e.g., debug mode enables DEBUG logging),
        and sets up the logger with the specified configuration.

        Args:
            name (str): Logger name (typically __name__ of the calling module).
            init (dict): Base initialization dictionary from environment.
            force_init (dict): Dictionary of parameters to forcibly override init values.
        Returns:
            dict: A CMeta dictionary with the following keys:
                - **return** (int): 0 for success, >0 for error.
                - **error** (str): Error message if return > 0.
                - **logger** (logging.Logger): Configured logger instance (if return == 0).
                - init (dict): Final merged initialization parameters (if return == 0).

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    
    for k in force_init:
        init[k] = force_init[k]

    # A bare `--home` (True rather than a path): CMETA_HOME, else CMETA_HOME2, else ~/CMETA
    if is_on(init.get('home')):
        init['home'] = _home_of_the_flag()

    if init.get('log_file') is not None and init.get('log_level') is None:
        init['log_level'] = 'DEBUG'

    if init.get('debug') is None: 
        init['debug'] = False
    elif init.get('debug') is True:
        init['log_level'] = 'DEBUG'
        if init.get('log_level') is None:
            init['log_level'] = 'DEBUG'
        if init.get('fail_on_error') is None:
            init['fail_on_error'] = True

    if init.get('fail_on_error') is None: 
        init['fail_on_error'] = False

    try:
        r = set_logging(name, init.get('log_level'), init.get('log_file'), init.get('log_format'))
    except Exception as e:
        if init.get('fail_on_error'): raise
        return {'return':1, 'error':format(e)}

    if r['return']>0: return r

    logger = r['logger']

    return {'return': 0, 'logger': logger, 'init': init}
