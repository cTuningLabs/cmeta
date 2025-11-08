"""
Common reusable functions

cMeta author and developer: (C) 2025 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

from .common import _error
from .cli import print_params_help

###################################################################################################
def load_module(module_path, module_cache, fail_on_error=False, category=False, cmeta=None):
    """
    Load a Python module as part of a package, with caching and timestamp checking.

    Parameters:
        module_path (str): Full path to the Python module file (e.g., .../mypackage/module1.py)
        module_cache (dict): Cache dictionary with module paths as keys
        fail_on_error (bool): If True, raises exceptions instead of returning error dict
        category (bool): If True, initialize category

    Returns:
        dict: {'return': 0, 'module': module} on success
              {'return': 1, 'error': error_message} on failure (if fail_on_error=False)
    """
    import os
    import sys
    import importlib
    import traceback

    # Check if file exists
    if not os.path.isfile(module_path):
        return _error(f'Module file not found: {module_path}', 16, None, fail_on_error)

    # Determine paths
    module_path = os.path.abspath(module_path)
    module_dir = os.path.dirname(module_path)
    package_name = os.path.basename(module_dir)
    package_root = os.path.dirname(module_dir)
    module_name = os.path.splitext(os.path.basename(module_path))[0]

    full_module_name = f"{package_name}.{module_name}"

    # Get api modification timestamp
    current_timestamp = os.path.getmtime(module_path)

    # Check cache
    if module_path in module_cache:
        cached_data = module_cache[module_path]
        if cached_data.get('timestamp') == current_timestamp:
            return {'return':0, 'cache': cached_data}

    # Load using importlib
    must_remove = False
    try:
        parent_dir = os.path.dirname(module_dir)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
            must_remove = True

        module = importlib.import_module(full_module_name)

        cache = {
            'python_module': module,
            'timestamp': current_timestamp
        }

        if category:
            cache['initialized_class'] = module.Category(cm=cmeta)

        # Update cache
        module_cache[module_path] = cache

        return {'return':0, 'cache':module_cache[module_path]}

    except Exception as e:
        return _error(f'Failed to import module {full_module_name} from {module_path}', 1, e, fail_on_error)

    finally:
        if must_remove and parent_dir in sys.path:
            sys.path.remove(parent_dir)

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

