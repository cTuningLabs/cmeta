"""
Network functions

cMeta author and developer: (C) 2025 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

def normalize_tags(tags, fail_on_error = False):
    """
    """
 
    if type(tags) == str:
        tags = tags.split(',')
    elif type(tags) != list:
        return _error(f'tags should be string or list - got {type(tags)}', 1, None, fail_on_error)

    clean_tags = []

    for t in tags:
        clean_tags.append(t.strip())

    return {'return':0, 'tags': clean_tags}

def detect_cid_in_the_current_directory(cmeta, path = None, debug = False, logger = None):
    """
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

def copy_text_to_clipboard(text = '', add_quotes = False, do_not_fail = False):
    """
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

def compare_versions(version1, version2):
    """
    Compare two version strings.
    
    Parameters:
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

def access_api(url, params, headers = {}):
    """
    Send POST request to FastAPI endpoint with params and return JSON response.
    
    Parameters:
        url (str): The API endpoint URL
        params (dict): Dictionary of parameters to send as JSON
        
    Returns:
        dict: {'return': 0, 'output': dict} on success
              {'return': 1, 'error': str} on error
    """
    import requests

    try:
        response = requests.post(url, json=params, headers=headers)
        response.raise_for_status()
        
        output = response.json()
       
    except requests.exceptions.RequestException as e:
        return {'return': 1, 'error': f'API request to {url} failed: {str(e)}'}
    except ValueError as e:
        return {'return': 1, 'error': f'Failed to parse JSON response from {url}: {str(e)}'}
    except Exception as e:
        return {'return': 1, 'error': f'Unexpected error when accessing {url}: {str(e)}'}

    return {'return': 0, 'response': output}
