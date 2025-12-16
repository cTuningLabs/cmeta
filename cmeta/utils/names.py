"""
Reusable functions to handle cMeta objects

cMeta author and developer: (C) 2025 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.

-------------------------------------------------------
Conventions:

  cMeta UID = 16 hex characters
  cMeta alias = any adopted filename in Linux, Windows and MacOS (since we keep them as directories i repositories)

  cMeta name = alias | UID | alias,UID

  repo_name = repo_alias | repo_uid | repo_alias,repo_uid
  repo == repo_name

  artifact_name = artifact_alias | artifact_uid | artifact_alias,artifact_uid
  artifact_name_dict = {'artifact_alias', 'artifact_uid'}

  artifact_obj = (artifact_repo_name:)artifact_name
  artifact_obj_dict = {artifact_repo_alias, artifact_repo_uid, artifact_alias, artifact_uid}
  artifact == artifact_obj

  category_name = category_alias | category_uid | category_alias,category_uid
  category_name_dict = {category_alias, category_uid}

  category_obj = (category_repo_name:)category_name
  category_obj_dict = {category_repo_alias, category_repo_uid, category_alias, category_uid}
  category == category_obj

  cmeta_ref = category_obj::artifact_obj
  cmeta_ref_dict = {category_repo_alias, category_repo_uid, category_alias, category_uid,
                    artifact_repo_alias, artifact_repo_uid, artifact_alias, artifact_uid}
  cRef == cmeta_ref
  
Find in Fast index:

  records = list of artifacts following search criteria
  record = {'path',
            'cmeta_ref_parts',
            'cmeta'}


"""

from typing import Optional, Tuple, Dict, Union, List, Any
import uuid

from .common import _error

def generate_cmeta_uid() -> str:
    """
    Generate a new 16-character UID (from UUID4).

    Returns:
        str: A new 16-character hexadecimal UID string.
    """
    return uuid.uuid4().hex[:16]

def is_valid_cmeta_uid(text: str) -> bool:
    """
    Validate if UID is a valid 16-character hex string (case-insensitive).

    Args:
        text (str): The string to validate as a UID.

    Returns:
        bool: True if the text is a valid 16-character hex string, False otherwise.
    """
    return len(text)==16 and all(c in set("0123456789abcdefABCDEF") for c in text)

def is_valid_category_alias(
        alias: str  # The string to validate as category alias
):
    """
    Validate if category alias is valid (Windows, Linux, MacOS)

    Args:
        alias (str): The string to validate as category alias.

    Returns:
        dict: Dictionary with 'return': 0 if valid, or 'return': 1 and 'error' if invalid.
    """
    
    r = is_valid_cmeta_alias(alias)
    if r['return']>0: return r

    if ' ' in alias:
        return {'return': 1, 'error': f'Invalid alias "{alias}". Cannot contain spaces'}

    if alias.startswith('.'):
        return {'return': 1, 'error': f'Invalid alias "{alias}". Cannot start with a dot'}
    
    if alias.endswith('.'):
        return {'return': 1, 'error': f'Invalid alias "{alias}". Cannot end with a dot'}

    if alias != alias.lower():
        return {'return': 1, 'error': f'Invalid alias "{alias}". Cannot have capital letters'}

    # Check for reserved names on Windows (case-insensitive)
    reserved_names = {'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 
                      'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 
                      'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'}

    base_name = alias.split('.')[0].upper()
    if base_name in reserved_names:
        return {'return': 1, 'error': f'Invalid alias "{alias}". Reserved name on Windows'}
    
    return {'return':0}

def is_valid_cmeta_alias(
        alias: str  # The string to validate as a CMeta alias
):
    """Validate if alias is valid for Windows, Linux, and MacOS filesystems.
    
    Checks for invalid characters and problematic patterns that would cause
    issues when used as directory names across different operating systems.

    Args:
        alias (str): The string to validate as a CMeta alias.

    Returns:
        dict: Dictionary with 'return': 0 if valid, or 'return': 1 and 'error' if invalid.
    """
    invalid_chars = '<>:"/\\|?*'

    if any(char in alias for char in invalid_chars):
        return {'return': 1, 'error': f'Invalid characters in alias "{alias}" - it cannot contain: {invalid_chars}'}
    
    # Check for leading/trailing spaces or dots (problematic on Windows)
    if alias != alias.strip():
        return {'return': 1, 'error': f'Invalid alias "{alias}". Cannot have leading/trailing spaces'}

    return {'return':0}

def parse_cmeta_name(
        name: Optional[Union[str, Dict[str, Any]]],  # The name string or dict to parse
        key: Optional[str] = None                    # Optional key prefix for result keys
) -> Dict[str, Any]:
    """
    Parse cMeta name (alias | uid | alias,uid), returning a dict.

    Args:
        name (Optional[str|dict]): The name string or dict to parse. Can be None.
        key (Optional[str]): If provided, keys will be '{key}_alias' and '{key}_uid'.

    Returns:
        Dict[str, Any]: {'return': 0, 'name': {keyed alias/uid or just alias/uid}}.
                        If error, returns {'return': 1, 'error': ...}
                        If input is dict, returns it unchanged as {'return': 0, 'name': name}
    """
    if isinstance(name, dict):
        return {'return': 0, 'name': name}

    if name is None:
        alias, uid = None, None
    else:
        name = name.strip()
        if not name:
            alias, uid = None, None
        elif is_valid_cmeta_uid(name):
            alias, uid = None, name.lower()
        else:
            i = name.rfind(",")
            if i != -1:
                left = name[:i].strip()
                right = name[i + 1 :].strip()
                if is_valid_cmeta_uid(right):
                    alias, uid = left or None, right.lower()
                else:
                    alias, uid = name or None, None
            else:
                alias, uid = name or None, None

    result = {}
    
    if alias is not None and is_valid_cmeta_uid(alias):
        return {'return':1, 'error':f"alias can't be a UID in {name}"}

    if key is not None:
        if alias is not None:
            result[f"{key}_alias"] = alias
        if uid is not None:
            result[f"{key}_uid"] = uid
    else:
        if alias is not None:
            result["alias"] = alias
        if uid is not None:
            result["uid"] = uid
    
    return {'return': 0, 'name': result}


def restore_cmeta_name(
        name: Dict[str, Any],        # Dict containing alias/uid or {key}_alias/{key}_uid
        key: Optional[str] = None,   # Optional key to use for lookup
        fail_on_error: bool = False  # If True, raise error on failure
) -> Dict[str, Any]:
    """
    Restore cMeta name string from canonicalized dict.

    Args:
        name (Dict[str, Any]): Dict containing alias/uid or {key}_alias/{key}_uid.
        key (Optional[str]): Optional key to use for lookup.
        fail_on_error (bool): If True, raise error on failure.

    Returns:
        Dict[str, Any]: {'return': 0, 'name': restored_string}.
                        If error, returns {'return': 1, 'error': ...}
    """
    if key is not None:
        alias = name.get(f"{key}_alias")
        uid = name.get(f"{key}_uid")
    else:
        alias = name.get("alias")
        uid = name.get("uid")

    if alias is not None and uid is not None:
        restored = f"{alias},{uid}"
    elif alias is not None:
        restored = alias
    elif uid is not None:
        restored = uid
    else:
        restored = None

    return {'return': 0, 'name': restored}



def parse_cmeta_obj(
        obj: Optional[Union[str, Dict[str, Any]]],  # Object string or dict to parse
        key: Optional[str] = None,                  # Optional key prefix for dict keys
        fail_on_error: bool = False                 # If True, raise error on failure
) -> Dict[str, Any]:
    """
    Parse cMeta object string (repo_name:cmeta_name or cmeta_name) into dict.

    Args:
        obj (Optional[str|dict]): Object string or dict to parse.
        key (Optional[str]): Optional key prefix for dict keys.
        fail_on_error (bool): If True, raise error on failure.

    Returns:
        Dict[str, Any]: {'return': 0, 'obj_parts': {repo/name parts}}.
                        If error, returns {'return': 1, 'error': ...}
                        If input is dict, returns it unchanged as {'return': 0, 'obj_parts': obj}
    """
    if isinstance(obj, dict):
        return {'return': 0, 'obj_parts': obj}

    if obj is None:
        repo = None
        name = None
    else:
        obj = obj.strip()
        if not obj:
            repo = None
            name = None
        else:
            if '::' in obj:
                return _error(f'cMeta obj must not have :: in "{obj}"', 1, None, fail_on_error)             
            elif ':' in obj:
                repo, name = obj.split(':', 1)
                repo = repo.strip() or None
                name = name.strip() or None
            else:
                repo = None
                name = obj

    if repo:
        r = parse_cmeta_name(repo, key + '_repo' if key else 'repo')
        if r['return'] > 0:
            return r
        repo_dict = r['name']
    else:
        repo_dict = {}

    if name:
        r = parse_cmeta_name(name, key)
        if r['return'] > 0:
            return r
        name_dict = r['name']
    else:
        name_dict = {}

    result = {**repo_dict, **name_dict}
    
    return {'return': 0, 'obj_parts': result}

def restore_cmeta_obj(
        obj_parts: Dict[str, Any],   # Dict with repo/name parts
        key: Optional[str] = None,   # Optional key prefix
        fail_on_error: bool = False  # If True, raise error on failure
) -> Dict[str, Any]:
    """
    Restore cMeta object string from canonicalized dict.

    Args:
        obj_parts (Dict[str, Any]): Dict with repo/name parts.
        key (Optional[str]): Optional key prefix.
        fail_on_error (bool): If True, raise error on failure.

    Returns:
        Dict[str, Any]: {'return': 0, 'obj': restored_string}.
                        If error, returns {'return': 1, 'error': ...}
    """
    r = restore_cmeta_name(obj_parts, key + '_repo' if key else 'repo', fail_on_error=fail_on_error)
    if r['return']>0: return r
    repo = r['name']

    r = restore_cmeta_name(obj_parts, key, fail_on_error=fail_on_error)
    if r['return']>0: return r
    name = r['name']
    
    if repo and name:
        obj = f"{repo}:{name}"
    elif name:
        obj = name
    else:
        obj = None

    return {'return':0, 'obj':obj}

def parse_cmeta_ref(
        ref: Optional[Union[str, Dict[str, Any]]],  # Ref string or dict to parse
        fail_on_error: bool = False                 # If True, raise error on failure
) -> Dict[str, Any]:
    """
    Parse cMeta ref string (category_obj::artifact_obj) into dict.

    Args:
        ref (Optional[str|dict]): Ref string or dict to parse.
        fail_on_error (bool): If True, raise error on failure.

    Returns:
        Dict[str, Any]: {'return': 0, 'ref_parts': {category/artifact parts}}.
                        If error, returns {'return': 1, 'error': ...}
                        If input is dict, returns it unchanged as {'return': 0, 'ref_parts': ref}
    """
    if isinstance(ref, dict):
        return {'return': 0, 'ref_parts': ref}

    if ref is None:
        result = {}
    else:
        ref = ref.strip()
        if "::" in ref:
            category_part, artifact_part = ref.split("::", 1)
            category_part = category_part.strip() or None
            artifact_part = artifact_part.strip() or None
        else:
            return _error(f'cMeta ref must have :: in "{ref}"', 1, None, fail_on_error)

        r = parse_cmeta_obj(category_part, key="category", fail_on_error=fail_on_error)
        if r['return']>0: return r
        category_parts = r['obj_parts']
    
        if not category_parts:
            return _error(f'category is not defined in cMeta ref "{ref}"', 1, None, fail_on_error)

        r = parse_cmeta_obj(artifact_part, key="artifact", fail_on_error=fail_on_error)
        if r['return']>0: return r
        artifact_parts = r['obj_parts']
    
        result = {**category_parts, **artifact_parts}
    
    return {'return': 0, 'ref_parts': result}

def restore_cmeta_ref(
        ref_parts: Dict[str, Any],   # Dict with category/artifact parts
        fail_on_error: bool = False  # If True, raise error on failure
) -> Dict[str, Any]:
    """
    Restore cMeta ref string from canonicalized dict.

    Args:
        ref_parts (Dict[str, Any]): Dict with category/artifact parts.
        fail_on_error (bool): If True, raise error on failure.

    Returns:
        Dict[str, Any]: {'return': 0, 'ref': restored_string}.
                        If error, returns {'return': 1, 'error': ...}
    """
    r = restore_cmeta_obj(ref_parts, key="category", fail_on_error=fail_on_error)
    if r['return']>0: return r
    category = r['obj']

    r = restore_cmeta_obj(ref_parts, key="artifact", fail_on_error=fail_on_error)
    if r['return']>0: return r
    artifact = r['obj']

    if category and artifact:
        ref = f"{category}::{artifact}"
    elif artifact:
        return _error(f"category is not present in cMeta ref {ref_parts} ", 1, None, fail_on_error)
    elif category:
        ref = f"{category}::"
    else:
        ref = None

    return {'return':0, 'ref':ref}

def get_sort_key_cmeta_obj_alias_or_uid(
        item: dict  # Dictionary containing 'cmeta_ref_parts' with artifact identifiers
):
    """Get a sort key from a CMeta object for sorting by alias or UID.
    
    Extracts the artifact identifier for sorting, prioritizing lowercase alias,
    then regular alias, then UID.
    
    Args:
        item (dict): Dictionary containing 'cmeta_ref_parts' with artifact identifiers.
        
    Returns:
        str or None: The artifact's lowercase alias, alias, or UID for sorting.
    """
    cmeta_ref_parts = item.get("cmeta_ref_parts", {})
    return (
        cmeta_ref_parts.get("artifact_alias_lowercase")
        or cmeta_ref_parts.get("artifact_alias")
        or cmeta_ref_parts.get("artifact_uid")
    )
