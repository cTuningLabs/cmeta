"""
cMeta repositories manager

cMeta author and developer: (C) 2025 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
import os
import fnmatch
import time

from . import utils
from .utils.common import _error

class Repos:
    """
    cMeta repositories manager.
    """
    
    ###################################################################################################
    def __init__(
            self,
            cfg: Dict[str, Any],             # Configuration dictionary
            home_path: Path,                 # Path to repositories directory
            index_path: Path,                # Path to index directory
            repos_config_path: Path,         # Path to repositories config file
            logger: logging.Logger = None,   # Logger instance (optional)
            index_extension: str = '.pkl',   # Index file extension
            fail_on_error: bool = False      # If True, raise exception on error
    ):
        """
        Initialize Repos manager.
        
        Args:
            cfg (Dict[str, Any]): Configuration dictionary.
            home_path (Path): Path to repositories directory.
            index_path (Path): Path to index directory.
            repos_config_path (Path): Path to repositories config file.
            logger (logging.Logger | None): Logger instance (optional).
            index_extension (str): Index file extension.
            fail_on_error (bool): If True, raise exception on error.
        """
        self.cfg = cfg
        self.home_path = home_path
 
        self.index_path = index_path
        self.file_cache = {}

        self.index_extension = index_extension

        self.repos_config_path = repos_config_path
        self._repositories = []
        self.fail_on_error = fail_on_error
        
        # Create a child logger that inherits CMeta's configuration
        self.logger = logging.getLogger(__name__) if logger is None else logger.getChild("repos")
        self.logger.debug("Initializing Repos class ...")

        self.KEY_INDEX_UIDS = 'uids'
        self.KEY_INDEX_LOWERCASE_ALIASES = 'lowercase_aliases'

    ###################################################################################################
    def init(
            self,
            con: bool = False,      # Console mode flag (for compatibility)
            verbose: bool = False   # Enable verbose output (for compatibility)
    ):
        """Initialize repositories and index if running for the first time.
        
        Creates repos directory, local repository, and triggers reindexing if needed.
        
        Args:
            con (bool): Console mode flag (for compatibility).
            verbose (bool): Enable verbose output (for compatibility).
            
        Returns:
            dict: Dictionary with 'return': 0 on success, or 'return' > 0 and 'error' on failure.
        """

        trigger_reindex = False

        home_path_local = os.path.join(self.home_path, 'local')

        # Check if repos do not exist
        if not os.path.isdir(self.home_path):
            self.logger.debug(f"Creating repos directory in {self.home_path} ...")

            os.makedirs(self.home_path)

        # Check local repo there
        if not os.path.isdir(home_path_local):
            self.logger.debug(f"Creating local repo directory in {home_path_local} ...")

            os.makedirs(home_path_local)

        repo_local_meta_file = os.path.join(home_path_local, self.cfg['repo_meta_desc'])

        if not os.path.isfile(repo_local_meta_file):
            repo_local_meta = self.cfg['repo_local_meta'].copy()
            repo_local_meta['category'] = 'repo,' + self.cfg['category_repo_uid']

            r = utils.files.safe_write_file(repo_local_meta_file, repo_local_meta, fail_on_error=self.fail_on_error, logger=self.logger)
            if r['return']>0: return r

        # Check if repo file exists
        if not os.path.isfile(self.repos_config_path):
            trigger_reindex = True

            # Need ordered dict (Python >= 3.7)
            repos_paths = {}

            # First local
            repos_paths[home_path_local]={}

            # Then internal repo
            this_module_path = os.path.dirname(os.path.abspath(__file__))
            internal_repo_path = os.path.join(this_module_path, 'internal-repo')
            repos_paths[internal_repo_path]={}

            # Do not sort keys!
            r = utils.files.safe_write_file(self.repos_config_path, repos_paths, fail_on_error=self.fail_on_error, logger=self.logger, sort_keys=False)
            if r['return']>0: return r

        if trigger_reindex or not os.path.isdir(self.index_path):
            r = self.reindex(con=con, verbose=verbose)
            if r['return'] >0: return r

        return {'return':0}

    ###################################################################################################
    def add_to_index(self, cmeta, cmeta_ref_parts, path, original_alias = None, original_uid = None):
        """
        """

        category_alias = cmeta_ref_parts['category_alias'].lower()
        artifact_uid = cmeta_ref_parts['artifact_uid']
        artifact_alias = cmeta_ref_parts.get('artifact_alias')

        # Data is taken directly from cache to be fast - it should not be changed externally
        index_file = os.path.join(self.index_path, category_alias + self.index_extension)

        r = utils.files.safe_read_file(index_file, lock=True, keep_locked=True, fail_on_error=self.fail_on_error, logger=self.logger)
        if r['return']>0: 
            if r['return']!=16: return r

            index_data = {}
            index_file_lock = None
        else:
            index_data = r['data']
            index_file_lock = r['file_lock']

        uids = index_data.setdefault(self.KEY_INDEX_UIDS, {})
        lowercase_aliases = index_data.setdefault(self.KEY_INDEX_LOWERCASE_ALIASES, {})

        # If needed, delete the original one before adding the new/updated one
        if original_alias is not None:
            artifact_alias_lowercase = original_alias.lower()
            lowercase_alias_uids = lowercase_aliases.get(artifact_alias_lowercase, [])
            if original_uid in lowercase_alias_uids:
                lowercase_alias_uids.remove(original_uid)
                if len(lowercase_alias_uids) == 0:
                    del(lowercase_aliases[artifact_alias_lowercase])

        if original_uid is not None and original_uid in uids:
            del(uids[original_uid])

        # Prepare new record
        record = {'cmeta': cmeta, 'cmeta_ref_parts': cmeta_ref_parts, 'path': path}

        uids[artifact_uid] = record

        if artifact_alias is not None: 
            artifact_alias_lowercase = artifact_alias.lower()

            lowercase_alias_uids = lowercase_aliases.get(artifact_alias_lowercase, [])

            if artifact_uid not in lowercase_alias_uids:
                lowercase_alias_uids.append(artifact_uid)
                lowercase_aliases[artifact_alias_lowercase] = lowercase_alias_uids

        # Use atomic write to avoid corrupting large index files
        r = utils.files.safe_write_file(index_file, index_data, file_lock=index_file_lock, atomic=True, fail_on_error=self.fail_on_error, logger=self.logger, sort_keys=False)
        if r['return']>0: return r

#        r = utils.files.safe_write_file(os.path.splitext(index_file)[0] + ".json", index_data, atomic=True, fail_on_error=self.fail_on_error, logger=self.logger)
#        if r['return']>0: return r

        return {'return':0}



    ###################################################################################################
    def remove_from_index(self, index_file, artifact_uid, artifact_alias_lowercase):
        """Remove an artifact from the repository index.
        
        Args:
            index_file: Path to index file.
            artifact_uid: UID of artifact to remove.
            artifact_alias_lowercase: Lowercase alias of artifact to remove from alias index.
            
        Returns:
            dict: Dictionary with 'return': 0 on success, or 'return' > 0 and 'error' on failure.
        """
        r = utils.files.safe_read_file(index_file, lock=True, keep_locked=True, fail_on_error=self.fail_on_error, logger=self.logger)
        if r['return']>0: 
            if r['return']!=16: return r

            index_data = {}
            index_file_lock = None
        else:
            index_data = r['data']
            index_file_lock = r['file_lock']

        if artifact_alias_lowercase is not None:
            lowercase_aliases = index_data.setdefault(self.KEY_INDEX_LOWERCASE_ALIASES, {})
            lowercase_alias_uids = lowercase_aliases.get(artifact_alias_lowercase, [])
            if artifact_uid in lowercase_alias_uids:
                lowercase_alias_uids.remove(artifact_uid)
                if len(lowercase_alias_uids) == 0:
                    del(lowercase_aliases[artifact_alias_lowercase])

        uids = index_data.setdefault(self.KEY_INDEX_UIDS, {})

        if artifact_uid in uids:
            del(uids[artifact_uid])

        r = utils.files.safe_write_file(index_file, index_data, file_lock=index_file_lock, atomic=True, fail_on_error=self.fail_on_error, logger=self.logger)
        if r['return']>0: return r

#        r = utils.files.safe_write_file(os.path.splitext(index_file)[0] + ".json", index_data, atomic=True, fail_on_error=self.fail_on_error, logger=self.logger)
#        if r['return']>0: return r

        return {'return':0}

    ###################################################################################################
    def find_in_index(self, category_alias, category_uid, artifact_alias = None, artifact_uid = None, repos = [], only_uids=False, add_index_file=False, skip_uids=False):
        """Find artifacts in the repository index.
        
        Args:
            category_alias: Lowercase category alias.
            category_uid: Category UID.
            artifact_alias: Artifact alias to search for.
            artifact_uid: Artifact UID to search for.
            repos: List of repository names to search in.
            only_uids: If True, return only UIDs without full metadata.
            add_index_file: If True, include index_file path in result.
            skip_uids: If True, skip UID validation.
            
        Returns:
            dict: Dictionary with 'return': 0 and 'lst' containing found artifacts,
                  or 'return' > 0 and 'error' on failure.
        """
        category_alias = category_alias.lower()

        # Data is taken directly from cache to be fast - it should not be changed externally
        index_file = os.path.join(self.index_path, category_alias + self.index_extension)

        r = utils.files.safe_read_file_via_cache(index_file, cache=self.file_cache, fail_on_error=self.fail_on_error, logger=self.logger)
        if r['return']>0: 
            if r['return']!=16: return r
            index = {}
        else:
            # Data from cache - do not change!
            index = r['data']

        artifact_uids = []

        if artifact_uid is not None and artifact_uid != "":
            if artifact_uid not in index.get(self.KEY_INDEX_UIDS, {}):
                x = f'"{artifact_alias}" ({artifact_uid})' if artifact_alias is not None and artifact_alias != '' else f'{artifact_uid}'
                err = f'{category_alias} artifact {x} not found'
                return _error(err, 16, None, self.fail_on_error)

            artifact_uids.append(artifact_uid)

        elif artifact_alias is not None and artifact_alias != "":
            artifact_alias_lowercase = artifact_alias.lower()
            if '*' in artifact_alias or '?' in artifact_alias:
                check_artifact_uids = list(index.get(self.KEY_INDEX_UIDS, {}).keys())

                for artifact_uid in check_artifact_uids:
                    if artifact_uid not in index[self.KEY_INDEX_UIDS]:
                        return _error(f'corrupted {category_alias} UID "{artifact_uid}" not found in the index"', 1, None, self.fail_on_error)

                    record = index[self.KEY_INDEX_UIDS][artifact_uid]

                    lowercase_alias = record['cmeta_ref_parts'].get('artifact_alias_lowercase', None)
                    if lowercase_alias is None:
                        lowercase_alias = record['cmeta_ref_parts'].get('artifact_alias', '') 
                        if not skip_uids and lowercase_alias == '':
                            lowercase_alias = artifact_uid

                    if fnmatch.fnmatch(lowercase_alias, artifact_alias_lowercase):
                        artifact_uids.append(artifact_uid)
            else:
                if artifact_alias_lowercase not in index.get(self.KEY_INDEX_LOWERCASE_ALIASES, {}):
                    # We should not be failing below even on debug to handle multiple-search - we need to handle aggregated search results
                    x_artifact_alias = "artifacts" if artifact_alias == '' or artifact_alias == None or artifact_alias == '*' else f'"{artifact_alias}"'
                    return _error(f'{category_alias} {x_artifact_alias} not found', 16, None, False) #self.fail_on_error)

                artifact_uids.extend(index[self.KEY_INDEX_LOWERCASE_ALIASES][artifact_alias_lowercase])

        else:
            artifact_uids = list(index.get(self.KEY_INDEX_UIDS, {}).keys())

        result = {'return':0, 'index_file': index_file, 'index': index}

        # Check if prune by repos
        if repos or category_uid is not None:
            pruned_artifact_uids = []

            for artifact_uid in artifact_uids:
                if artifact_uid not in index[self.KEY_INDEX_UIDS]:
                    return _error(f'corrupted index for {category_alias} UID "{artifact_uid}"', 1, None, self.fail_on_error)

                artifact_cmeta_ref_parts = index[self.KEY_INDEX_UIDS][artifact_uid]['cmeta_ref_parts']

                if repos and artifact_cmeta_ref_parts['repo_uid'] not in repos:
                    continue

                if category_uid is not None and artifact_cmeta_ref_parts['category_uid'] != category_uid:
                    continue

                pruned_artifact_uids.append(artifact_uid)

            artifact_uids = pruned_artifact_uids

        if only_uids:
            result['artifact_uids'] = artifact_uids
        else:
            artifacts = []

            for artifact_uid in artifact_uids:
                if artifact_uid not in index[self.KEY_INDEX_UIDS]:
                    return _error(f'corrupted index for {category_alias} UID "{artifact_uid}"', 1, None, self.fail_on_error)

                artifact = index[self.KEY_INDEX_UIDS][artifact_uid].copy()

                if add_index_file:
                    artifact['index_file'] = index_file

                artifacts.append(artifact)

            result['artifacts'] = artifacts

        return result

    ###################################################################################################
    def find_in_file_system(self, category_meta, category_alias, category_uid, artifact_alias = None, artifact_uid = None, repo_uids = []):
        """
        Find artifacts by scanning directories instead of using index.
        Used for categories with no_index flag.
        
        Args:
            category_alias: Category alias (lowercase)
            category_uid: Category UID
            artifact_alias: Optional artifact alias (supports wildcards)
            artifact_uid: Optional artifact UID
           
        Returns:
            dict: {'return': 0, 'artifacts': [...]} or error
        """

        # Get repo artifacts
        repo_artifacts = []

        if repo_uids == None:
            repo_uids = ['*']

        for repo_uid in repo_uids:
            repo_alias = None
            if repo_uid == '*':
                repo_alias = '*'
                repo_uid = None

            r = self.find_in_index('repo', self.cfg['category_repo_uid'], repo_alias, repo_uid)
            if r['return'] >0: return r
            repo_artifacts += r['artifacts']

        # Iterate over repos:
        artifacts = []

        for repo_artifact in repo_artifacts:
            repo_path = repo_artifact['path']
            repo_meta = repo_artifact['cmeta']

            repo_cmeta_ref_parts = repo_artifact['cmeta_ref_parts']

            repo_alias = repo_cmeta_ref_parts.get('artifact_alias')
            repo_uid = repo_cmeta_ref_parts['artifact_uid']

            if category_uid in repo_meta.get('sharding_slices', {}):
                sharding_slices = repo_meta['sharding_slices'][category_uid]
            else:
                sharding_slices = category_meta.get('sharding_slices')

            # Get category path
            path_to_category = os.path.join(repo_path, category_alias)
            if os.path.isdir(path_to_category):
                # Look for artifacts
                r = self._find_artifacts(repo_meta, repo_alias, repo_uid, category_meta, category_alias, category_uid, path_to_category, 
                                         False, False, None, 0, 
                                         artifact_alias = artifact_alias, artifact_uid = artifact_uid)
                if r['return'] >0: return r
                
                artifacts += r['artifacts']
        
        return {'return': 0, 'artifacts': artifacts}

    ###################################################################################################
    def find(self, cmeta_ref, add_index_file=False, tags=None, skip_uids=False):
        """Find artifacts by cMeta reference.
        
        Args:
            cmeta_ref: cMeta reference string or parsed dictionary.
            add_index_file: If True, include index_file path in result.
            tags: Optional tags to filter results.
            skip_uids: If True, skip UID validation.
            
        Returns:
            dict: Dictionary with 'return': 0 and 'artifacts' list on success,
                  or 'return' > 0 and 'error' on failure.
        """

        # Parse cMeta ref
        if isinstance(cmeta_ref, str):
            r = utils.names.parse_cmeta_ref(cmeta_ref, fail_on_error = self.fail_on_error)
            if r['return'] >0: return r
            cmeta_ref_parts = r['ref_parts']
        else:
            cmeta_ref_parts = cmeta_ref

        # Check tags
        if tags != None:
            r = utils.common.normalize_tags(tags, fail_on_error = self.fail_on_error)
            if r['return'] >0: return r

            tags = r['tags']

        # Unpack to search
        category_alias = cmeta_ref_parts.get('category_alias')
        category_uid = cmeta_ref_parts.get('category_uid')

        category_repo_alias = cmeta_ref_parts.get('category_repo_alias')
        category_repo_uid = cmeta_ref_parts.get('category_repo_uid')

        artifact_alias = cmeta_ref_parts.get('artifact_alias')
        artifact_uid = cmeta_ref_parts.get('artifact_uid')

        artifact_repo_alias = cmeta_ref_parts.get('artifact_repo_alias')
        artifact_repo_uid = cmeta_ref_parts.get('artifact_repo_uid')

        # Disambiguate repos
        category_repo_artifacts = None
        if (category_repo_uid is not None and category_repo_uid != '') or (category_repo_alias is not None and category_repo_alias != ''):
            r = self.find_in_index('repo', self.cfg['category_repo_uid'], category_repo_alias, category_repo_uid, only_uids=True, skip_uids=skip_uids)
            if r['return'] >0: return r
            category_repo_artifacts = r['artifact_uids']

        # Disambiguate categories (need UID and alias)
        r = self.find_in_index('category', 'dd9ea50e7f76467f', category_alias, category_uid, repos = category_repo_artifacts, skip_uids=skip_uids)
        if r['return'] >0: return r

        category_artifacts = r['artifacts']

        artifacts = []

        if category_artifacts:

            artifact_repo_artifacts = None
            if (artifact_repo_uid is not None and artifact_repo_uid != '') or (artifact_repo_alias is not None and artifact_repo_alias != ''):
                r = self.find_in_index('repo', self.cfg['category_repo_uid'], artifact_repo_alias, artifact_repo_uid, only_uids=True, skip_uids=skip_uids)
                if r['return'] >0: return r
                artifact_repo_artifacts = r['artifact_uids']

            # Find artifacts
            for category in category_artifacts:
                # category_alias should always exist until we, by accident, add non-aliased category (UID)
                category_alias = category['cmeta_ref_parts'].get('artifact_alias')

                if category_alias is None or category_alias=="": # or category_alias=='repo':
                    continue

                category_uid = category['cmeta_ref_parts']['artifact_uid']

                category_cmeta = category['cmeta']

                if category_cmeta.get('no_index', False):
                    r = self.find_in_file_system(category_cmeta, category_alias, category_uid, artifact_alias, artifact_uid, repo_uids = artifact_repo_artifacts)
                    if r['return'] >0: 
                        if r['return'] == 16:
                            # If index not found
                            continue
                        return r

                else:
                    r = self.find_in_index(category_alias, category_uid, artifact_alias, artifact_uid, repos = artifact_repo_artifacts, add_index_file = add_index_file, skip_uids=skip_uids)
                    if r['return'] >0: 
                        if r['return'] == 16:
                            # If index not found
                            continue

                        return r

                # Check conditions
                add_artifacts = []

                if tags != None and len(tags)>0:
                    for a in r['artifacts']:
                        cmeta = a['cmeta']
                        ctags = cmeta.get('tags', [])

                        if type(ctags) != list:
                            cmeta_ref_parts = a['cmeta_ref_parts']
                            cmeta_ref_parts_artifact_alias = cmeta_ref_parts['artifact_alias']
                            cmeta_ref_parts_artifact_uid = cmeta_ref_parts['artifact_uid']
                            return {'return':1, 'error':f'tags are corrupted for artifact "{cmeta_ref_parts_artifact_alias},{cmeta_ref_parts_artifact_uid}"'}

                        if all(str(tag).lower() in [str(ctag).lower() for ctag in ctags] for tag in tags):
                            add_artifacts.append(a)

                else:
                    add_artifacts = r['artifacts']

                # Adding artifacts
                artifacts.extend(add_artifacts)

        if len(artifacts) == 0:
            x_artifact_alias = "artifacts" if artifact_alias == '' or artifact_alias == None else f'"{artifact_alias}"'
            return _error(f'{category_alias} {x_artifact_alias} not found', 16, None, False) #self.fail_on_error)

        return {'return':0, 'artifacts':artifacts}




    ######################################################################################################################
    def reindex(self, con=False, verbose=False):
        """Clean index and reindex all repositories.
        
        Removes existing index files and rebuilds them by scanning all repositories.
        
        Args:
            con: If True, print console messages during reindexing.
            verbose: If True, print detailed progress information.
            
        Returns:
            dict: Dictionary with 'return': 0 on success, or 'return' > 0 and 'error' on failure.
        """

        return self.index(clean=True, con=con, verbose=verbose)
    

    def index(self, clean=False, con=False, verbose=False, add_repo_paths=[], delete_repo_paths=[]):
        """
        Index repos
        """

        from tqdm import tqdm

        import time
        time_start = time.time()

        index_path = self.index_path

        conx = True if verbose else False

        if conx:
            print ('='*40)
        if con:
            print ('Reindexing all repos - it can take some time ...')
        if conx:
            print ('')
            print (f'Index path:     {index_path}')


        ######################################################################################################################
        # Clean index files besides repo and category
        if clean:
            if conx:
                print('')
                print(f'Cleaning existing index files in {index_path} ...')
            
            try:
                for filename in os.listdir(index_path):
                    if filename.endswith(self.index_extension):
                        file_path = os.path.join(index_path, filename)
                        if os.path.isfile(file_path):
                            os.remove(file_path)
#                            if conx:
#                                print(f'  Removed: {filename}')

            except Exception as e:
                if self.fail_on_error:
                    return {'return': 1, 'error': f'Failed to clean index files: {str(e)}'}
                else:
                    self.logger.warning(f'Failed to clean some index files: {str(e)}')


        ######################################################################################################################
        # Re-reading repo paths file and checking paths

        repos_meta = {}
        repos_config_path = self.repos_config_path

        # Then checking internal repo path
        this_module_path = os.path.dirname(os.path.abspath(__file__))

        force_internal_repo_path = os.environ.get(self.cfg['env_var_internal_repo_path'], '').strip()
        if force_internal_repo_path != '':
            this_internal_repo_path = force_internal_repo_path
        else:
            this_internal_repo_path = os.path.join(this_module_path, 'internal-repo')

        existing_internal_repo_path = None

        if conx:
            print (f'Repo file path: {repos_config_path}')


        r = utils.files.safe_read_file(repos_config_path, retry_if_not_found=3, fail_on_error=self.fail_on_error, logger=self.logger)
        if r['return']>0: return r 

        paths_to_repos = {}
        original_paths_to_repos = r['data']

        to_update = False

        for path in original_paths_to_repos:
            extra_meta = original_paths_to_repos[path].get('meta',{})

            if path.endswith('internal-repo') and os.path.normpath(path) != this_internal_repo_path:
                path = this_internal_repo_path
                to_update = True

            path_to_repo_desc = os.path.join(path, self.cfg['repo_meta_desc'])

            if not os.path.isfile(path_to_repo_desc):
                to_update = True
            else:
                r = utils.files.safe_read_file(path_to_repo_desc, retry_if_not_found=3, fail_on_error=self.fail_on_error, logger=self.logger)
                if r['return']==0: 
                    repo_meta = r['data']

                    if len(extra_meta)>0:
                        repo_meta.update(extra_meta)

                    repos_meta[path] = repo_meta

                    paths_to_repos[path] = {}

        if to_update:
            # Do not sort keys - preserve order!
            r = utils.files.safe_write_file(repos_config_path, paths_to_repos, atomic=True, fail_on_error=self.fail_on_error, logger=self.logger, sort_keys=False)
            if r['return']>0: return r

        if len(paths_to_repos) == 0:
            return {'return':1, 'error':f'could not find any repository in {repos_config_path}'}

        ######################################################################################################################
        # Indexing repos ...
        index_repo_file = os.path.join(index_path, 'repo' + self.index_extension)

        index_repos = {self.KEY_INDEX_UIDS:{}, self.KEY_INDEX_LOWERCASE_ALIASES:{}}
        repo_uids_to_use = []

        if conx:
            print ('')
            print ('Indexing repositories ...')
            print ('')

        for path in paths_to_repos.keys():
            repo_meta = repos_meta[path]

            full_path = _get_full_path(path, repo_meta)
                  
            if conx:
                print (f'  Analyzing repository in {full_path} ...')
                
            artifact_name = repo_meta['artifact']

            r = utils.names.parse_cmeta_name(artifact_name)
            if r['return']>0: return r
            cmeta_name_parts = r['name']

            uid = cmeta_name_parts.get('uid')
            alias = cmeta_name_parts.get('alias')
            lowercase_alias = alias.lower()

#                # Change to proper artifact and category
#                if 'artifact' not in repo_meta:
#                    repo_meta['artifact'] = alias + ','+uid
            if 'category' not in repo_meta:
                repo_meta['category'] = 'repo,' + self.cfg['category_repo_uid']

            if conx:
                print (f"    CID = {lowercase_alias},{uid}")

            repo_uids_to_use.append(uid.lower())

            if lowercase_alias in index_repos[self.KEY_INDEX_LOWERCASE_ALIASES]:
                print (f'      Warning: repo "{alias}" is already in index!')

                if uid is not None and uid in index_repos[self.KEY_INDEX_LOWERCASE_ALIASES][lowercase_alias]:
                    return {'return':1, 'error': f'ambiguity - repo "{alias}" with the same UID "{uid}" alredy exists in the index - please fix it!'}

            index_repos[self.KEY_INDEX_LOWERCASE_ALIASES][alias] = [uid]

            entry = {'path': path, 'full_path':full_path}

            cmeta_ref_parts = {'category_alias':'repo', 'category_uid':self.cfg['category_repo_uid'], 'artifact_alias':alias, 'artifact_uid':uid}

            if alias != alias.lower():
                cmeta_ref_parts['artifact_alias_lowercase'] = alias.lower()

            entry['cmeta_ref_parts'] = cmeta_ref_parts

            method = ''
            path_git = os.path.join(path, '.git')
            if os.path.isdir(path_git):
                method = 'git'

            entry['cmeta'] = repo_meta.copy()
            entry['cmeta']['method'] = method
            # Keep clean copy just in case
            entry['_cmr'] = repo_meta

            index_repos[self.KEY_INDEX_UIDS][uid] = entry

        if conx:
            print('')
            print(f'  Recording repo index file: {index_repo_file}')

        # Use atomic write to avoid corrupting large index files
        r = utils.files.safe_write_file(index_repo_file, index_repos, atomic=True, fail_on_error=self.fail_on_error, logger=self.logger, sort_keys=False)
        if r['return']>0: return r
    
        ######################################################################################################################
        # Indexing categories
        index_categories = {self.KEY_INDEX_UIDS:{}, self.KEY_INDEX_LOWERCASE_ALIASES:{}}

        if conx:
            print ('')
            print ('Indexing categories ...')
            print ('')

        categories = []
        categories_to_index = []

        for path in paths_to_repos:
            repo_meta = repos_meta[path]

            repo_full_path = _get_full_path(path, repo_meta)
            category_full_path = os.path.join(repo_full_path, 'category')

            if os.path.isdir(category_full_path):
                if conx:
                    print (f'  Processing categories in {category_full_path} ...')

                category_dirs = os.listdir(category_full_path)

                for category in sorted(category_dirs):
                    category_meta_desc_file_json = os.path.join(category_full_path, category, self.cfg['meta_filename_base'] + '.json')
                    category_meta_desc_file_yaml = os.path.join(category_full_path, category, self.cfg['meta_filename_base'] + '.yaml')

                    category_meta = {}
                    
                    if os.path.isfile(category_meta_desc_file_yaml):
                        r = utils.files.safe_read_file(category_meta_desc_file_yaml, retry_if_not_found=3, fail_on_error=self.fail_on_error, logger=self.logger)
                        if r['return']==0: 
                            category_meta = r['data']
                    elif os.path.isfile(category_meta_desc_file_json):
                        r = utils.files.safe_read_file(category_meta_desc_file_json, retry_if_not_found=3, fail_on_error=self.fail_on_error, logger=self.logger)
                        if r['return']==0: 
                            category_meta = r['data']
                    else:
                        # Checking older format
                        category_meta_desc_file_json = os.path.join(category_full_path, category, '_cm.json')
                        category_meta_desc_file_yaml = os.path.join(category_full_path, category, '_cm.yaml')

                        if os.path.isfile(category_meta_desc_file_yaml):
                            r = utils.files.safe_read_file(category_meta_desc_file_yaml, retry_if_not_found=3, fail_on_error=self.fail_on_error, logger=self.logger)
                            if r['return']==0: 
                                category_meta = r['data']
                        elif os.path.isfile(category_meta_desc_file_json):
                            r = utils.files.safe_read_file(category_meta_desc_file_json, retry_if_not_found=3, fail_on_error=self.fail_on_error, logger=self.logger)
                            if r['return']==0: 
                                category_meta = r['data']

                        if category_meta:
                            # Update to new format
                            uid = category_meta['uid']
                            alias = category_meta.get('alias')

                            category_meta['artifact'] = uid
                            category_meta['category'] = 'category,dd9ea50e7f76467f'

                            for key in ['uid', 'alias', 'automation_uid', 'automation_alias']:
                                if key in category_meta:
                                    del(category_meta[key])

                            category_meta_desc_file_yaml = os.path.join(category_full_path, category, self.cfg['meta_filename_base'] + '.yaml')

                            r = utils.files.safe_write_file(category_meta_desc_file_yaml, category_meta, fail_on_error=self.fail_on_error, logger=self.logger)
                            if r['return']>0: return r

                    if category_meta:
                        category_path = os.path.join(category_full_path, category)

                        category_entry = {'category':category, 'meta':category_meta}

                        categories.append(category_entry)

                        if path in add_repo_paths:
                            categories_to_index.append(category_entry)


                        category_name = category_meta['artifact']
#                        if conx:
#                            print (f'    Found category "{category}"')

                        r = utils.names.parse_cmeta_name(category_name)
                        if r['return']>0: return r
                        cmeta_name_parts = r['name']

                        uid = cmeta_name_parts.get('uid')
                        alias = cmeta_name_parts.get('alias')
                        if alias == None:
                            alias = category
                        if alias != None:
                            lowercase_alias = alias.lower()

                        if alias is not None and lowercase_alias in index_categories[self.KEY_INDEX_LOWERCASE_ALIASES]:
                            print (f'      Warning: category "{alias}" already exists in the index!')

                            if uid is not None and uid in index_categories[self.KEY_INDEX_LOWERCASE_ALIASES][lowercase_alias]:
                                xpath = index_categories[self.KEY_INDEX_UIDS][uid]['path']
                                return {'return':1, 'error': f'ambiguity - category "{alias}" with the same UID "{uid}" and path "{xpath}" alredy exists in the index - please fix it!'}

                        cmeta_ref_parts = {'category_alias':'category', 'category_uid':'dd9ea50e7f76467f', 'artifact_uid':uid}

                        if alias is not None and alias != '':
                            uids = index_categories[self.KEY_INDEX_LOWERCASE_ALIASES].get(lowercase_alias, [])
                            uids.append(uid)
                            index_categories[self.KEY_INDEX_LOWERCASE_ALIASES][lowercase_alias] = uids

                            if len(uids)>1:
                                print (f'      Warning: AMBIGUITY for category "{alias}": more than 1 UID found in paths:')
                                for uid in uids:
                                     if uid in index_categories[self.KEY_INDEX_UIDS]:
                                         print ('               * ' + index_categories[self.KEY_INDEX_UIDS][uid]['path'])
                                print ('               * ' + category_path)
                                if con:
                                    input ('               Fix it or press Enter to continue!')

                            cmeta_ref_parts['artifact_alias'] = alias
                            if alias != alias.lower():
                                cmeta_ref_parts['artifact_alias_lowercase'] = lowercase_alias

                        repo_name = repo_meta['artifact']
                        r = utils.names.parse_cmeta_name(repo_name)
                        if r['return']>0: return r
                        repo_name_parts = r['name']

                        repo_alias = repo_name_parts.get('alias')
                        repo_uid = repo_name_parts.get('uid')   

                        if repo_alias is not None and repo_alias != '':
                            cmeta_ref_parts['repo_alias'] = repo_alias

                        if repo_uid is not None and repo_uid != '':
                            cmeta_ref_parts['repo_uid'] = repo_uid

                        entry = {'path': category_path}

                        entry['cmeta_ref_parts'] = cmeta_ref_parts

                        entry['cmeta'] = category_meta

                        index_categories[self.KEY_INDEX_UIDS][uid] = entry

        if index_categories[self.KEY_INDEX_UIDS]:
            index_category_file = os.path.join(index_path, 'category' + self.index_extension)
            if conx:
                print('')
                print(f'  Recording category index file ({len(index_categories[self.KEY_INDEX_UIDS])} categories found): {index_category_file}')

            # Use atomic write to avoid corrupting large index files
            r = utils.files.safe_write_file(index_category_file, index_categories, atomic=True, fail_on_error=self.fail_on_error, logger=self.logger, sort_keys=False)
            if r['return']>0: return r


        # Clean removed category indexes
        if conx:
            print('')
            print(f'Cleaning unused category files in {index_path} ...')

        all_category_filenames = ['category' + self.index_extension, 
                                  'repo' + self.index_extension]
        for category_mix in categories:
            all_category_filenames.append(category_mix['category'] + self.index_extension)
        
        try:
            for filename in os.listdir(index_path):
                if filename.endswith(self.index_extension):
                    if filename not in all_category_filenames:
                        file_path = os.path.join(index_path, filename)
                        if os.path.isfile(file_path):
                            os.remove(file_path)

        except Exception as e:
            if self.fail_on_error:
                return {'return': 1, 'error': f'Failed to clean index files: {str(e)}'}
            else:
                self.logger.warning(f'Failed to clean some index files: {str(e)}')

        ######################################################################################################################
        # Indexing artifacts
        index_artifacts = {}

        artifact_num = 0
        if clean or len(add_repo_paths)>0:

            if conx:
                print ('')
                print ('Indexing artifacts ...')
                print ('')

#            selected_paths_to_repos = add_repo_paths if len(add_repo_paths)>0 else paths_to_repos
            # We go through all repos but check all or selected categories only
            selected_paths_to_repos = paths_to_repos

            for path in selected_paths_to_repos:
                repo_meta = repos_meta[path]

                repo_name = repo_meta['artifact']

                r = utils.names.parse_cmeta_name(repo_name)
                if r['return']>0: return r
                cmeta_name_parts = r['name']

                repo_uid = cmeta_name_parts.get('uid')
                repo_alias = cmeta_name_parts.get('alias')

                repo_full_path = _get_full_path(path, repo_meta)

                if conx:
                    print (f'  Processing repo in {repo_full_path} ...')

                selected_categories = categories_to_index if len(add_repo_paths)>0 else categories

                for category_mix in selected_categories:

                    category = category_mix['category']

                    # Skip already index categories (repo and category)
                    if category in ['category', 'repo']:
                        continue

                    category_meta = category_mix['meta']

                    if category_meta.get('no_index', False):
                        continue

                    category_name = category_meta['artifact']

                    r = utils.names.parse_cmeta_name(category_name)
                    if r['return']>0: return r
                    cmeta_name_parts = r['name']

                    category_uid = cmeta_name_parts.get('uid')
                    category_alias = category

                    full_category_name = f'{category},' + category_uid

                    path_to_category = os.path.join(repo_full_path, category)

                    r = self._find_artifacts(repo_meta, repo_alias, repo_uid, category_meta, category_alias, category_uid, path_to_category, 
                                             con, conx, index_artifacts, artifact_num)
                    if r['return'] >0: return r

                    an = r['artifact_num']
                    artifact_num = an

        else:
            for category_mix in categories:
                index_artifacts[category_mix['category']] = {}

        if index_artifacts:
            if conx:
                print ('')
                print (f'Recording index files for artifacts in {index_path} ...')

            for category in tqdm(sorted(index_artifacts), disable = not (con and conx), desc="  Recording index file: "): 
                category_index = index_artifacts[category]

                index_artifact_file = os.path.join(index_path, category + self.index_extension)

#                if conx:
#                    print(f'  Recording {category} index file: {index_artifact_file}')

                existing_category_index = {}
                index_file_lock = None
                atomic_flag = False

                if clean:
                    existing_category_index = category_index

                else:
                    if os.path.isfile(index_artifact_file):
                        atomic_flag = True

                        r = utils.files.safe_read_file(index_artifact_file, lock=True, keep_locked=True, fail_on_error=self.fail_on_error, logger=self.logger)
                        if r['return']>0: return r

                        existing_category_index = r['data']
                        index_file_lock = r['file_lock']

                    if len(add_repo_paths)>0 or len(delete_repo_paths)>0:
                        uids = existing_category_index.setdefault(self.KEY_INDEX_UIDS, {})
                        lowercase_aliases = existing_category_index.setdefault(self.KEY_INDEX_LOWERCASE_ALIASES, {})

                        # Remove UIDs of old/updated repos
                        for uid in list(uids.keys()):
                            artifact = uids[uid]
                            path = artifact['path']

                            for remove_path in add_repo_paths + delete_repo_paths:
                                if utils.files.is_path_within(remove_path, path):
                                    del(uids[uid])
                                    break

                        # Remove aliases
                        updated_uids_keys = list(uids.keys())
                        for lowercase_alias in list(lowercase_aliases.keys()):
                            for uid in lowercase_aliases[lowercase_alias]:
                                if uid not in updated_uids_keys:
                                    del(lowercase_aliases[lowercase_alias])
                                    break

                        if len(add_repo_paths)>0:
                            # Merge new ones
                            new_uids = category_index.get(self.KEY_INDEX_UIDS, {})
                            new_lowercase_aliases = category_index.get(self.KEY_INDEX_LOWERCASE_ALIASES, {})

                            for uid in new_uids:
                                uids[uid] = new_uids[uid]

                            for lowercase_alias in new_lowercase_aliases:
                                if lowercase_alias not in lowercase_aliases:
                                    lowercase_aliases[lowercase_alias] = []
                                lowercase_aliases[lowercase_alias] += new_lowercase_aliases[lowercase_alias]

                    artifact_num += len(existing_category_index.get(self.KEY_INDEX_UIDS, {}))

                r = utils.files.safe_write_file(index_artifact_file, existing_category_index, file_lock=index_file_lock, 
                                                atomic=atomic_flag, fail_on_error=self.fail_on_error, logger=self.logger, sort_keys=False)
                if r['return']>0: return r

        
        time_end = time.time()
        elapsed = time_end - time_start

        if conx:
            print ('')
            print (f'Number of index artifacts: {artifact_num}')
            print (f'Indexing time: {elapsed:.2f} sec.')
            print ('='*40)

        r = {'return':0, 'elapsed_time':elapsed}
        return r


    ################################################################################
    def _find_artifacts(self, repo_meta, repo_alias, repo_uid, category_meta, category_alias, category_uid, path_to_category, 
                              con, conx, index_artifacts, artifact_num,
                              artifact_alias = None, artifact_uid = None):
        """Find and index artifacts in a category directory.
        
        Args:
            repo_meta: Repository metadata dictionary.
            repo_alias: Repository alias.
            repo_uid: Repository UID.
            category_meta: Category metadata dictionary.
            category_alias: Category alias.
            category_uid: Category UID.
            path_to_category: Path to category directory.
            con: If True, enable console output.
            conx: If True, enable extended console output.
            index_artifacts: Dictionary to populate with found artifacts (None for searching without indexing).
            artifact_num: Current artifact count.
            artifact_alias: Optional artifact alias to filter results (supports wildcards).
            artifact_uid: Optional artifact UID to filter results.
            
        Returns:
            dict: Dictionary with 'return': 0, 'artifacts' list, and 'artifact_num' on success,
                  or 'return' > 0 and 'error' on failure.
        """

        from tqdm import tqdm

        artifacts = []

        category = category_alias

        if category_uid in repo_meta.get('sharding_slices', {}):
            sharding_slices = repo_meta['sharding_slices'][category_uid]
        else:
            sharding_slices = category_meta.get('sharding_slices')

        if os.path.isdir(path_to_category):
            if conx:
                print (f'    Processing category {category} ...', flush=True)


            if index_artifacts is not None:
                # TBD sharding
                if sharding_slices is not None:
                    # Pass artifact_alias for smart shard pruning when not indexing
                    search_alias = artifact_alias if index_artifacts is None else None
                    artifact_dirs = _get_artifacts_from_sharded_path(path_to_category, sharding_slices, artifact_alias=search_alias)
                else:
                    artifact_dirs = os.listdir(path_to_category)

                tmp_artifact_dirs = tqdm(artifact_dirs, disable = not (con and conx), desc="      Indexing artifacts: ")

            else:
                # Filter artifact_dirs if searching without index
                tmp_artifact_dirs = []

                if artifact_alias is None or artifact_alias == '':
                    artifact_alias = '*'

                artifact_alias_lowercase = artifact_alias.lower()
                
                if '*' in artifact_alias or '?' in artifact_alias:
                    if sharding_slices is not None:
                        tmp_artifact_dirs = _get_artifacts_from_sharded_path(path_to_category, sharding_slices, artifact_alias=artifact_alias)
                    else:
                        tmp_artifact_dirs = os.listdir(path_to_category)

                else:
                    last_artifact_dirs_parent = None
                    path_to_category_with_shard = path_to_category

                    if sharding_slices is not None:
                        r = utils.files.apply_sharding_to_path(None, artifact_alias, sharding_slices)
                        if r['return']>0: return r

                        last_artifact_dirs = r['sharded_parts']
                        if len(last_artifact_dirs)>0:
                            last_artifact_dirs_parent = os.path.join(*(last_artifact_dirs[:-1]))
                            path_to_category_with_shard = os.path.join(path_to_category, last_artifact_dirs_parent)

                    if os.path.isdir(path_to_category_with_shard):
                        for artifact_dir in os.listdir(path_to_category_with_shard):
                            if artifact_dir.lower() == artifact_alias_lowercase:
                                tmp_dir = artifact_dir if last_artifact_dirs_parent is None else os.path.join(last_artifact_dirs_parent, artifact_dir)
                                tmp_artifact_dirs.append(tmp_dir)
                                break


            for long_artifact in tmp_artifact_dirs:
                artifact = os.path.basename(long_artifact)

                path_to_artifact = os.path.join(path_to_category, long_artifact)

                artifact_meta_desc_file_json = os.path.join(path_to_artifact, self.cfg['meta_filename_base'] + '.json')
                artifact_meta_desc_file_yaml = os.path.join(path_to_artifact, self.cfg['meta_filename_base'] + '.yaml')

                artifact_meta = {}

                if os.path.isfile(artifact_meta_desc_file_yaml):
                    r = utils.files.safe_read_file(artifact_meta_desc_file_yaml, retry_if_not_found=3, fail_on_error=self.fail_on_error, logger=self.logger)
                    if r['return']==0: 
                        artifact_meta = r['data']
                elif os.path.isfile(artifact_meta_desc_file_json):
                    r = utils.files.safe_read_file(artifact_meta_desc_file_json, retry_if_not_found=3, fail_on_error=self.fail_on_error, logger=self.logger)
                    if r['return']==0: 
                        artifact_meta = r['data']

                if artifact_meta:
                    if index_artifacts is None:
                        r = utils.names.parse_cmeta_name(artifact_meta['category'])
                        if r['return']>0: return r

                        cmeta_category_name_parts = r['name']

                        if cmeta_category_name_parts['uid'] != category_uid:
                            continue

                        cmeta_category_alias = cmeta_category_name_parts.get('alias')
                        if cmeta_category_alias is not None and cmeta_category_alias !='' and cmeta_category_alias != category_alias:
                            continue

                    if 'artifact' not in artifact_meta:
                        print ('', flush=True)
                        print (f"           Warning: {artifact} doesn't have 'artifact' key in {path_to_artifact}")
                        self.logger.error (f"           Warning: {artifact} doesn't have proper 'artifact' key in {path_to_artifact}")

                        # TBD - better handling?
                        continue

                    artifact_name = artifact_meta['artifact']

                    r = utils.names.parse_cmeta_name(artifact_name)
                    if r['return']>0: return r
                    cmeta_name_parts = r['name']

                    uid = cmeta_name_parts.get('uid')
                    if uid is None or not utils.names.is_valid_cmeta_uid(uid):
                        print ('', flush=True)
                        print (f"           Warning: {artifact} doesn't have proper {uid}")
                        self.logger.error (f"           Warning: {artifact} doesn't have proper {uid}")

                        # TBD - better handling?
                        continue

                    if artifact_uid is not None and artifact_uid != uid:
                        continue

                    alias = artifact
                    lowercase_alias = alias.lower()

                    entry = {'path':path_to_artifact, 'cmeta':artifact_meta}

                    cmeta_ref_parts = {'artifact_uid':uid, 'category_uid':category_uid, 'repo_uid':repo_uid}
                    if alias is not None and alias != "": 
                        cmeta_ref_parts['artifact_alias'] = alias
                        if alias != alias.lower():
                            cmeta_ref_parts['artifact_alias_lowercase'] = alias.lower()
                    if category_alias is not None and category_alias!="": 
                        cmeta_ref_parts['category_alias'] = category_alias
                    if repo_alias is not None and repo_alias!="": 
                        cmeta_ref_parts['repo_alias'] = repo_alias
                    entry['cmeta_ref_parts'] = cmeta_ref_parts

                    if index_artifacts is None:
                        artifacts.append(entry)

                    else:
                        artifact_num += 1

                        if category not in index_artifacts:
                            index_artifacts[category] = {self.KEY_INDEX_UIDS:{}, self.KEY_INDEX_LOWERCASE_ALIASES:{}}

                        uids = index_artifacts[category][self.KEY_INDEX_UIDS]
                        aliases_lower_case = index_artifacts[category][self.KEY_INDEX_LOWERCASE_ALIASES]

                        if uid in uids:
                            xpath = uids[uid]['path']
                            if xpath != path_to_artifact:
                                return {'return':1, 'error': f'ambiguity -  artifact "{artifact}" with the same UID "{uid}" and path "{path_to_artifact}" alredy exists in the index in path "{xpath}"- please fix it!'}

                        else:
                            uids[uid] = entry

                        if alias is not None and alias != '':
                            alias_lower_case = alias.lower()
                            if alias_lower_case not in aliases_lower_case:
                                aliases_lower_case[alias_lower_case] = []
                            name_uids = aliases_lower_case[alias_lower_case]
                            if uid not in name_uids:
                                name_uids.append(uid)

                            if len(name_uids)>1:
                                print ('', flush=True)
                                print (f'      Warning: Conflict for {category_alias}:{alias} - multiple UIDs: "{name_uids} ..."')

        return {'return':0, 'artifact_num': artifact_num, 'artifacts': artifacts}

################################################################################
def _get_full_path(path, repo_meta):
    """
    Get path with prefix if specified in repo metadata
    
    Args:
        path: Base repository path
        repo_meta: Repository metadata dictionary
        
    Returns:
        str: Path with prefix applied if exists, otherwise original path
    """
    full_path = path
    
    subdir = repo_meta.get('subdir')
    
    if subdir is not None:
        subdir = subdir.strip()
        if subdir != '':
            full_path = os.path.join(path, subdir)
    
    return full_path

################################################################################
def _get_artifacts_from_sharded_path(base_path, slices, artifact_alias=None):
    """
    Get list of artifact directories from sharded path structure.
    
    Args:
        base_path: Base path to search
        slices: List of slice lengths (e.g. [2] or [3,2])
        artifact_alias: Optional alias to filter (supports wildcards)
        
    Returns:
        list: List of relative paths to artifact directories
    """
    if not os.path.isdir(base_path):
        return []
    
    # Normalize artifact_alias for case-insensitive matching
    artifact_alias_lowercase = None
    use_wildcard = False
    if artifact_alias is not None:
        artifact_alias_lowercase = artifact_alias.lower()
        use_wildcard = '*' in artifact_alias or '?' in artifact_alias
    
    # Calculate total depth from slices
    total_depth = sum(slices)
    
    def _recursive_traverse(current_path, current_depth, rel_path_parts):
        """
        Recursively traverse sharded structure and collect matching artifacts.
        
        Args:
            current_path: Current directory path
            current_depth: Current depth in the shard structure
            rel_path_parts: List of path components for building relative path
            
        Returns:
            list: Matched artifact paths
        """
        matches = []
        
        try:
            entries = os.listdir(current_path)
        except (OSError, PermissionError):
            return matches
        
        # At target depth - check for matching artifact directories
        if current_depth == total_depth:
            for dirname in entries:
                dir_path = os.path.join(current_path, dirname)
                if not os.path.isdir(dir_path):
                    continue
                
                final_name = dirname.lower()
                
                # Filter by artifact_alias if provided
                if artifact_alias_lowercase is not None:
                    if use_wildcard:
                        if not fnmatch.fnmatch(final_name, artifact_alias_lowercase):
                            continue
                    else:
                        if final_name != artifact_alias_lowercase:
                            continue
                
                # Build relative path
                artifact_path = os.path.join(*(rel_path_parts + [dirname]))
                matches.append(artifact_path)
        
        # Not at target depth yet - continue traversing
        elif current_depth < total_depth:
            for dirname in entries:
                dir_path = os.path.join(current_path, dirname)
                if os.path.isdir(dir_path):
                    # Recursively traverse subdirectory
                    matches.extend(_recursive_traverse(
                        dir_path,
                        current_depth + len(dirname),
                        rel_path_parts + [dirname]
                    ))
        
        return matches
    
    # Start recursive traversal from base_path
    return _recursive_traverse(base_path, 0, [])
