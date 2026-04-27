"""
Common reusable functions

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
from .common import _error
from .cli import print_params_help
from . import files

###################################################################################################
def load_module(
    module_path: str,  # Absolute path to the Python module file.
    module_cache: dict,  # Dictionary to store cached module information.
    fail_on_error: bool = False,  # If True, raises exception on error instead of returning error dict.
    init_class: str = None,  # Class name to instantiate from the loaded module, if provided.
    cmeta = None,  # CMeta instance to pass to Category initialization.
    suffix: str = None,  # Optional suffix for module name sanitization.
    self_meta: dict = None,  # Optional metadata dictionary to attach to the initialized object.
):
    """
        Dynamically load a Python module from file path with caching support.

        Loads category API modules and manages them in a cache. Handles module naming
        sanitization and creates proper package structures for category modules.

        Args:
            module_path (str): Absolute path to the Python module file.
            module_cache (dict): Dictionary to store cached module information.
            fail_on_error (bool): If True, raises exception on error instead of returning error dict.
            category (bool): If True, initializes the Category class from the module.
            cmeta: CMeta instance to pass to Category initialization.
            suffix (str | None): Optional suffix for module name sanitization.

            init_class (str): Class name to instantiate from the loaded module, if provided.
            self_meta (dict): Optional metadata dictionary to attach to the initialized object.
        Returns:
            dict: Dictionary with 'return': 0 and 'cache' containing module info,
                  or 'return' > 0 and 'error' on failure.

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    import os, sys, importlib.util, importlib.machinery, re, hashlib

    def sanitize(
        name,  # Object or artifact name.
        suffix = None,  # Value for suffix.
    ):
        """
            Sanitize dynamic module/package names for safe Python imports.

            Args:
                name: Object or artifact name.
                suffix: Value for suffix.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """
        cleaned = re.sub(r'[^0-9a-zA-Z_]', '_', name)

        if re.match(r'^\d', cleaned):
            cleaned = "_" + cleaned

        if cleaned != name or cleaned.strip("_") == "":
            if suffix is None or suffix == '':
                suffix = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]

        if suffix is not None and suffix != '':
            cleaned = f"{cleaned}_{suffix}"

        return cleaned

    if not os.path.isfile(module_path):
        return _error(f'Module file not found: {module_path}', 16, None, fail_on_error)

    module_path = os.path.abspath(module_path)
    module_dir = os.path.dirname(module_path)
    module_name = os.path.splitext(os.path.basename(module_path))[0]

    category_dir = os.path.dirname(module_dir)
    raw_cat = os.path.basename(category_dir)
    raw_pkg = os.path.basename(module_dir)

    cat_name = sanitize(raw_cat, suffix)
    pkg_name = sanitize(raw_pkg)

    full_package_name = f"{cat_name}.{pkg_name}"
    full_module_name = f"{full_package_name}.{module_name}"

    timestamp = os.path.getmtime(module_path)

    if module_path in module_cache:
        cached = module_cache[module_path]
        if cached.get("timestamp") == timestamp:
            return {"return": 0, "cache": cached}

    try:
        # Ensure category package exists
        if cat_name not in sys.modules:
            spec = importlib.machinery.ModuleSpec(cat_name, loader=None, is_package=True)
            pkg = importlib.util.module_from_spec(spec)
            pkg.__path__ = [category_dir]
            sys.modules[cat_name] = pkg

        # Ensure api subpackage exists
        if full_package_name not in sys.modules:
            spec = importlib.machinery.ModuleSpec(full_package_name, loader=None, is_package=True)
            pkg = importlib.util.module_from_spec(spec)
            pkg.__path__ = [module_dir]
            sys.modules[full_package_name] = pkg

        # Load the plugin module
        spec = importlib.util.spec_from_file_location(full_module_name, module_path)
        module = importlib.util.module_from_spec(spec)

        module.__package__ = full_package_name
        module.__file__ = module_path

        sys.modules[full_module_name] = module
        spec.loader.exec_module(module)

        cache_data = {
            "python_module": module,
            "timestamp": timestamp,
            "full_module_name": full_module_name,
        }

        if init_class:
            cls = getattr(module, init_class)

            obj = cls(cm=cmeta)

            if self_meta is not None and type(self_meta) == dict:
                obj.cmeta = self_meta

            cache_data["initialized_class"] = obj

        module_cache[module_path] = cache_data
        return {"return": 0, "cache": cache_data}

    except Exception as e:
        return _error(f'Failed to import module {full_module_name} at "{module_path}"', 1, e, fail_on_error)

###################################################################################################
def find_command_func(
    category_api,  # Category API object instance.
    command: str,  # Command name string to search for.
):
    """
        Find command function in category API object.

        Searches for the command function using standard naming conventions:
        command_, command__, or command (in that order).

        Args:
            category_api: Category API object instance.
            command (str): Command name string to search for.

        Returns:
            dict: Dictionary with 'return': 0, 'func' (function object or None),
                  and 'func_name' (actual function name if found).

        Raises:
            Exception: Propagated runtime errors, if any.
    """

    func = None

    for find_command in [command + '_', command + '__', command]:
        if hasattr(category_api, find_command):
           available_func = getattr(category_api, find_command)
           if callable(available_func):
               func = available_func
               break

    result = {'return':0, 'func': func}

    if func is not None:
        result['func_name'] = find_command

    return result

###################################################################################################
def get_func_properties(
    f,  # Function object to inspect.
):
    """
        Extract source code properties from a function object.

        Gets the source file path, line numbers, and API documentation text
        for a given function.

        Args:
            f: Function object to inspect.

        Returns:
            dict: Dictionary with 'return': 0 and properties including 'filename',
                  'start_line', 'end_line', and 'api_text'.

        Raises:
            Exception: Propagated runtime errors, if any.
    """

    import inspect

    filename = inspect.getsourcefile(f) or inspect.getfile(f)
    lines, start_line = inspect.getsourcelines(f)
    end_line = start_line + len(lines) - 1

    r = get_api_text(lines, start_line)
    if r['return']>0: return r

    api_info = r['api_info']

    short_func_desc = ''
    j = api_info.find('"""')
    if j>0:
        x = api_info[j+3:].strip()
        if x.endswith('"""'):
            x = x[:-3]
        if len(x)>0:
            j = x.find('\n')
            short_func_desc = x[:j] if j>0 else x
            if short_func_desc.endswith('"""'):
                short_func_desc = short_func_desc[:-3]

    return {'return':0, 'func': f, 
                        'filename':filename, 
                        'lines': lines, 
                        'start_line':start_line, 
                        'end_line':end_line, 
                        'api_info':api_info, 
                        'short_func_desc': short_func_desc}
    

###################################################################################################
def find_func_definition(
    obj,  # Object instance to search for the function.
    name: str,  # Name of the function to find.
):
    """
        Find function definition in an object by name.

        Locates a function by name in an object's class, unwraps decorators,
        and extracts its source code properties.

        Args:
            obj: Object instance to search for the function.
            name (str): Name of the function to find.

        Returns:
            dict: Dictionary with 'return': 0 and function properties on success,
                  or 'return': 1 and 'error' if function not found.

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    import inspect

    func = getattr(obj.__class__, name, None)
    if func is None:
        return {'return':1, 'error':f'function "{name}" not found in {obj.__class__.__name__}'}

    # Unwrap in case it's decorated
    func = inspect.unwrap(func)

    return get_func_properties(func)



###################################################################################################
def get_api_info(
    category_api,  # The category API object.
    command: str,  # The command name.
    full_command: str,  # Full command string.
    control_params_desc = None,  # Control parameters description.
    category_apis: list = [],  # List of category APIs.
):
    """
        Extract function definition and docstring for API information.

        Args:
            category_api: The category API object.
            command (str): The command name.
            full_command (str): Full command string.
            control_params_desc: Control parameters description.
            category_apis (list): List of category APIs.

        Returns:
            dict: Dictionary with 'return': 0 and 'api_info' string for success,
                  or 'return' > 0 and 'error' for errors.

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    
    r = find_func_definition(category_api, command)
    if r['return'] > 0: 
        return r

    lines = r['lines']
    start_line = r['start_line']
    end_line = r['end_line']
    filename = r['filename']

    x = f'for "{full_command}" ' if full_command != '' else ''

    api_info = f'Python API {x}({filename}:{start_line}-{end_line}):\n'

    r = get_api_text(lines, start_line)
    if r['return']>0: return r

    api_info += r['api_info']

    # Extract redirects
    for line in api_info.split('\n'):
        linex = line.strip()

        func = ''

        xcategory_api = category_api

        if linex.startswith('@base.'):
            func = linex[6:]
            xcategory_api = category_apis[-1]['code']

        elif linex.startswith('@self.'):
            func = linex[6:]
            if func == command:
                func = ''

        if func!='':
            j = func.find('(')
            if j>0:
                func = func[:j]

            r = get_api_info(xcategory_api, func, '', category_apis = category_apis)
            if r['return']>0: return r

            api_info += '\n' + r['api_info']

    if control_params_desc is not None:
        r = print_params_help(control_params_desc)
        if r['return']>0: return r

        api_info += '\nCommon CLI flags (remove -- from keys for the Python API):\n'
        api_info += '\n' + r['params_info']

    return {'return':0, 'api_info': api_info}

###################################################################################################
def get_api_text(
    lines: list,  # List of source code lines.
    start_line: int,  # Starting line number.
):
    """
        Extract API text from function source lines.

        Parses function definition and docstring from source code lines.

        Args:
            lines (list): List of source code lines.
            start_line (int): Starting line number.

        Returns:
            dict: Dictionary with 'return': 0 and 'api_info' containing formatted text.

        Raises:
            Exception: Propagated runtime errors, if any.
    """

    api_info = ''

    # Add function definition lines
    func_def_lines = []
    docstring_lines = []
    found_def = False
    found_docstring = False

    for line in lines:
        stripped = line.strip()

        if not found_def and (stripped.startswith('def ') or stripped.startswith('async def ')):
            found_def = True
            func_def_lines.append(line)
            continue

        if found_def and not found_docstring:
            # Check for docstring immediately after function definition
            if stripped.startswith('"""'):
                found_docstring = True
                docstring_lines.append(line)
                if len(stripped)>3 and stripped.endswith('"""'):
                    break
                continue

            func_def_lines.append(line)
              
        if found_docstring:
            docstring_lines.append(line)
            if stripped.endswith('"""') and len(stripped) > 3:
                break
            elif stripped == '"""':
                break
#        elif found_def and not found_docstring:
#            # If not a docstring, break after function definition line
#            break

    if func_def_lines:
        api_info += "\n"
        for l in func_def_lines:
            api_info += l
    if docstring_lines:
        api_info += "\n"
        for l in docstring_lines:
            api_info += l

    return {'return': 0, 'api_info': api_info}

###################################################################################################
def flush_input():
    """
        Flush stdin buffer on Unix/Linux/Mac and Windows.

        Clears any pending keyboard input from the stdin buffer.

        Args:
            None.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """
    import os, sys

    if os.name == 'posix':  # Unix/Linux/Mac
        import termios
        termios.tcflush(sys.stdin, termios.TCIFLUSH)
    elif os.name == 'nt':  # Windows
        import msvcrt
        while msvcrt.kbhit():
            msvcrt.getch()

    return

############################################################
def run(
    cmd: str,  # Command to execute.
    work_dir: str = None,  # Working directory.
    env: dict = None,  # 2nd (current) env to update global ENV.
    envs: dict = None,  # 1st level of env to update global ENV.
    genv: dict = None,  # Global ENV (force in the end).
    os_env: dict = os.environ,  # Environment variables to inject into the subprocess.
    capture_output: bool = False,  # False by default.
    text_cmd: str = 'RUN',  # Text prefix for command display.
    timeout: int = None,  # None by default. TBD: Current timeout doesn't terminate subprocesses.
    verbose: bool = False,  # If True, print extra info.
    hide_in_cmd: list = None,  # List of keys in CMD to hide (for secrets).
    hide_in_env: list = None,  # List of keys in ENV to hide (for secrets).
    save_script: str = '',  # Save script for reproducibility.
    run_script: bool = False,  # Run created script (useful for pipes).
    script_prefix: str = '',  # Add prefix string to script.
    skip_run: bool = False,  # If True, skip run.
    print_cmd: bool = False,  # If True, force print CMD.
    con: bool = False,  # If True, enable console output.
    fail_on_error: bool = False,  # If True, raise exception on error.
    logger = None,  # Optional logger for debug messages.
    space = '',  # Optional indentation prefix for console output formatting.
    capture_env: bool = False,  # If True, capture and return environment changes produced by the command.
    print_env_keys: list = None,  # Environment variable keys to print after execution.
    print_extra_line: bool = False,  # If True, print an extra blank line in console output.
    print_cur_dir: bool = False, # If True, print current directory before running command.
    open_shell: bool = False, # Open shell instead of running command.
    pack_existing_env_values: bool = False, # If part of new value is the same as value in existing env, 
                                            # substitute it with new:${key}
    print_env_with_os_sep_on_new_lines: bool = True, # If True, separate env print with os sep on new lines
):
    """
        Run CMD with environment.

        Args:
            cmd (str): Command to execute.
            work_dir (str | None): Working directory.
            env (dict | None): 2nd (current) env to update global ENV.
            envs (dict | None): 1st level of env to update global ENV.
            genv (dict | None): Global ENV (force in the end).
            capture_output (bool): False by default.
            text_cmd (str): Text prefix for command display.
            timeout (int | None): None by default. TBD: Current timeout doesn't terminate subprocesses.
            verbose (bool): If True, print extra info.
            hide_in_cmd (list | None): List of keys in CMD to hide (for secrets).
            hide_in_env (list | None): List of keys in ENV to hide (for secrets).
            save_script (str): Save script for reproducibility.
            run_script (bool): Run created script (useful for pipes).
            script_prefix (str): Add prefix string to script.
            skip_run (bool): If True, skip run.
            print_cmd (bool): If True, force print CMD.
            con (bool): If True, enable console output.
            fail_on_error (bool): If True, raise exception on error.
            logger: Optional logger for debug messages.

            os_env (dict): Environment variables to inject into the subprocess.
            space: Optional indentation prefix for console output formatting.
            capture_env (bool): If True, capture and return environment changes produced by the command.
            print_env_keys (list): Environment variable keys to print after execution.
            print_extra_line (bool): If True, print an extra blank line in console output.
            print_cur_dir (bool): If True, print current directory before running command
        Returns:
            dict: Unified output with 'return', 'returncode', 'stdout', 'stderr'.

        Raises:
            Exception: Propagated runtime errors, if any.
    """

    import subprocess
    import os
    import platform

    if not con: verbose = False

    cur_dir = os.getcwd()

    if work_dir is not None:
        if not os.path.isdir(work_dir):
            return {'return':1, 'error':f'Directory doesn\'t exist: {work_dir}'}
        os.chdir(work_dir)

    cur_dir2 = os.getcwd()

    # Initialize mutable defaults
    if env is None:
        env = {}
    if envs is None:
        envs = {}
    if genv is None:
        genv = {}
    if hide_in_cmd is None:
        hide_in_cmd = []
    if hide_in_env is None:
        hide_in_env = []

    # Just in case, check if input comes from CMD
    if timeout is not None:
        timeout = int(timeout)

    bat_ext = '.bat' if os.name == 'nt' else '.sh'

    if run_script:
        if save_script == '':
            save_script = 'cmeta-run' + bat_ext

    if save_script and save_script.endswith('{{file_ext_bat}}'):
        save_script = save_script.replace('{{file_ext_bat}}', bat_ext)

    cur_env = {} if not os_env else os_env.copy()

    for e in [envs, env, genv]:
        for k in e:
            v = e[k]

            if type(v) == list:
                v = os.pathsep.join(v)
            elif v is not None:
                v = str(v)

            if k.startswith('+'):
                if v != '':
                    k = k[1:].strip()
                    v1 = cur_env.get(k, '')
                    if v1 != '':
                        if not v.endswith(os.pathsep):
                            v += os.pathsep
                        v += v1
                else:
                    v = None

            if v is not None:
                cur_env[k] = v

    temp_file_to_collect_env = None
    if capture_env:
        r = files.gen_temp_filepath()
        if r['return']>0: return r
        temp_file_to_collect_env_before = r['filepath']

        r = files.gen_temp_filepath()
        if r['return']>0: return r

        temp_file_to_collect_env_after = r['filepath']

        x = 'set' if os.name == 'nt' else 'env'

        xcmd = f'{x} > {temp_file_to_collect_env_before} && '

        if cmd != '':
            xcmd += cmd + ' && '

        xcmd += f'{x} > {temp_file_to_collect_env_after}'

        cmd = xcmd

    env1 = '%' if platform.system() == "Windows" else '${'
    env2 = '%' if platform.system() == "Windows" else '}'

    print_env = {}
    if print_env_keys is None:
        print_env_keys = cur_env.keys()

    for k in print_env_keys:
        if k in cur_env:
            v = str(cur_env[k])
            if k not in os_env or str(os_env[k]) != str(v):
               if pack_existing_env_values and k in os_env:
                  vv = str(os_env[k])
                  j = v.find(vv)
                  if j>=0:
                     v = v[:j] + env1 + k + env2
               print_env[k] = v

    script = ''
    if save_script != '':
        script = '@echo off\n' if os.name == 'nt' else '#!/bin/bash\n'


        cur_dir2 = files.quote_path(cur_dir2)
        x = '/d ' if os.name == 'nt' else ''
        script += f'\ncd {x}{cur_dir2}\n'

        if script_prefix != '':
            script += '\n' + script_prefix

    if len(print_env) > 0:
        if verbose:
            print('')

        if save_script != '':
            script += '\n'

        for k in sorted(print_env):
            v = print_env[k]

            if verbose:
                vx = v if k not in hide_in_env else '***'

                if print_env_with_os_sep_on_new_lines and os.pathsep in vx:
                    print(f'{space}ENV {k}:')

                    for x in vx.split(os.pathsep):
                        if x:
                            print (f'{space}      - {x}')

                else:
                    print(f'{space}ENV {k}={vx}')

            if save_script != '':
                if os.name == 'nt':
                    x = 'set'
                    vv = v
                else:
                    x = 'export'
                    vv = v if ' ' not in v else '"' + v + '"'

                script += f'{x} {k}={vv}\n'

        if save_script != '':
            script += '\n'

    returncode = 0
    stdout = ''
    stderr = ''

    # Hide secrets from CMD
    xcmd = cmd
    for h in hide_in_cmd:
        j = xcmd.find(h)
        if j >= 0:
            j1 = xcmd.find(' ', j + len(h))
            if j1 < 0:
                j1 = len(xcmd)
            if j1 >= 0:
                xcmd = xcmd[:j+len(h)] + '***' + xcmd[j1:]

    if verbose and print_cur_dir:
        print('')
        print (f'{space}PWD: {cur_dir}')


    if verbose or print_cmd:
        print('')

        if skip_run:
            print (f'{space}SKIP {xcmd}')
        else:
            print (f'{space}{text_cmd} {xcmd}')

    elif con:
        print ('')
        print (f'{space}{xcmd}')


    if save_script is not None and save_script != '':
        script += cmd + '\n'

        # Note: This assumes utils.save_txt exists in your codebase
        # You may need to import or implement this function
        r=files.write_file(save_script, script, fail_on_error=fail_on_error, logger=logger, file_format="text")
        if r['return'] > 0:
            return r

    if run_script:
        if os.name == 'nt':
            cmd = f'call {save_script}'
        else:
            x = '' if save_script.startswith('.') or save_script.startswith('/') else '. ./'
            cmd = f'bash -c "{x}{save_script}"'

        if verbose:
            x = 'SKIP ' if skip_run else ''
            print('')
            print(f'{space}{x}{text_cmd} {cmd}')

    is_windows = os.name == 'nt'

    if open_shell:
        if con:
            print ('')
            print (f'{space}INFO: Opening shell for testing and debugging. Exiting shell will resume cMeta workflow execution:')
            print ('')

        if is_windows:
            shell_cmd = ["cmd.exe"]
        else:
            shell_cmd = [os.environ.get("SHELL", "/bin/sh")]

        subprocess.run(shell_cmd, env = cur_env)

        if con:
            print ('')
            print (f'{space}INFO: Returned to cMeta workflow. Continue executing ...')
            print ('')

    if not skip_run:
        if con and print_extra_line:
            print ('')

        try:
            use_popen = (timeout is not None and not is_windows)

            if use_popen:
                # ----- UNIX: custom Popen + process group handling -----
                import signal
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE if capture_output else None,
                    stderr=subprocess.PIPE if capture_output else None,
                    text=True,
                    shell=True,
                    env=cur_env,
                    preexec_fn=os.setsid
                )

                try:
                    stdout, stderr = process.communicate(timeout=timeout)
                    returncode = process.returncode

                except subprocess.TimeoutExpired:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    stdout, stderr = process.communicate()
                    returncode = -1

            else:
                # ----- Windows with timeout: delegate to your wrapper -----
                if timeout is not None and is_windows:
                    returncode, stdout, stderr = run_command_with_timeout_tree_kill_on_windows(
                        cmd=cmd,
                        capture_output=capture_output,
                        cur_env=cur_env,
                        timeout=timeout,
                        shell=True,
                        text=True,
                    )

                # ----- Normal subprocess.run (any OS) -----
                else:
                    result = subprocess.run(
                        cmd,
                        capture_output=capture_output,
                        text=True,
                        shell=True,
                        env=cur_env,
                        timeout=timeout,
                    )
                    returncode = result.returncode
                    stdout = result.stdout if capture_output else ''
                    stderr = result.stderr if capture_output else ''

        except Exception as e:
            stdout = ''
            stderr = format(e)
            returncode = -1

        if returncode != 0 and stderr != '' and verbose:
             print ('')
             print (f'{space}WARNING: Command failed: {stderr}')

    if work_dir is not None:
        os.chdir(cur_dir)

    result = {'return': 0, 'returncode': returncode, 'stdout': stdout, 'stderr': stderr, 'cur_env': cur_env}

    # Check if collect env
    if capture_env:
        r = files.read_file(temp_file_to_collect_env_before, fail_on_error = fail_on_error, logger = logger)
        if r['return']>0: 
            return _error(f'Capture env output file not found (before): {temp_file_to_collect_env_before}', 1, None, fail_on_error)

        try:
            os.remove(temp_file_to_collect_env_before)
        except Exception as e:
            pass

        r = files.parse_env_dump(r['data'])
        if r['return']>0: return r

        collected_env_before = r['env']

        r = files.read_file(temp_file_to_collect_env_after, fail_on_error = fail_on_error, logger = logger)
        if r['return']>0: 
            return _error(f'Capture env output file not found (after): {temp_file_to_collect_env_after}', 1, None, fail_on_error)

        try:
            os.remove(temp_file_to_collect_env_after)
        except Exception as e:
            pass

        r = files.parse_env_dump(r['data'])
        if r['return']>0: return r

        collected_env_after = r['env']

        result['collected_env_before'] = collected_env_before
        result['collected_env_after'] = collected_env_after

        r = files.diff_env(collected_env_before, collected_env_after)
        if r['return']>0: return r

        result['env_added'] = r['env_added']
        result['env_removed'] = r['env_removed']

    return result

###################################################################################################
def run_command_with_timeout_tree_kill_on_windows(
    cmd: str,  # Command string to execute.
    capture_output: bool,  # If True, capture stdout and stderr.
    cur_env: dict,  # Environment variables dictionary.
    timeout: float,  # Timeout in seconds.
    shell: bool = True,  # If True, run command through shell.
    text: bool = True,  # If True, decode output as text.
):
    """
        Run command on Windows with timeout and process tree termination.

        Uses Windows Job Objects to ensure entire process tree is killed on timeout.

        Args:
            cmd (str): Command string to execute.
            capture_output (bool): If True, capture stdout and stderr.
            cur_env (dict): Environment variables dictionary.
            timeout (float): Timeout in seconds.
            shell (bool): If True, run command through shell.
            text (bool): If True, decode output as text.

        Returns:
            tuple: (returncode, stdout, stderr).

        Raises:
            OSError: If Windows API calls fail.
    """
    import subprocess
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32

    # Constants
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JobObjectExtendedLimitInformation = 9

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
            ("PerJobUserTimeLimit",     wintypes.LARGE_INTEGER),
            ("LimitFlags",              wintypes.DWORD),
            ("MinimumWorkingSetSize",   ctypes.c_size_t),
            ("MaximumWorkingSetSize",   ctypes.c_size_t),
            ("ActiveProcessLimit",      wintypes.DWORD),
            ("Affinity",                ctypes.c_size_t),
            ("PriorityClass",           wintypes.DWORD),
            ("SchedulingClass",         wintypes.DWORD),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount",   ctypes.c_ulonglong),
            ("WriteOperationCount",  ctypes.c_ulonglong),
            ("OtherOperationCount",  ctypes.c_ulonglong),
            ("ReadTransferCount",    ctypes.c_ulonglong),
            ("WriteTransferCount",   ctypes.c_ulonglong),
            ("OtherTransferCount",   ctypes.c_ulonglong),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo",                IO_COUNTERS),
            ("ProcessMemoryLimit",    ctypes.c_size_t),
            ("JobMemoryLimit",        ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed",     ctypes.c_size_t),
        ]

    # (Optional but nice) declare arg/return types
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype  = wintypes.HANDLE

    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, wintypes.INT, wintypes.LPVOID, wintypes.DWORD
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL

    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype  = wintypes.BOOL

    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateJobObject.restype  = wintypes.BOOL

    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype  = wintypes.BOOL

     # --- Windows + timeout: use a Job Object ---
    # Create job object
    hjob = kernel32.CreateJobObjectW(None, None)
    if not hjob:
        raise OSError("CreateJobObjectW failed")

    try:
        # Configure "kill on job close"
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

        ok = kernel32.SetInformationJobObject(
            hjob,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            raise OSError("SetInformationJobObject failed")

        # Start the process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=text,
            shell=shell,
            env=cur_env,
        )

        # Assign to job object so all its children are part of the job
        ok = kernel32.AssignProcessToJobObject(hjob, wintypes.HANDLE(process._handle))
        if not ok:
            # Clean up process if we can't track it via job
            process.kill()
            raise OSError("AssignProcessToJobObject failed")

        try:
            stdout, stderr = process.communicate(timeout=timeout)
            returncode = process.returncode
        except subprocess.TimeoutExpired:
            # Kill whole tree
            kernel32.TerminateJobObject(hjob, 1)
            # Drain pipes after kill
            stdout, stderr = process.communicate()
            returncode = -1  # or choose a sentinel you like
    finally:
        kernel32.CloseHandle(hjob)

    if not capture_output:
        stdout = ""
        stderr = ""

    return returncode, stdout, stderr

###################################################################################################
def format_size(
    size: int,  # Size in bytes to format.
    binary: bool = True,  # If True, use 1024 base with IEC units (KiB, MiB, GiB).
    unit: str = None,  # Force specific unit (e.g., 'MB', 'MiB'). If None, auto-select.
):
    """
        Convert size in bytes to a human-readable string.

        Args:
            size (int): Size in bytes to format.
            binary (bool): If True, use 1024 base with IEC units (KiB, MiB, GiB).
                           If False, use 1000 base with SI units (KB, MB, GB).
            unit (str | None): Force specific unit (e.g., 'MB', 'MiB'). If None, auto-select.

        Returns:
            dict: Dictionary with 'return': 0 and 'nice_size' containing formatted string.

        Raises:
            ValueError: If unit is not valid.
    """

    # Choose base and unit list
    if binary:
        base = 1024
        units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB']
    else:
        base = 1000
        units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB']

    nice_size = None  # final output string

    # ---------------------------------------------------------
    # Forced unit mode
    # ---------------------------------------------------------
    if unit is not None:
        if unit not in units:
            raise ValueError(f"Invalid unit '{unit}'. Must be one of: {units}")
        # Convert based on unit index
        power = units.index(unit)
        value = size / (base ** power)
        nice_size = f"{value:.2f} {unit}"

    else:
        # -----------------------------------------------------
        # Automatic unit selection mode
        # -----------------------------------------------------
        working_size = size  # avoid modifying input
        for current_unit in units:
            if working_size < base:
                nice_size = f"{working_size:.2f} {current_unit}"
                break
            working_size /= base

        # Extremely large values fallback
        if nice_size is None:
            nice_size = f"{working_size:.2f} {units[-1]}"

    return {'return': 0, 'nice_size': nice_size}

###################################################################################################
def get_dir_size(
    path: str,  # Directory path to measure.
    binary: bool = False,  # If True, use binary (1024) units, else decimal (1000).
    unit: str = None,  # Force specific unit for size formatting.
    skip_datetime: bool = False,  # If True, skip datetime conversion fields in the result.
):
    """
        Calculate total size of a directory recursively.

        Walks through directory tree and sums file sizes.

        Args:
            path (str): Directory path to measure.
            binary (bool): If True, use binary (1024) units, else decimal (1000).
            unit (str | None): Force specific unit for size formatting.

            skip_datetime (bool): If True, skip datetime conversion fields in the result.
        Returns:
            dict: Dictionary with 'return': 0, 'size' in bytes, 'nice_size' formatted,
                  'total_dirs' count, 'total_files' count, 'latest_modification_dt',
                  and 'weird_dates' list of files with future modification dates.

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    from datetime import datetime
    
    total = 0
    total_dirs = 0
    total_files = 0

    if not skip_datetime:
        latest_mtime = None
        weird_dates = []
        current_time = datetime.now().timestamp()

    for root, dirs, files in os.walk(path):
        # Count subdirectories at this level
        total_dirs += len(dirs)
        
        # Check modification time of the current directory
        if not skip_datetime:
            try:
                dir_mtime = os.path.getmtime(root)
                if latest_mtime is None or dir_mtime > latest_mtime:
                    latest_mtime = dir_mtime
            except (OSError, PermissionError):
                pass  # Skip directories we can't access

        for f in files:
            fp = os.path.join(root, f)
            if os.path.isfile(fp):  # avoid broken symlinks
                try:
                    total += os.path.getsize(fp)
                    total_files += 1
                    
                    # Check file modification time
                    if not skip_datetime:
                        file_mtime = os.path.getmtime(fp)
                        
                        # Detect files with future modification dates
                        if file_mtime > current_time:
                            weird_dates.append({
                                'path': fp,
                                'mtime': file_mtime,
                                'mtime_dt': datetime.fromtimestamp(file_mtime).isoformat()
                            })
                        
                        if latest_mtime is None or file_mtime > latest_mtime:
                            latest_mtime = file_mtime
                except (OSError, PermissionError):
                    pass  # Skip files we can't access

    r = format_size(total, binary, unit)
    if r['return'] > 0:
        return r

    nice_size = r['nice_size']
    
    result = {
        'return': 0,
        'size': total,
        'nice_size': nice_size,
        'total_dirs': total_dirs,
        'total_files': total_files,
    }

    # Convert timestamp to datetime
    if not skip_datetime:
        result['latest_modification_dt'] = datetime.fromtimestamp(latest_mtime) if latest_mtime is not None else None
        result['weird_dates'] = weird_dates

    return result

###################################################################################################
def get_min_arch_host_info():
    """
        Collect lightweight OS and architecture metadata.

        Args:
            None.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """
    import os
    import platform
    import struct

    python_bits = struct.calcsize("P") * 8
    system = platform.system()
    system_lower = system.lower()

    cpu_arch = platform.machine()

    if system_lower == "windows":
        os_bits = 64 if os.environ.get("PROCESSOR_ARCHITEW6432") else python_bits
    elif system_lower == "darwin":
        os_bits = 64
    else:  # Linux / Unix
        os_bits = 64 if cpu_arch.endswith("64") else 32

    return {
        "return": 0,
        "os": system,                       # Windows, Linux, Darwin
        "os_lower": system.lower(),
        "os_release": platform.release(),   # OS version
        "os_version": platform.version(),   # Detailed version
        "python_bits": python_bits,
        "os_bits": os_bits,
        "cpu_arch": cpu_arch,               # x86_64, AMD64, arm64, aarch64, etc.
        "cpu_arch_lower": cpu_arch.lower(),
    }


###################################################################################################
def get_min_raw_host_info():
    """
        Collect minimal host hardware information including CPU and memory.

        Args:
            None.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """
    import psutil
    import os
    import platform
    import sys
    import struct

    result = get_min_arch_host_info()
    if result['return']>0: return result

    # --- Number of CPU cores ---
    physical_cores = psutil.cpu_count(logical=False)
    logical_cores = psutil.cpu_count(logical=True)

    mem_info = psutil.virtual_memory()
    total_memory = mem_info.total
    free_memory = mem_info.available

    # --- Memory used by the current Python process ---
    process = psutil.Process(os.getpid())
    memory_used = process.memory_info().rss  # bytes

    result.update({
      'physical_cores': physical_cores,
      'logical_cores': logical_cores,
      'total_memory': total_memory,
      'free_memory': free_memory,
      'memory_used': memory_used,
    })

    return result

###################################################################################################
def get_min_host_info(
    only_memory: bool = False,  # If True, only return memory information.
    binary: bool = False,  # If True, use binary (1024) units for memory sizes.
    unit: str = 'GB',  # Unit for memory size formatting (default: 'GB').
    con: bool = False,  # If True, print information to console.
    line: int = 0,  # Prefix line index used for structured console output.
    self_time: bool = False,  # If True, include self-timing information in console output.
    space = '',  # Optional indentation prefix for console output formatting.
):
    """
        Get minimal host system information including CPU and memory.

        Retrieves system information including CPU core counts, total memory,
        free memory, and current process memory usage.

        Args:
            only_memory (bool): If True, only return memory information.
            binary (bool): If True, use binary (1024) units for memory sizes.
            unit (str): Unit for memory size formatting (default: 'GB').
            con (bool): If True, print information to console.

            line (int): Prefix line index used for structured console output.
            self_time (bool): If True, include self-timing information in console output.
            space: Optional indentation prefix for console output formatting.
        Returns:
            dict: Dictionary with 'return': 0 and host information including:
                  'physical_cores' (int): Number of physical CPU cores.
                  'logical_cores' (int): Number of logical CPU cores.
                  'total_memory' (int): Total system memory in bytes.
                  'nice_total_memory' (str): Formatted total memory string.
                  'free_memory' (int): Free system memory in bytes.
                  'nice_free_memory' (str): Formatted free memory string.
                  'memory_used' (int): Memory used by current process in bytes.
                  'nice_memory_used' (str): Formatted process memory string.
                  'self_time' (float): Execution time in seconds.
                  'nice_self_time' (str): Formatted execution time.
                  'string' (str): Formatted output for display.

        Raises:
            Exception: Propagated runtime errors, if any.
    """

    import time

    start_time = time.time()

    result = get_min_raw_host_info()
    if result['return']>0: return result

    # --- Total system memory ---
    total_memory = result['total_memory']
    free_memory = result['free_memory']

    # --- Number of CPU cores ---
    physical_cores = result['physical_cores']
    logical_cores = result['logical_cores']

    # --- Memory used by the current Python process ---
    memory_used = result['memory_used']

    r = format_size(total_memory, binary=binary, unit=unit)
    if r['return']>0: return r
    nice_total_memory = r['nice_size']

    r = format_size(free_memory, binary=binary, unit=unit)
    if r['return']>0: return r
    nice_free_memory = r['nice_size']

    r = format_size(memory_used, binary=binary, unit=unit)
    if r['return']>0: return r
    nice_memory_used = r['nice_size']

    x = ''

    if line>0:
        x += '='*line + '\n'

    if not only_memory:
        x += (f"{space}Host physical cores: {physical_cores}\n"
              f"{space}Host logical cores: {logical_cores}\n")

    x += (f"{space}Host total memory: {nice_total_memory}\n"
        f"{space}Host free memory: {nice_free_memory}\n"
        f"{space}Memory used by current process: {nice_memory_used}\n")

    end_time = time.time()
    self_time = end_time - start_time
    nice_self_time = f"{self_time:.3f} sec."

    if self_time:
        x += f"{space}Time to obtain system info: {nice_self_time}\n"

    if con:
        print (x)

    result.update({
      'nice_total_memory': nice_total_memory,
      'nice_free_memory': nice_free_memory,
      'nice_memory_used': nice_memory_used,
      'string': x,
      'self_time': self_time,
      'nice_self_time': nice_self_time
    })
    
    return result

##########################################################################################
def get_disk_space(
    path: str,  # Path to check disk space for.
    nice: bool = False,  # If True, return human-readable sizes with 'nice_*' keys.
    binary: bool = False,  # If True, use binary (1024) units, else decimal (1000).
    unit: str = None,  # Force specific unit for size formatting (e.g., 'GB', 'GiB').
    line: int = 0,  # Prefix line index used for structured console output.
    self_time: bool = False,  # If True, include self-timing information in console output.
    space = '',  # Optional indentation prefix for console output formatting.
):
    """
        Get disk space information for a given path.

        Retrieves total, used, and free disk space for the filesystem containing
        the specified path.

        Args:
            path (str): Path to check disk space for.
            nice (bool): If True, return human-readable sizes with 'nice_*' keys.
            binary (bool): If True, use binary (1024) units, else decimal (1000).
            unit (str | None): Force specific unit for size formatting (e.g., 'GB', 'GiB').

            line (int): Prefix line index used for structured console output.
            self_time (bool): If True, include self-timing information in console output.
            space: Optional indentation prefix for console output formatting.
        Returns:
            dict: Dictionary with 'return': 0 and:
                  'total' (int): Total disk space in bytes.
                  'used' (int): Used disk space in bytes.
                  'free' (int): Free disk space in bytes.
                  'self_time' (float): Execution time in seconds.
                  'nice_self_time' (str): Formatted execution time.
                  If nice=True, also includes:
                  'nice_total' (str): Formatted total size.
                  'nice_used' (str): Formatted used size.
                  'nice_free' (str): Formatted free size.

        Raises:
            Exception: Propagated runtime errors, if any.
    """

    from shutil import disk_usage
    import time

    start_time = time.time()

    usage = disk_usage(path)

    result = {
        'return':0, 
        'total': usage.total,
        'used': usage.used,
        'free': usage.free
    }

    if nice:
        x = ''

        if line>0:
            x += space + '='*line + '\n'

        x += f'{space}Path: {path}\n'
        for key in ['total', 'used', 'free']:
            size = result[key]

            r = format_size(size, binary, unit)
            if r['return']>0: return r

            nice_size = r['nice_size']

            result['nice_'+key] = nice_size

            x += space + key.capitalize() + f' size: {nice_size}\n'

        end_time = time.time()
        self_time = end_time - start_time
        nice_self_time = f"{self_time:.3f} sec."

        if self_time:
            x += f"{space}Time to obtain disk space: {nice_self_time}\n"

        result['string'] = x

    end_time = time.time()
    self_time = end_time - start_time
    nice_self_time = f"{self_time:.3f} sec."

    if nice:
        x += f"{space}Self time: {nice_self_time}\n"

    result['self_time'] = self_time
    result['nice_self_time'] = nice_self_time

    return result

##########################################################################################
def plus_env(
    env,  # Environment variable mapping.
):
    """
        If key starts with + and value is not list, convert to list as path

        Args:
            env: Environment variable mapping.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """

    for k in list(env.keys()):
        if k.startswith('+'):
            v = env[k]
            if type(v) != list:
                env[k] = v.split(os.pathsep)

    return {'return':0}
