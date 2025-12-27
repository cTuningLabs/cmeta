"""
Common reusable functions

cMeta author and developer: (C) 2025 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

###################################################################################################
def _error(error_msg, return_code=1, exception=None, fail_on_error=False):
    """Create error return dictionary or raise exception based on fail_on_error flag.
    
    Args:
        error_msg: Error message string. If None, uses exception string.
        return_code: Error return code. Default is 1. Code 16 is for file not found warnings.
        exception: Optional exception object to include in error message.
        fail_on_error: If True, raises exception instead of returning error dict.
        
    Returns:
        dict: Dictionary with 'return' and 'error' keys.
        
    Raises:
        Exception: If fail_on_error is True and return_code != 16.
    """

    # Return code 16 is a special one - it's more a warning to handle files that are not found
    # but it's not critical for the system
    if return_code != 16 and fail_on_error:
        if exception:
            raise exception
        else:
            raise RuntimeError(error_msg)

    if error_msg is None:
        err = str(exception)
    else:
        err2 = f" ({exception})" if exception is not None else ""
        err = error_msg + err2

    return {'return': return_code, 'error': err}

###################################################################################################
def deep_merge(
        target: dict,                   # Original dictionary to be updated
        source: dict,                   # New dictionary with updates
        append_lists: bool = False,     # If True, append lists instead of overwrite
        ignore_root_keys: list = []     # Keys to ignore at root level
):
    """
    Recursively updates the target dictionary with values from the source dictionary.
    
    Args:
        target (dict): The original dictionary to be updated.
        source (dict): The new dictionary with updates.
        append_lists (bool): If True, lists will be appended instead of overwritten.
        ignore_root_keys (list): List of keys to ignore from source at the root level.
    """
    from collections.abc import Mapping

    for key, value in source.items():
        if key in ignore_root_keys:
            continue
            
        if isinstance(value, Mapping):
            target[key] = deep_merge(target.get(key, {}), value, append_lists=append_lists)
        elif isinstance(value, list):
            if append_lists and isinstance(target.get(key), list):
                target[key] += value
            else:
                target[key] = value[:]
        else:
            target[key] = value

    return target

###################################################################################################
def deep_remove(
        target: dict,                   # Dictionary to remove keys/values from
        source: dict                    # Dictionary specifying what to remove
):
    """
    Recursively removes keys/values from target dictionary based on source dictionary.
    
    Args:
        target (dict): The dictionary to remove keys/values from (modified in place).
        source (dict): The dictionary specifying what to remove.
                      - If value is a dict, recursively remove nested keys
                      - If value is a list, remove list elements from target list
                      - Otherwise, remove the entire key from target
                      
    Returns:
        dict: The modified target dictionary
    """
    from collections.abc import Mapping

    for key, value in source.items():
        if key not in target:
            continue
            
        if isinstance(value, Mapping) and isinstance(target[key], Mapping):
            # Recursively remove from nested dictionaries
            deep_remove(target[key], value)
            # Remove the key if the nested dict is now empty
            if not target[key]:
                del target[key]
        elif isinstance(value, list) and isinstance(target[key], list):
            # Remove list elements that exist in source from target
            target[key] = [item for item in target[key] if item not in value]
            # Remove the key if the list is now empty
            if not target[key]:
                del target[key]
        else:
            # Remove the key entirely
            del target[key]

    return target

###################################################################################################
def safe_serialize_json(
        obj,                                    # Python object to serialize
        non_serializable_text: str = None       # Text for non-serializable objects
):
    """Recursively serialize Python objects to JSON-compatible format.
    
    Handles objects that are not JSON serializable by converting them to strings
    or nested structures. Sets, tuples, and non-serializable objects are handled.
    
    Args:
        obj: Python object to serialize.
        non_serializable_text (str | None): Text to use for non-serializable objects. 
                              Default is "#NON-SERIALIZABLE#".
        
    Returns:
        JSON-serializable version of obj (dict, list, str, int, float, bool, None).
    """
    import json

    if non_serializable_text is None:
        non_serializable_text = "#NON-SERIALIZABLE#"

    try:
        json.dumps(obj)
        return obj
    except (TypeError, OverflowError):
        if isinstance(obj, dict):
            return {k: safe_serialize_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [safe_serialize_json(item) for item in obj]
        elif isinstance(obj, tuple):
            return tuple(safe_serialize_json(item) for item in obj)
        elif isinstance(obj, set):
            return [safe_serialize_json(item) for item in obj]  # Convert sets to lists
        else:
            return non_serializable_text

###################################################################################################
def safe_print_json(
        obj,                                    # Python object to print as JSON
        indent: int = 2,                        # Number of spaces for indentation
        non_serializable_text: str = None,      # Text for non-serializable objects
        ignore_keys: list = [],                 # Top-level keys to exclude
        sort: bool = True                       # If True, sort dictionary keys
):
    """Print object as JSON with safe serialization of non-serializable objects.
    
    Args:
        obj: Python object to print as JSON.
        indent (int): Number of spaces for indentation. Default is 2.
        non_serializable_text (str | None): Text to use for non-serializable objects.
        ignore_keys (list): List of top-level keys to exclude from output.
        sort (bool): If True, sort dictionary keys. Default is True.
        
    Returns:
        dict: Dictionary with 'return': 0.
    """
    print(safe_print_json_to_str(obj, indent=indent, non_serializable_text=non_serializable_text, ignore_keys=ignore_keys, sort=sort))

    return {'return':0}

###################################################################################################
def safe_print_json_to_str(
        obj,                                    # Python object to convert to JSON string
        indent: int = 2,                        # Number of spaces for indentation
        non_serializable_text: str = None,      # Text for non-serializable objects
        ignore_keys: list = [],                 # Top-level keys to exclude
        sort: bool = True                       # If True, sort dictionary keys
):
    """Convert object to JSON string with safe serialization.
    
    Args:
        obj: Python object to convert to JSON string.
        indent (int): Number of spaces for indentation. Default is 2.
        non_serializable_text (str | None): Text to use for non-serializable objects.
        ignore_keys (list): List of top-level keys to exclude from output.
        sort (bool): If True, sort dictionary keys. Default is True.
        
    Returns:
        str: JSON string representation of obj.
    """
    import json

    # Only filter top-level dict keys if obj is a dict and ignore_keys is not empty
    if isinstance(obj, dict) and ignore_keys:
        obj = {k: v for k, v in obj.items() if k not in ignore_keys}

    return json.dumps(safe_serialize_json(obj, non_serializable_text=non_serializable_text), indent=indent, sort_keys=sort)

###################################################################################################
def normalize_tags(
        tags,                           # Tags as comma-separated string or list
        fail_on_error: bool = False     # If True, raise exception on error
):
    """Normalize tags from string or list format to clean list of strings.
    
    Converts comma-separated string to list and strips whitespace from each tag.
    
    Args:
        tags (str | list): Tags as comma-separated string or list of strings.
        fail_on_error (bool): If True, raises exception on error instead of returning error dict.
        
    Returns:
        dict: Dictionary with 'return': 0 and 'tags' list, or 'return' > 0 and 'error' on failure.
    """
 
    if type(tags) == str:
        tags = tags.split(',')
    elif type(tags) != list:
        return _error(f'tags should be string or list - got {type(tags)}', 1, None, fail_on_error)

    clean_tags = []

    for t in tags:
        clean_tags.append(t.strip())

    return {'return':0, 'tags': clean_tags}

###################################################################################################
def detect_cid_in_the_current_directory(
        cmeta,                      # CMeta instance
        path: str = None,           # Directory path to check
        debug: bool = False,        # If True, enable debug logging
        logger = None               # Logger instance for debug output
):
    """Detect CMeta repository, category, and artifact from current or specified directory.
    
    Traverses the directory tree to find CMeta repository information and determine
    which artifact the current path corresponds to.
    
    Args:
        cmeta: CMeta instance.
        path (str | None): Directory path to check. If None, uses current working directory.
        debug (bool): If True, enables debug logging.
        logger: Logger instance for debug output.
        
    Returns:
        dict: Dictionary with 'return': 0 and detected information including:
            - artifact_repo_name: Name of the artifact repository
            - artifact_path: Relative path within repository
            - category_alias, category_uid: Category identifiers
            - category_obj: Category object string
            - artifact_alias, artifact_uid, artifact_name: Artifact identifiers
            Or 'return' > 0 and 'error' on failure.
    """

    import os
    from . import names
    from . import files

    category_obj = None

    # Detect cMeta artifact, category and repo in the current directory
    if path == None:
        cur_dir = os.path.normpath(os.path.abspath(os.getcwd()))
    else:
        cur_dir = path

    # Get info about all repos to see if current path is in some existing repo
    r = cmeta.repos.find_in_index('repo', cmeta.cfg['category_repo_uid'])
    if r['return']>0: return r

    repo_artifacts = r['artifacts']

    found = False
    for repo in repo_artifacts:
        repo_path = os.path.normpath(os.path.abspath(repo['full_path']))
        if files.is_path_within(repo_path, cur_dir):
            found = True
            break

    if not found:
        return {'return':1, 'error':'no cMeta repository found in the current path'}

    if debug and logger is not None:
        logger.debug(f'Detecting cMeta repository in the current path: {repo}')

    repo_cmeta_ref_parts = repo['cmeta_ref_parts']

    artifact_repo_alias = repo_cmeta_ref_parts['artifact_alias']
    artifact_repo_uid = repo_cmeta_ref_parts['artifact_uid']

    artifact_repo_name = None

    if artifact_repo_alias != None or artifact_repo_uid != None:
        r = names.restore_cmeta_name({'alias':artifact_repo_alias, 'uid':artifact_repo_uid})
        if r['return']>0: return r
         
        artifact_repo_name = r['name']

    artifact_path = cur_dir[len(repo_path):]
    if artifact_path.startswith(os.sep):
        artifact_path = artifact_path[1:]

    category_alias = None
    category_uid = None

    artifact_alias = None
    artifact_uid = None
    artifact_name = None

    if len(artifact_path)>0:
        j = artifact_path.find(os.sep)
        category_alias = artifact_path[:j] if j>0 else artifact_path

    if category_alias is not None:
        # Find artifacts
        cmeta_ref = {'artifact_repo_alias': artifact_repo_alias,
                     'artifact_repo_uid': artifact_repo_uid,
                     'category_alias':category_alias}

        r = cmeta.repos.find(cmeta_ref)
        # If fails, means that we don't find category but we can still continue ...
        if r['return'] == 0:
            artifacts = r['artifacts']

            found = False
            for artifact in artifacts:
                test_artifact_path = os.path.normpath(os.path.abspath(artifact['path']))

                if files.is_path_within(test_artifact_path, cur_dir):
                    found = True
                    break
            
            if found:
                artifact_cmeta_ref_parts = artifact['cmeta_ref_parts']

                category_uid = artifact_cmeta_ref_parts.get('category_uid')

                artifact_alias = artifact_cmeta_ref_parts.get('artifact_alias')
                artifact_uid = artifact_cmeta_ref_parts.get('artifact_uid')

    if category_alias != None or category_uid != None:
        r = names.restore_cmeta_name({'alias':category_alias, 'uid':category_uid})
        if r['return']>0: return r
         
        category_obj = r['name']

    if artifact_alias != None or artifact_uid != None:
        r = names.restore_cmeta_name({'alias':artifact_alias, 'uid':artifact_uid})
        if r['return']>0: return r
         
        artifact_name = r['name']

    return {'return':0, 
            'artifact_repo_name': artifact_repo_name,
            'artifact_repo_alias': artifact_repo_alias,
            'artifact_repo_uid': artifact_repo_uid,
            'artifact_path': artifact_path,
            'category_alias': category_alias,
            'category_uid': category_uid,
            'category_obj': category_obj,
            'artifact_alias': artifact_alias,
            'artifact_uid': artifact_uid,
            'artifact_name': artifact_name
    }

###################################################################################################
def copy_text_to_clipboard(
        text: str = '',             # Text string to copy to clipboard
        add_quotes: bool = False,   # If True, wrap text in quotes
        do_not_fail: bool = False   # If True, return warning instead of error
):
    """Copy text to system clipboard using pyperclip.
    
    Args:
        text (str): Text string to copy to clipboard.
        add_quotes (bool): If True, wraps text in double quotes before copying.
        do_not_fail (bool): If True, returns warning instead of error if pyperclip not installed.
        
    Returns:
        dict: Dictionary with 'return': 0 on success, or 'return' > 0 and 'error'/'warning' on failure.
    """

    import sys

    try:
        import pyperclip as pc
    except ImportError as e:
        err = f'pyperclip package not found - please install via "pip install pyperclip" ({e})'

        if do_not_fail:
            return {'return':0, 'warning':err}

        return {'return':1, 'error':err}

    if add_quotes:
        text = '"' + text + '"'

    pc.copy(text)

    return {'return':0}

###################################################################################################
def compare_versions(
        version1: str,  # First version string (e.g., "0.3.1", "1.2", "3.2.0-dev")
        version2: str   # Second version string
):
    """
    Compare two version strings.
    
    Args:
        version1 (str): First version string (e.g., "0.3.1", "1.2", "3.2.0-dev")
        version2 (str): Second version string
        
    Returns:
        dict: {'return': 0, 'comparison': '<' | '=' | '>'}
              where '<' means version1 < version2
                    '=' means version1 == version2
                    '>' means version1 > version2
              or {'return': 1, 'error': str} on error
    """
    import re
    
    comparison = None

    try:
        # Split version into numeric parts and suffix (e.g., "3.2.0-dev" -> ["3", "2", "0"], "dev")
        def parse_version(version):
            # Match numeric parts and optional suffix
            match = re.match(r'^([\d.]+)(-.*)?$', version.strip())
            if not match:
                raise ValueError(f"Invalid version format: {version}")
            
            numeric_part = match.group(1)
            suffix = match.group(2) or ""
            
            # Convert numeric parts to integers
            parts = [int(x) for x in numeric_part.split('.')]
            return parts, suffix
        
        parts1, suffix1 = parse_version(version1)
        parts2, suffix2 = parse_version(version2)
        
        # Pad shorter version with zeros
        max_len = max(len(parts1), len(parts2))
        parts1.extend([0] * (max_len - len(parts1)))
        parts2.extend([0] * (max_len - len(parts2)))
        
        # Compare numeric parts
        if parts1 > parts2:
            comparison = '>'
        elif parts1 < parts2:
            comparison = '<'
        else:
            # Numeric parts are equal, compare suffixes
            # Version without suffix is considered higher than with suffix
            # e.g., "3.2.0" > "3.2.0-dev"
            if suffix1 == suffix2:
                comparison = '='
            elif suffix1 == "":
                comparison = '>'
            elif suffix2 == "":
                comparison = '<'
            else:
                # Both have suffixes, compare lexicographically
                if suffix1 > suffix2:
                    comparison = '>'
                else:
                    comparison = '<'
    
    except Exception as e:
        return {'return': 1, 'error': f'Error comparing versions: {str(e)}'}

    return {'return':0, 'comparison': comparison}

###################################################################################################
def generate_timestamp(
        cut: int = None,     # If specified, truncate timestamp to this many characters
        slices: list = None  # List of slice sizes for creating sharded path
):
    """Generate timestamp string and optionally create sharded path.
    
    Creates a timestamp in format YYYYMMDD-MMSS and optionally creates a sharded
    directory path from it.
    
    Args:
        cut (int | None): If specified, truncates timestamp to this many characters.
        slices (list | None): List of slice sizes for creating sharded path.
        
    Returns:
        dict: Dictionary with 'return': 0, 'timestamp' (string), and 'path' (sharded if slices provided).
    """
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    if cut is not None and cut>0:
        timestamp = timestamp[:cut]

    path = timestamp

    if slices is not None and len(slices)>0:
        from .files import shard_name
        import os

        r = shard_name(path, slices)
        if r['return']>0: return r

        path = os.path.join(*r['parts'])

    return {'return':0, 'timestamp': timestamp, 'path': path}

###################################################################################################
def sort_versions(versions, reverse=False):
    def parse_version(v):
        import re

        # Remove leading 'v' if present
        v = v.lstrip("v")
        
        # Extract numeric components (e.g., [12, 3, 4] from "12.3.4dev")
        nums = [int(x) for x in re.findall(r'\d+', v)]
        
        # Extract trailing non-numeric part for optional tie-breaking
        suffix_match = re.search(r'[a-zA-Z]+', v)
        suffix = suffix_match.group(0) if suffix_match else ""
        
        # Return tuple enabling correct comparison
        # Numeric parts first, suffix last
        return (*nums, suffix)

    return sorted(versions, key=parse_version, reverse=reverse)

###################################################################################################
def flatten_dict(d, parent_key="", sep="."):
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k

        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())

        elif isinstance(v, list):
            # add comma before '=' by modifying the key
            items.append((f"{new_key},", ",".join(map(str, v))))

        else:
            items.append((new_key, v))

    return dict(items)
