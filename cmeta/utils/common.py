"""
Common reusable functions

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

from packaging.version import Version

###################################################################################################
def _error(
    error_msg,  # Error message string. If None, uses exception string.
    return_code = 1,  # Error return code. Default is 1. Code 16 is for
    exception = None,  # Optional exception object to include in error message.
    fail_on_error = False,  # If True, raises exception instead of returning error dict.
    fail_on_16 = False,  # If True, treat return code 16 as a fatal error when fail_on_error is enabled.
):
    """
        Create error return dictionary or raise exception based on fail_on_error flag.

        Args:
            error_msg: Error message string. If None, uses exception string.
            return_code: Error return code. Default is 1. Code 16 is for
                           "file not found" or other warnings - it should not
                           fail during debugging.
            exception: Optional exception object to include in error message.
            fail_on_error: If True, raises exception instead of returning error dict.

            fail_on_16: If True, treat return code 16 as a fatal error when fail_on_error is enabled.
        Returns:
            dict: Dictionary with 'return' and 'error' keys.

        Raises:
            Exception: If fail_on_error is True and return_code != 16.
    """

    # Return code 16 is a special one - it's more a warning to handle files that are not found
    # but it's not critical for the system
    if (return_code != 16 or fail_on_16) and fail_on_error:
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
def check_params(
    params,  # Input parameters dictionary.
    keys,  # Collection of dictionary keys.
    name = None,  # Object or artifact name.
):
    """
        Validate that input dictionary contains only expected keys.

        Args:
            params: Input parameters dictionary.
            keys: Collection of dictionary keys.
            name: Object or artifact name.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """

    for k in list(params.keys()):
        if k not in keys:
            x = ''
            if name:
                import importlib.util
                spec = importlib.util.find_spec(name)
                x = f' in module "{spec.origin}" ({name})'
            err = f'unknown input parameter "{k}"{x}'
            return {'return':1, 'error': err}

    return {'return':0}

###################################################################################################
def deep_merge(
    target: dict,  # The original dictionary to be updated.
    source: dict,  # The new dictionary with updates.
    append_lists: bool = False,  # If True, lists will be appended instead of overwritten.
    prepend_lists: bool = False,  # If True and append_lists is True, insert new items at the
    ignore_root_keys: list = [],  # List of keys to ignore from source at the root level.
):
    """
        Recursively updates the target dictionary with values from the source dictionary.

        Args:
            target (dict): The original dictionary to be updated.
            source (dict): The new dictionary with updates.
            append_lists (bool): If True, lists will be appended instead of overwritten.
            prepend_lists (bool): If True and append_lists is True, insert new items at the
                                 start of existing lists instead of appending at the end.
            ignore_root_keys (list): List of keys to ignore from source at the root level.

        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """
    from collections.abc import Mapping

    for key, value in source.items():
        if key in ignore_root_keys:
            continue
            
        if isinstance(value, Mapping):
            target[key] = deep_merge(target.get(key, {}), value, append_lists=append_lists, prepend_lists=prepend_lists)
        elif isinstance(value, list):
            if append_lists and isinstance(target.get(key), list):
                if prepend_lists:
                    target[key] = value + target[key]
                else:
                    if type(value) == list:
                        for v in value:
                            if v not in target[key]:
                                target[key].append(v)
                    elif value not in target[key]:
                        target[key].append(value)
            else:
                target[key] = value[:]
        else:
            target[key] = value

    return target

###################################################################################################
def deep_remove(
    target: dict,  # The dictionary to remove keys/values from (modified in place).
    source: dict,  # The dictionary specifying what to remove.
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

        Raises:
            Exception: Propagated runtime errors, if any.
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
    obj,  # Python object to serialize.
    non_serializable_text: str = None,  # Text to use for non-serializable objects.
):
    """
        Recursively serialize Python objects to JSON-compatible format.

        Handles objects that are not JSON serializable by converting them to strings
        or nested structures. Sets, tuples, and non-serializable objects are handled.

        Args:
            obj: Python object to serialize.
            non_serializable_text (str | None): Text to use for non-serializable objects.
                                  Default is "#NON-SERIALIZABLE#".

        Returns:
            JSON-serializable version of obj (dict, list, str, int, float, bool, None).

        Raises:
            Exception: Propagated runtime errors, if any.
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
    obj,  # Python object to print as JSON.
    indent: int = 2,  # Number of spaces for indentation. Default is 2.
    non_serializable_text: str = None,  # Text to use for non-serializable objects.
    ignore_keys: list = [],  # List of top-level keys to exclude from output.
    sort: bool = True,  # If True, sort dictionary keys. Default is True.
):
    """
        Print object as JSON with safe serialization of non-serializable objects.

        Args:
            obj: Python object to print as JSON.
            indent (int): Number of spaces for indentation. Default is 2.
            non_serializable_text (str | None): Text to use for non-serializable objects.
            ignore_keys (list): List of top-level keys to exclude from output.
            sort (bool): If True, sort dictionary keys. Default is True.

        Returns:
            dict: Dictionary with 'return': 0.

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    print(safe_print_json_to_str(obj, indent=indent, non_serializable_text=non_serializable_text, ignore_keys=ignore_keys, sort=sort))

    return {'return':0}

###################################################################################################
def print_module_vars(
    obj,
    indent: int = 2,
    sort: bool = True,
    private: bool = True,
):

    for key, value in obj.__dict__.items():
        if private or not key.startswith("_"):  # filter public only
            print(f"{key} = {value}")

    return

###################################################################################################
def safe_print_json_to_str(
    obj,  # Python object to convert to JSON string.
    indent: int = 2,  # Number of spaces for indentation. Default is 2.
    non_serializable_text: str = None,  # Text to use for non-serializable objects.
    ignore_keys: list = [],  # List of top-level keys to exclude from output.
    sort: bool = True,  # If True, sort dictionary keys. Default is True.
):
    """
        Convert object to JSON string with safe serialization.

        Args:
            obj: Python object to convert to JSON string.
            indent (int): Number of spaces for indentation. Default is 2.
            non_serializable_text (str | None): Text to use for non-serializable objects.
            ignore_keys (list): List of top-level keys to exclude from output.
            sort (bool): If True, sort dictionary keys. Default is True.

        Returns:
            str: JSON string representation of obj.

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    import json

    # Only filter top-level dict keys if obj is a dict and ignore_keys is not empty
    if isinstance(obj, dict) and ignore_keys:
        obj = {k: v for k, v in obj.items() if k not in ignore_keys}

    return json.dumps(safe_serialize_json(obj, non_serializable_text=non_serializable_text), indent=indent, sort_keys=sort)

###################################################################################################
def normalize_tags(
    tags,  # Tags as comma-separated string or list of strings.
    fail_on_error: bool = False,  # If True, raises exception on error instead of returning error dict.
):
    """
        Normalize tags from string or list format to clean list of strings.

        Converts comma-separated string to list and strips whitespace from each tag.

        Args:
            tags (str | list): Tags as comma-separated string or list of strings.
            fail_on_error (bool): If True, raises exception on error instead of returning error dict.

        Returns:
            dict: Dictionary with 'return': 0 and 'tags' list, or 'return' > 0 and 'error' on failure.

        Raises:
            Exception: Propagated runtime errors, if any.
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
    cmeta,  # CMeta instance.
    path: str = None,  # Directory path to check. If None, uses current working directory.
    debug: bool = False,  # If True, enables debug logging.
    logger = None,  # Logger instance for debug output.
):
    """
        Detect CMeta repository, category, and artifact from current or specified directory.

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

        Raises:
            Exception: Propagated runtime errors, if any.
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
    text: str = '',  # Text string to copy to clipboard.
    add_quotes: bool = False,  # If True, wraps text in double quotes before copying.
    do_not_fail: bool = False,  # If True, returns warning instead of error if pyperclip not installed.
):
    """
        Copy text to system clipboard using pyperclip.

        Args:
            text (str): Text string to copy to clipboard.
            add_quotes (bool): If True, wraps text in double quotes before copying.
            do_not_fail (bool): If True, returns warning instead of error if pyperclip not installed.

        Returns:
            dict: Dictionary with 'return': 0 on success, or 'return' > 0 and 'error'/'warning' on failure.

        Raises:
            Exception: Propagated runtime errors, if any.
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
    version2: str,  # Second version string
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

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    import re
    
    comparison = None

    try:
        # Split version into numeric parts and suffix (e.g., "3.2.0-dev" -> ["3", "2", "0"], "dev")
        def parse_version(
            version,  # Value for version.
        ):
            """
                Parse version into numeric parts and optional suffix.

                Args:
                    version: Value for version.
                Returns:
                    dict: Operation result.
                Raises:
                    Exception: Propagated runtime errors, if any.
            """
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
    cut: int = None,  # If specified, truncates timestamp to this many characters.
    slices: list = None,  # List of slice sizes for creating sharded path.
):
    """
        Generate timestamp string and optionally create sharded path.

        Creates a timestamp in format YYYYMMDD-MMSS and optionally creates a sharded
        directory path from it.

        Args:
            cut (int | None): If specified, truncates timestamp to this many characters.
            slices (list | None): List of slice sizes for creating sharded path.

        Returns:
            dict: Dictionary with 'return': 0, 'timestamp' (string), and 'path' (sharded if slices provided).

        Raises:
            Exception: Propagated runtime errors, if any.
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
def sort_versions(
    versions,  # Value for versions.
    reverse = False,  # Value for reverse.
):
    """
        Sort version-like strings using numeric-aware comparison.

        Args:
            versions: Value for versions.
            reverse: Value for reverse.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """
    def parse_version(
        v,  # Value for v.
    ):
        """
            Convert a version-like string to a sortable tuple.

            Args:
                v: Value for v.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """
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
def flatten_dict(
    d,  # Value for d.
    parent_key = '',  # Value for parent key.
    sep = '.',  # Value for sep.
):
    """
        Flatten a nested dictionary into dotted keys.

        Args:
            d: Value for d.
            parent_key: Value for parent key.
            sep: Value for sep.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """
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

###################################################################################################
def matches_query(
    data,  # Input data object.
    query,  # Value for query.
    match_version_func = None,  # Value for match version func.
    match_empty_version = False,  # Value for match empty version.
):
    """
        Check whether input data satisfies a query dictionary.

        Args:
            data: Input data object.
            query: Value for query.
            match_version_func: Value for match version func.
            match_empty_version: Value for match empty version.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """
    for key, q_value in query.items():
        negate = key.endswith("-")
        actual_key = key[:-1] if negate else key

        is_version_key = isinstance(actual_key, str) and actual_key.startswith('@')
        actual_key = key[1:] if is_version_key else actual_key

        if actual_key not in data:
            if negate:
                continue  # key doesn't exist → OK for negation

            if is_version_key and match_empty_version:
                continue  # if version key doesn't exist and match_empty_version is on -> OK

            return False

        d_value = data[actual_key]

        # Check if the data key starts with '@' (version comparison indicator)
        if is_version_key and match_version_func is not None:
            # Call match_version_func with query value first, then data value
            result = match_version_func(q_value, d_value)
            
            # Expect cMeta dict with 'return': 0 and 'match': bool
            if result.get('return') != 0:
                return False
            
            matched = result.get('matched', False)
        else:
            matched = value_matches(d_value, q_value, match_version_func, match_empty_version)

        if negate and matched:
            return False
        if not negate and not matched:
            return False

    return True


###################################################################################################
def value_matches(
    data_value,  # Value for data value.
    query_value,  # Value for query value.
    match_version_func = None,  # Value for match version func.
    match_empty_version = False,  # Value for match empty version.
):
    """
        Evaluate a single query value against a data value.

        Args:
            data_value: Value for data value.
            query_value: Value for query value.
            match_version_func: Value for match version func.
            match_empty_version: Value for match empty version.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """
    # Dict → recursive match
    if isinstance(query_value, dict):
        if not isinstance(data_value, dict):
            return False
        return matches_query(data_value, query_value, match_version_func, match_empty_version)

    # List → query list must be subset of data list
    if isinstance(query_value, list):
        if not isinstance(data_value, list):
            return False
        return all(item in data_value for item in query_value)

    # Scalar → direct equality
    return data_value == query_value

###################################################################################################
def _get_nested(
    mapping,  # Value for mapping.
    path,  # Filesystem path.
    default = None,  # Value for default.
):
    """
        Get a nested dictionary value using dot-separated path.

        Args:
            mapping: Value for mapping.
            path: Filesystem path.
            default: Value for default.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """
    current = mapping
    for part in path.split("."):
        if not isinstance(current, dict):
            return default
        current = current.get(part)
        if current is None:
            return default
    return current


def _normalize_value(
    value,  # Input value.
    *,
    as_version = False,  # Value for as version.
):
    """
        Normalize sortable values and optionally parse semantic versions.

        Args:
            value: Input value.
            as_version: Value for as version.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """
    if value is None:
        return value

    if as_version:
        try:
            return Version(value)
        except Exception:
            return value

    return value


def _invert_value(
    value,  # Input value.
):
    """
        Invert a sortable value for descending ordering.

        Args:
            value: Input value.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """
    if value is None:
        return value

    if isinstance(value, (int, float)):
        return -value

    if isinstance(value, Version):
        return tuple(-v for v in value.release)

    return "".join(chr(0x10FFFF - ord(c)) for c in str(value))

def _with_missing_flag(
    value,  # Input value.
):
    """
        Tag values so missing entries sort after present entries.

        Args:
            value: Input value.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """
    if value is None:
        return (1, None)
    return (0, value)

def build_sort_key(
    artifact,  # Artifact reference.
    sort_keys,  # Sort key definitions.
):
    """
        Build a stable tuple key for artifact sorting rules.

        Args:
            artifact: Artifact reference.
            sort_keys: Sort key definitions.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """
    key_parts = []

    for raw_key in sort_keys:
        as_version = raw_key.startswith("@")
        descending = raw_key.endswith("-")

        key = raw_key
        if as_version:
            key = key[1:]
        if descending:
            key = key[:-1]

        value = _get_nested(artifact, key)
        value = _normalize_value(value, as_version=as_version)

        if descending:
            value = _invert_value(value)

        # 👇 THIS LINE FIXES THE ERROR
        key_parts.append(_with_missing_flag(value))

    return tuple(key_parts)

###################################################################################################
def expand_string(
    template: str,  # Value for template.
    values: dict,   # Input values.
) -> str:
    """
        Expand template placeholders from a values dictionary.

        Args:
            template: Value for template.
            values: Input values.
        Returns:
            string: Result string value.
            (value): Result non-string value only if only one and non string!
                     (useful for env dict for example)

        Raises:
            Exception: Propagated runtime errors, if any.
    """

    out = []
    i = 0

    while i < len(template):
        start = template.find("{{", i)
        if start == -1:
            out.append(template[i:])
            break

        x = template[i:start]
        if x != '':
            out.append(x)

        end = template.find("}}", start + 2)
        if end == -1:
            return {'return':1, 'error':f'Unclosed "{{" in "{template}"'}

        expr = template[start + 2:end].strip()
        i = end + 2

        # default handling
        if "|" in expr:
            key, default = expr.split("|", 1)
            key, default = key.strip(), default.strip()
        else:
            key, default = expr, None

        # check if cName (if key startswith $$, use UID, elif startswith $, use alias)
        use_alias = False
        use_uid = False
        if key.startswith('$$'):
            use_uid = True
            key = key[2:]
        elif key.startswith('$'):
            use_alias = True
            key = key[1:]

        # nested lookup
        cur = values
        for part in key.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                if default is not None:
                    if default.startswith('$'):
                        import ast

                        try:
                            default = ast.literal_eval(default[1:])
                        except (ValueError, SyntaxError):
                            pass  # use original string 

                    cur = default
                    break
                return {'return':1, 'error':f'Missing key "{key}" in context dict'}

        v = cur

        if use_uid or use_alias:
            from .names import parse_cmeta_name

            r = parse_cmeta_name(v)
            if r['return']>0: return r

            name = r['name']

            if use_alias:
                v = name.get('alias', name.get('uid'))
            else:
                v = name.get('uid')

            v = str(v).lower()

        out.append(v)

#   FGG: on 20260325 I changed expansion of None to ""
    result = {'return': 0, 'string': "".join("" if x is None else str(x) for x in out)}

#    result = {'return':0, 'string': "".join(map(str, out))}

    if len(out) == 1 and type(out[0]) != str:
        result['value'] = out[0]

    return result

###################################################################################################
def expand_strings_in_dict(
    data,  # Dictionary or list to process (modified in-place)
    values: dict,  # Dictionary of values for template expansion
) -> dict:
    """
        Recursively expand template strings in a dictionary/list structure.

        Traverses dictionaries and lists, calling expand_string on any string values found.
        Updates the original data in-place if expansion succeeds.

        Args:
            data: Dictionary or list to process (modified in-place)
            values: Dictionary of values for template expansion

        Returns:
            dict: {'return': 0} on success, or {'return': 1, 'error': str} on failure

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    
    def process_value(
        value,  # Input value.
    ):
        """
            Recursively process a value (dict, list, or string).

            Args:
                value: Input value.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """
        if isinstance(value, dict):
            r = expand_strings_in_dict(value, values)
            if r['return'] > 0:
                return r
            return {'return': 0, 'value': value}
            
        elif isinstance(value, list):
            for i, item in enumerate(value):
                r = process_value(item)
                if r['return'] > 0:
                    return r
                value[i] = r['value']
            return {'return': 0, 'value': value}
            
        elif isinstance(value, str):
            r = expand_string(value, values)
            if r['return'] > 0:
                return r

            result = {'return': 0}

            if 'value' in r:
                result['value'] = r['value']
            else:
                result['value'] = r['string']

            return result
            
        else:
            # Non-string, non-dict, non-list values pass through unchanged
            return {'return': 0, 'value': value}
    
    if isinstance(data, dict):
        # Process each key-value pair in the dictionary
        for key, value in data.items():
            r = process_value(value)
            if r['return'] > 0:
                return r
            data[key] = r['value']

    elif isinstance(data, list):
        # Process each list element in place
        for i, value in enumerate(data):
            r = process_value(value)
            if r['return'] > 0:
                return r
            data[i] = r['value']

    else:
        return {'return': 1, 'error': f'data should be dict or list - got {type(data)}'}
    
    return {'return': 0}

###################################################################################################
def restricted_bool_eval(
    expression: str,  # Value for expression.
    variables: dict = None,  # Value for variables.
) -> bool:
    """
        Safely evaluate a boolean expression using restricted eval.

        :param expression: Boolean expression as a string
        :param variables: Allowed variables (name -> value)
        :return: True or False (False on any error)

        Args:
            expression: Value for expression.
            variables: Value for variables.
        Returns:
            bool: Result value.
        Raises:
            Exception: Propagated runtime errors, if any.
    """
    if variables is None:
        variables = {}

    result = None

    try:
        result = bool(eval(
            expression,
            {"__builtins__": {}},  # Disable built-ins
            variables
        ))
    except Exception as e :
        return {'return':1, 'error':f'can\'t evaluate expression "{str}": {e}'}

    return {'return':0, 'result': result}

###################################################################################################
def smart_get(
    d: dict, 
    key: str, 
    default = None):

    """
    Retrieve a value from a nested dictionary using a dot-separated key.

    Args:
        d (dict): The dictionary to query.
        key (str): Dot-separated key string (e.g., "a.b.c").
        default (Any, optional): Value to return if any key is not found.
            Defaults to None.

    Returns:
        Any: The value found at the nested key path, or ``default`` if
        the path does not exist.

    Examples:
        >>> data = {'x': {'y': 'z'}}
        >>> smart_get(data, 'x.y')
        'z'
        >>> smart_get(data, 'x')
        {'y': 'z'}
        >>> smart_get(data, 'a.b', 'NA')
        'NA'
    """
    keys = key.split(".")
    current = d

    for k in keys:
        if isinstance(current, dict) and k in current:
            current = current[k]
        else:
            return default

    return current

###################################################################################################
def smart_set(params: dict, key: str, value):
    parts = key.split(".")
    cur = params

    for part in parts[:-1]:
        if part not in cur:
            cur[part] = {}
        elif not isinstance(cur[part], dict):
            raise TypeError(f"Cannot descend into non-dict at key '{part}'")
        cur = cur[part]

    cur[parts[-1]] = value
    
    return
