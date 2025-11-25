"""
Common reusable functions

cMeta author and developer: (C) 2025 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
from .common import _error
from .cli import print_params_help

def load_module(module_path, module_cache, fail_on_error=False, category=False, cmeta=None):
    import os, sys, importlib.util, importlib.machinery, re, hashlib

    def sanitize(name):
        cleaned = re.sub(r'[^0-9a-zA-Z_]', '_', name)
        if re.match(r'^\d', cleaned):
            cleaned = "_" + cleaned
        if cleaned != name or cleaned.strip("_") == "":
            suffix = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
            cleaned = f"{cleaned}_{suffix}"
        return cleaned

    if not os.path.isfile(module_path):
        return _error(f'Module file not found: {module_path}', 16, None, fail_on_error)

    module_path = os.path.abspath(module_path)
    module_dir = os.path.dirname(module_path)            # .../api
    module_name = os.path.splitext(os.path.basename(module_path))[0]

    category_dir = os.path.dirname(module_dir)           # .../java.1
    raw_cat = os.path.basename(category_dir)
    raw_pkg = os.path.basename(module_dir)

    cat_name = sanitize(raw_cat)
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

        if category:
            cache_data["initialized_class"] = module.Category(cm=cmeta)

        module_cache[module_path] = cache_data
        return {"return": 0, "cache": cache_data}

    except Exception as e:
        return _error(f"Failed to import module {full_module_name}", 1, e, fail_on_error)

###################################################################################################
def find_command_func(category_api, command):

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
def get_func_properties(f):
    """Get function properties"""

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
def find_func_definition(obj, name):
    """Find function definitiion"""
    import inspect

    func = getattr(obj.__class__, name, None)
    if func is None:
        return {'return':1, 'error':f'function "{name}" not found in {obj.__class__.__name__}'}

    # Unwrap in case it's decorated
    func = inspect.unwrap(func)

    return get_func_properties(func)



###################################################################################################
def get_api_info(category_api, command, full_command, control_params_desc = None, category_apis = []):
    """Extract function definition and docstring for API information
    
    Args:
        category_api: The category API object
        command: The command name
        category_api_path: Path to the category API file
        
    Returns:
        Dictionary with {"return": 0, "api_info": "formatted API info string"} for success
        or {"return": >0, "error": "error text"} for errors
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
def get_api_text(lines, start_line):

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
def run(cmd, 
        work_dir=None,
        env=None, 
        envs=None, 
        genv=None, 
        capture_output=False, 
        text_cmd='$',
        timeout=None, 
        verbose=False, 
        hide_in_cmd=None, 
        save_script='', 
        run_script=False, 
        script_prefix='', 
        skip_run=False, 
        print_cmd=False,
        con=False,
        fail_on_error=False,
        logger=None):
    """
    Run CMD with environment

    Input:
        cmd (str): command to execute
        envs (dict): 1st level of env to update global ENV
        env (dict): 2nd (current) env to update global ENV
        genv (dict): global ENV (force in the end)
        capture_output (bool): False by default
        timeout (int): None by default
                       TBD: Current timeout doesn't terminate subprocesses
                       need to use POpen.
        verbose (bool): if True, print extra info
        hide_in_cmd (list): list keys in CMD to hide (for secrets)
        save_script (str): save script for reproducibility
        run_script (bool): run create script (useful for pipes)
        script_prefix (str): add prefix string to script
        skip_run (bool): if True, skip run
        print_cmd (bool): if True, force print CMD
        con (bool): if True, enable console output

    Output:
        dict: unified CM output
            * return (int): 0 if success
            * returncode (int): command return code
            * stdout (str): standard output
            * stderr (str): standard error
            * (error) (str): error string if return > 0
    """

    import subprocess
    import os

    if work_dir is not None:
        if not os.path.isdir(work_dir):
            return {'return':1, 'error':f'Directory doesn\'t exist: {work_dir}'}
        cur_dir = os.getcwd()
        os.chdir(work_dir)

    # Initialize mutable defaults
    if env is None:
        env = {}
    if envs is None:
        envs = {}
    if genv is None:
        genv = {}
    if hide_in_cmd is None:
        hide_in_cmd = []

    # Just in case, check if input comes from CMD
    if timeout is not None:
        timeout = int(timeout)

    if run_script:
        if save_script == '':
            save_script = 'cmeta-run.bat' if os.name == 'nt' else 'cmeta-run.sh'

    cur_env = os.environ.copy()

    print_env = {}

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
                        v += os.pathsep + v1
                else:
                    v = None

            if v is not None:
                cur_env[k] = v

                if con:
                    print_env[k] = v

    if save_script != '':
        script = '@echo off\n' if os.name == 'nt' else '#!/bin/bash\n'

        if script_prefix != '':
            script += '\n' + script_prefix

    if len(print_env) > 0:
        if verbose:
            print('')

        if save_script != '':
            script += '\n'

        for k in print_env:
            v = print_env[k]

            if verbose:
                print(f'ENV {k}={v}')

            if save_script != '':
                x = 'set' if os.name == 'nt' else 'export'
                vv = v if ' ' not in v else '"' + v + '"'
                script += f'{x} {k}={vv}\n'

        if save_script != '':
            script += '\n'

    returncode = 0
    stdout = ''
    stderr = ''
    script = ''

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

    if verbose or print_cmd:
        print('')

        if skip_run:
            print (f'SKIP {xcmd}')
        else:
            print (f'{text_cmd} {xcmd}')

        print ('')

    elif con:
        print ('')
        print (f'{xcmd}')
        print ('')


    if save_script is not None and save_script != '':
        script += cmd + '\n'

        # Note: This assumes utils.save_txt exists in your codebase
        # You may need to import or implement this function
        from . import files
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
            print(f'{x}RUN {cmd}')

    if not skip_run:
        try:
            is_windows = os.name == 'nt'
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

        if returncode>0 and stderr != '' and verbose:
             print ('')
             print (f'Command failed: {stderr}')

    if work_dir is not None:
        os.chdir(cur_dir)

    return {'return': 0, 'returncode': returncode, 'stdout': stdout, 'stderr': stderr}

def run_command_with_timeout_tree_kill_on_windows(
    cmd,
    capture_output: bool,
    cur_env,
    timeout: float | None,
    shell: bool = True,
    text: bool = True,
):
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
