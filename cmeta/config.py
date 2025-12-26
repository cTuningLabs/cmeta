"""
Configuration class

cMeta author and developer: (C) 2025 Grigori Fursin

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

        "con_error_prefix": "cMeta error: ",

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
        "env_var_cmeta_server_info_url": "http://127.0.0.1:8004/far?hcref=",
        
        "repos_config_filename": "repos.json",
        "repos_dir": "repos",
        "repo_meta_desc": "_cmr.yaml",

        "repo_local_meta": {
           'artifact':'local,9a3280b14a4285c9',
           'permanent':True
        },

        "category_repo_uid": "f4f792ab40c7498f",

        "default_git": "https://github.com",
        "default_git_repo": "ctuninglabs",
        "default_ctuning_api": "https://cTuning.ai/api/v1",

        "index_dir": "index",
        "index_db_filename": "index.db",

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
}

params_desc = [
  {'key':'help', 'aliases':['h'], 'type': bool, 'desc': 'Show help' },
  {'key':'version', 'aliases':['v'], 'type': bool, 'desc': 'Show version'},
  {'key':'reindex', 'type': bool, 'desc': 'Reindex all artifacts'},
  {'key':'verbose', 'aliases':['v'], 'type': bool, 'desc': 'Use verbose output'},
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
        value  # String value to check for "on" state
):
    """
    Check if a string value represents an "on" state.
    
    Args:
        value (str | bool | None): String to check (case-insensitive). Can be None.
        
    Returns:
        bool: True if value is "1", "on", "true" or "yes" (case-insensitive), False otherwise.
              Returns False if value is None.
    """
    if value is None:
        return False
    
    if value is True:
        return True

    if not isinstance(value, str):
        return False
    
    return value.lower().strip() in ('1', 'on', 'true', 'yes')


def set_logging(
        name: str,                        # Logger name
        log_level: Optional[str] = None,  # Logging level string
        log_file: Optional[str] = None,   # Path to log file
        log_format: Optional[str] = None  # Format string for log messages
) -> logging.Logger:
    """Set up logging configuration and return a logger.
    
    Args:
        name (str): Logger name.
        log_level (str | None): Logging level as string (case-insensitive). 
                  Accepted values: "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
                  If None or empty string, logging is disabled.
        log_file (str | None): Path to log file. If provided and not empty, logs will be written to this file.
                 If None or empty string, logs will be written to console.
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


def check_init_vars_from_env():
    """Load CMeta initialization parameters from environment variables.
    
    Checks various environment variables to determine the home directory,
    logging settings, and debug/fail-on-error flags for CMeta initialization.
    
    Returns:
        dict: A CMeta dictionary with the following keys:
            - return (int): Always 0 (success).
            - init (dict): Dictionary containing initialization parameters including
              'home', 'fail_on_error', 'log_level', 'log_file', and 'debug'.
    """

    init = {}

    ENV_CMETA_HOME = cfg['env_var_home']
    ENV_CMETA_HOME2 = cfg['env_var_home2']
    ENV_CMETA_LOG = cfg['env_cmeta_log']
    ENV_CMETA_LOG_FILE = cfg['env_cmeta_log_file']

    # First check main home variable
    home = os.environ.get(ENV_CMETA_HOME, '')
    if home == '':
        # Smart home - first virtual env and if not, then use this var
        home = os.environ.get(cfg['env_var_virtual_env'], '')
        if home == '':
            home = os.environ.get(cfg['env_var_virtual_env2'], '')
        if home == '':
            home = os.environ.get(ENV_CMETA_HOME2, '')
        else:
            home = os.path.join(home, cfg['capitalized_name'])

    if home == '':
        home = Path.home() / cfg['capitalized_name']

    init['home'] = str(home)

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
        name: str,             # Logger name
        init: dict = {},       # Base initialization dictionary
        force_init: dict = {}  # Parameters to forcibly override
):
    """Setup CMeta initialization parameters and configure logger.
    
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
    """
    
    for k in force_init:
        init[k] = force_init[k]

    if is_on(init.get('home')):
        init['home'] = str(Path.home() / cfg['capitalized_name'])

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
