"""
Reusable functions for CLI

cMeta author and developer: (C) 2025 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

from typing import Dict, Any, List, Optional

from .files import safe_read_file
from .common import deep_merge, _error

def parse_cmd(
        cmd,                      # Command string to parse, list of arguments, or None
        fail_on_error: bool = False  # If True, raise exception on error
):
    """
    Parse command line string or argument list into a structured dictionary.
    
    Supports various argument formats:

    - Positional arguments: stored in 'positional_arguments' list
    - Flags: --key=value, -key=value, key=value
    - Boolean flags: --key (True), --key- (False), --no-key (False)
    - List flags: --key, (creates list)
    - Nested keys: --parent.child=value
    - File inclusion: @filename (loads JSON/YAML)
      Note: On Windows, wrap file paths in double quotes if they contain backslashes (\\) 
      to prevent shlex.split() from interpreting them as escape characters.
    - Argument separator: -- (remaining args go to 'unparsed')
    
    Args:
        cmd: Command string to parse, list of arguments, or None.
        fail_on_error (bool): If True, raise exception on error.
        
    Returns:
        dict: Dictionary with keys:
        - 'return': 0 for success, >0 for error
        - 'params': Dictionary of parsed flags and values (may include "args" and "unparsed")
        - 'error': Error message (only present if return > 0).
    """

    if cmd is None:
        cmd = []
    elif isinstance(cmd, str):
        import shlex
        cmd = shlex.split(cmd)
    else:
        import copy
        cmd = copy.deepcopy(cmd)

    # Initialize 
    params = {}

    # Process each argument
    for index, argument in enumerate(cmd):
        
        # Handle argument separator
        if argument == '--':
            params['unparsed'] = cmd[index + 1:] if index < len(cmd) - 1 else []
            break

        # Handle file inclusion (@filename)
        elif argument.startswith('@'):
            filename = argument[1:]
            delete_after_read = filename.startswith('@')
            if delete_after_read:
                filename = filename[1:]  # Remove the second @

            r = safe_read_file(filename, fail_on_error=fail_on_error, retry_if_not_found=1)
            if r['return'] > 0: return r

            file_params = r['data']

            deep_merge(params, file_params, append_lists=False)
            
            # Delete file if it started with @@
            if delete_after_read:
                try:
                    import os
                    os.remove(filename)
                except Exception as e:
                    return _error(f'Failed to delete temporary file "{filename}"', 1, e, fail_on_error)

        # Handle invalid triple-dash flags
        elif argument.startswith('---'):
            return _error(f'Flag "{argument}" has unknown prefix "---"', 1, None, fail_on_error)
        # Handle double-dash flags (--key=value)
        elif argument.startswith('-'):
            flag_content = argument[2:] if argument.startswith('--') else argument[1:]
            
            # Handle --no-key format (sets key to False)
            if flag_content.startswith('no-') and '=' not in flag_content and not flag_content.endswith('-'):
                actual_key = flag_content[3:]  # Remove 'no-' prefix
                if actual_key:  # Make sure there's actually a key after 'no-'
                    r = split_flag(actual_key, params, False, fix_keys=True)
                    if r['return']>0: return r
                else:
                    return _error(f'Invalid flag format: "{argument}" - missing key after "no-"', 1, None, fail_on_error)
            else:
                # This will handle --key-, --key, --key=value formats
                r = split_flag(flag_content, params, fix_keys=True)
                if r['return']>0: return r

        # Handle non-flag arguments
        else:
            # Check if it's a key=value pair without dashes
            if '=' in argument:
                r = split_flag(argument, params, fix_keys=True)
                if r['return']>0: return r
            else:
                # It's a positional argument
                if params.get('args') is None:
                    params['args'] = []
                params['args'].append(argument)

    return {
        'return': 0, 
        'params': params 
    }


def split_flag(
        *args,   # Positional arguments passed to _split_flag
        **params  # Keyword arguments passed to _split_flag
):
    """Wrapper for _split_flag that handles exceptions.
    
    Args:
        *args: Positional arguments passed to _split_flag.
        **params: Keyword arguments passed to _split_flag.
        
    Returns:
        dict: Dictionary with 'return': 0 and 'split_flag' tuple, or 'return' > 0 and 'error'.
    """
    try:
        key, value, updated_array = _split_flag(*args,**params)
    except Exception as e:
        return {'return': 1, 'error': f"Error parsing flags: {e}"}

    return {'return': 0, 'split_flag': (key, value, updated_array)}


def _split_flag(flag: str, array: dict, value: Optional[str] = None, fix_keys = False) -> tuple[str, any, dict]:
    """
    Parse a command-line flag and add it to the given dictionary.
    
    Supports multiple formats:

    - key=value: Sets key to value
    - key: Sets key to True
    - key-: Sets key to False (trailing dash)
    - key,: Creates a list value (trailing comma)
    - nested.key: Creates nested dictionary structure
    
    Args:
        flag: Command-line flag string to parse
        array: Dictionary to store the parsed key-value pair
        value: Optional pre-determined value (for "-key value" style flags or --no-key format)
    
    Returns:
        tuple: (parsed_key, parsed_value, updated_array)
    """
    
    # Parse key=value format
    equals_index = flag.find('=')  # Find first equals sign
    if equals_index > 0:
        key = flag[:equals_index].strip()
        parsed_value = flag[equals_index + 1:].strip()
    else:
        key = flag
        if value is None:
            # Handle boolean flags: 'key-' becomes False, 'key' becomes True
            if key.endswith('-'):
                key = key[:-1]
                parsed_value = False
            else:
                parsed_value = True
        else:
            parsed_value = value

    # Handle list creation (trailing comma)
    if key.endswith(','):
        key = key[:-1]  # Remove trailing comma
        if parsed_value in [True, False]:
            parsed_value = [parsed_value]
        elif parsed_value != '':
            parsed_value = parsed_value.split(',')
        else:
            parsed_value = []

    # Handle nested dictionary keys (dot notation)
    if '.' in key:
        key_parts = key.split('.')
        current_dict = array
        
        # Navigate/create nested structure
        root_key = True
        for nested_key in key_parts[:-1]:
            if root_key and fix_keys:
                nested_key = nested_key.replace('-', '_')
            if nested_key not in current_dict:
                current_dict[nested_key] = {}
            current_dict = current_dict[nested_key]
            root_key = False
        
        # Set the final value
        if not isinstance(current_dict, dict):
            raise TypeError(f"{current_dict} must be a dict, not {type(current_dict).__name__}")

        current_dict[key_parts[-1]] = parsed_value
    else:
        # Simple key-value assignment
        if fix_keys:
            key = key.replace('-', '_')
        array[key] = parsed_value

    return key, parsed_value, array


def check_params(params, params_description, fail_on_error = False) -> Dict[str, Any]:
    """
    Check and validate input dictionary based on input description.
    Convert aliases to keys and validate types.
    
    Args:
        params: Input dictionary to validate
        params_description: List of configuration dictionaries with keys, types, etc.
        
    Returns:
        Dictionary with:
        - return: 0 for success, >0 for error
        - checked_params: Dictionary with validated and converted values for the group
        - remaining_params: Dictionary with remaining keys not in the group
        - error: Error message (only present if return > 0)
    """
    
    # Build lookup for keys and their aliases
    key_lookup = {}  # maps alias -> config_item
    all_group_keys = set()  # all keys that belong to this group
    
    for config_item in params_description:
        if config_item is not None:
            key = config_item['key']
            all_group_keys.add(key)
            
            # Map main key
            key_lookup[key] = config_item
            
            # Map aliases
            for alias in config_item.get('aliases', []):
                key_lookup[alias] = config_item
                all_group_keys.add(alias)
    
    checked_params = {}
    remaining_params = {}
    
    # Process each input key
    for input_key, input_value in params.items():
        if input_key in key_lookup:
            # This key belongs to our group - validate and convert
            config_item = key_lookup[input_key]
            main_key = config_item['key']
            expected_type = config_item.get('type', None)
            valid_values = config_item.get('values')

            if expected_type is None:
                expected_types = config_item.get('types', [])
                if len(expected_types)>0:
                    if type(input_value) not in expected_types:
                        expected_types_str = ', '.join(t.__name__ for t in expected_types)
                        return _error(f"Invalid type of '{main_key}' - expected '[{expected_types_str}]' but got '{type(input_value).__name__}'", 1, None, fail_on_error)

                # Store using the main key name
                checked_params[main_key] = input_value
            else:
                try:
                    # Type validation and conversion
                    if expected_type == bool:
                        if isinstance(input_value, bool):
                            converted_value = input_value
                        elif isinstance(input_value, str):
                            # Convert string to bool
                            tmp_converted_value = input_value.lower().strip()

                            if tmp_converted_value in ['1', 'on', 'true', 'yes']:
                                convert_value = True
                            elif tmp_converted_value in ['0', 'off', 'false', 'no']:
                                convert_value = False
                            else:
                                return _error(f"Invalid bool value '{input_value}' for '{main_key}'", 1, None, fail_on_error)

                        else:
                            return _error(f"Invalid type of key '{main_key}' - expected 'str' but got '{type(input_value).__name__}'", 1, None, fail_on_error)
                            
                    elif expected_type == str:
                        if not isinstance(input_value, str):
                            return _error(f"Invalid type of '{main_key}' - expected 'str' but got '{type(input_value).__name__}'", 1, None, fail_on_error)

                        converted_value = input_value
                            
                    elif expected_type == int:
                        try:
                            converted_value = int(input_value)
                        except (ValueError, TypeError):
                            return _error(f"Invalid int value '{input_value}' for '{main_key}'", 1, None, fail_on_error)
                            
                    elif expected_type == float:
                        try:
                            converted_value = float(input_value)
                        except (ValueError, TypeError):
                            return _error(f"Invalid float value '{input_value}' for '{main_key}'", 1, None, fail_on_error)
                    else:
                        # Default: keep as-is
                        converted_value = input_value
                    
                    # Store using the main key name
                    checked_params[main_key] = converted_value
                    
                except Exception as e:
                    return _error(f"Error processing {main_key}", 1, e, fail_on_error)
            
        else:
            # This key doesn't belong to our group - put in remaining
            remaining_params[input_key] = input_value
    
    return {
        'return': 0,
        'checked_params': checked_params,
        'remaining_params': remaining_params
    }


def print_params_help(
        params_description: list  # List of parameter dictionaries
):
    """Generate formatted help text for command-line parameters.
    
    Creates a formatted string displaying parameter flags, types, and descriptions
    with proper column alignment.
    
    Args:
        params_description (list): List of parameter dictionaries containing 'key', 'type',
                                   'desc', 'aliases', etc.
        
    Returns:
        dict: Dictionary with 'return': 0 and 'params_info' containing formatted help text.
    """

    params_info = ''
    
    # Calculate column widths for alignment
    max_flag_width = 0
    max_type_width = 0
    
    for param in params_description:
        # Build flag string with aliases
        flag_str = f"--{param['key']}"
        aliases = param.get('aliases', [])
        if aliases:
            alias_str = ', '.join([f"-{alias}" if len(alias) == 1 else f"--{alias}" for alias in aliases])
            flag_str = f"{flag_str}, {alias_str}"
        
        max_flag_width = max(max_flag_width, len(flag_str))
        param_type = param.get('type', None)
        type_str = param_type.__name__ if hasattr(param_type, '__name__') else str(param_type)
        max_type_width = max(max_type_width, len(type_str))
    
    # Print each parameter
    for param in params_description:
        if param.get('skip_from_help', False):
            continue

        if param.get('space_before', False):
            params_info += '\n'

        # Build flag string
        flag_str = f"--{param['key']}"
        aliases = param.get('aliases', [])
        if aliases:
            alias_str = ', '.join([f"-{alias}" if len(alias) == 1 else f"--{alias}" for alias in aliases])
            flag_str = f"{flag_str}, {alias_str}"
        
        # Get type name
        param_type = param.get('type', None)
        type_str = param_type.__name__ if hasattr(param_type, '__name__') else str(param_type)
        
        # Build info parts
        info_parts = []
        
        # Add default value if present
        if 'default' in param:
            info_parts.append(f"default: {param['default']}")
        
        # Add possible values if present
        if 'values' in param and param['values']:
            values_str = ', '.join(map(str, param['values']))
            info_parts.append(f"values: [{values_str}]")
        
        # Format the line
        flag_part = flag_str.ljust(max_flag_width)
        type_part = f"({type_str})".ljust(max_type_width + 2)
        
        info_str = f" ({'; '.join(info_parts)})" if info_parts else ""
        desc = param.get('desc', '')
        
        params_info += f"   {flag_part} {type_part} {desc}{info_str}\n"

    return {'return':0, 'params_info':params_info}
