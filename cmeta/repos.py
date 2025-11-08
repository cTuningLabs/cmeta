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
    def __init__(self, 
                 cfg: Dict[str, Any],
                 home_path: Path,
                 index_path: Path,
                 repos_config_path: Path,
                 logger: logging.Logger = None,
                 index_extension: str = '.pickle',
                 fail_on_error = False):
        """
        Initialize Repos manager.
        
        Args:
            cfg: Configuration dictionary
            home_path: Path to repositories directory
            repos_config_path: Path to repositories config file
            logger: Logger instance (optional)
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

    ###################################################################################################
    def init(self):
        """
        Check if runs for the first time (there is no repos.json and index)
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
            repo_local_meta = {'artifact':'local,9a3280b14a4285c9'}

            r = utils.files.safe_write_file(repo_local_meta_file, repo_local_meta, fail_on_error=self.fail_on_error, logger=self.logger)
            if r['return']>0: return r

        # Check if repo file exists
        if not os.path.isfile(self.repos_config_path):
            trigger_reindex = True

            repos_paths = []

            # First local
            repos_paths.append(home_path_local)

            # Then internal repo
            this_module_path = os.path.dirname(os.path.abspath(__file__))
            internal_repo_path = os.path.join(this_module_path, 'internal-repo')
            repos_paths.append(internal_repo_path)

            r = utils.files.safe_write_file(self.repos_config_path, repos_paths, fail_on_error=self.fail_on_error, logger=self.logger)
            if r['return']>0: return r

        if trigger_reindex or not os.path.isdir(self.index_path):
            print ('Reindexing all repos - it can take some time ...')
            print ('')

            r = self.reindex(con=False)
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

        uids = index_data.setdefault('uids', {})
        lowercase_aliases = index_data.setdefault('lowercase_aliases', {})

        # If need to delete the original one before adding the new/updated one
        if original_alias is not None:
            lowercase_artifact_alias = original_alias.lower()
            lowercase_alias_uids = lowercase_aliases.get(lowercase_artifact_alias, [])
            if original_uid in lowercase_alias_uids:
                lowercase_alias_uids.remove(original_uid)
                if len(lowercase_alias_uids) == 0:
                    del(lowercase_aliases[lowercase_artifact_alias])

        if original_uid is not None and original_uid in uids:
            del(uids[original_uid])

        # Prepare new record
        record = {'cmeta': cmeta, 'cmeta_ref_parts': cmeta_ref_parts, 'path': path}

        uids[artifact_uid] = record

        if artifact_alias is not None: 
            lowercase_artifact_alias = artifact_alias.lower()

            lowercase_alias_uids = lowercase_aliases.get(lowercase_artifact_alias, [])

            if artifact_uid not in lowercase_alias_uids:
                lowercase_alias_uids.append(artifact_uid)
                lowercase_aliases[lowercase_artifact_alias] = lowercase_alias_uids

        # Use atomic write to avoid corrupting large index files
        r = utils.files.safe_write_file(index_file, index_data, file_lock=index_file_lock, atomic=True, fail_on_error=self.fail_on_error, logger=self.logger)
        if r['return']>0: return r

#        r = utils.files.safe_write_file(os.path.splitext(index_file)[0] + ".json", index_data, atomic=True, fail_on_error=self.fail_on_error, logger=self.logger)
#        if r['return']>0: return r

        return {'return':0}



    ###################################################################################################
    def remove_from_index(self, index_file, artifact_uid, lowercase_artifact_alias):
        """
        """
        r = utils.files.safe_read_file(index_file, lock=True, keep_locked=True, fail_on_error=self.fail_on_error, logger=self.logger)
        if r['return']>0: 
            if r['return']!=16: return r

            index_data = {}
            index_file_lock = None
        else:
            index_data = r['data']
            index_file_lock = r['file_lock']

        if lowercase_artifact_alias is not None:
            lowercase_aliases = index_data.setdefault('lowercase_aliases', {})
            lowercase_alias_uids = lowercase_aliases.get(lowercase_artifact_alias, [])
            if artifact_uid in lowercase_alias_uids:
                lowercase_alias_uids.remove(artifact_uid)
                if len(lowercase_alias_uids) == 0:
                    del(lowercase_aliases[lowercase_artifact_alias])

        uids = index_data.setdefault('uids', {})

        if artifact_uid in uids:
            del(uids[artifact_uid])

        r = utils.files.safe_write_file(index_file, index_data, file_lock=index_file_lock, atomic=True, fail_on_error=self.fail_on_error, logger=self.logger)
        if r['return']>0: return r

#        r = utils.files.safe_write_file(os.path.splitext(index_file)[0] + ".json", index_data, atomic=True, fail_on_error=self.fail_on_error, logger=self.logger)
#        if r['return']>0: return r

        return {'return':0}

    ###################################################################################################
    def find_in_index(self, category_alias, category_uid, artifact_alias = None, artifact_uid = None, repos = [], only_uids=False, add_index_file=False, skip_uids=False):
        """
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
            if artifact_uid not in index.get('uids', {}):
                x = f'"{artifact_alias}" ({artifact_uid})' if artifact_alias is not None and artifact_alias != '' else f'{artifact_uid}'
                err = f'{category_alias} artifact {x} not found in the cMeta index'
                return _error(err, 16, None, self.fail_on_error)

            artifact_uids.append(artifact_uid)

        elif artifact_alias is not None and artifact_alias != "":
            lowercase_artifact_alias = artifact_alias.lower()
            if '*' in artifact_alias or '?' in artifact_alias:
                if 'ordered_uids' in index and len(index['ordered_uids'])>0:
                    check_artifact_uids = index['ordered_uids']
                else:
                    check_artifact_uids = list(index.get('uids', {}).keys())

                for artifact_uid in check_artifact_uids:
                    if artifact_uid not in index['uids']:
                        return _error(f'corrupted {category_alias} UID "{artifact_uid}" not found in the index"', 1, None, self.fail_on_error)

                    record = index['uids'][artifact_uid]

                    lowercase_alias = record['cmeta_ref_parts'].get('artifact_alias_lowercase', None)
                    if lowercase_alias is None:
                        lowercase_alias = record['cmeta_ref_parts'].get('artifact_alias', '') 
                        if not skip_uids and lowercase_alias == '':
                            lowercase_alias = artifact_uid

                    if fnmatch.fnmatch(lowercase_alias, lowercase_artifact_alias):
                        artifact_uids.append(artifact_uid)
            else:
                if lowercase_artifact_alias not in index.get('lowercase_aliases', {}):
                    # We should not be failing below even on debug to handle multiple-search - we need to handle aggregated search results
                    x_artifact_alias = "artifacts" if artifact_alias == '' or artifact_alias == None or artifact_alias == '*' else f'"{artifact_alias}"'
                    return _error(f'{category_alias} {x_artifact_alias} not found in the cMeta index', 16, None, False) #self.fail_on_error)

                artifact_uids.extend(index['lowercase_aliases'][lowercase_artifact_alias])

        else:
            if 'ordered_uids' in index and len(index['ordered_uids'])>0:
                artifact_uids = index['ordered_uids']
            else:
                artifact_uids = list(index.get('uids', {}).keys())

        result = {'return':0, 'index_file': index_file, 'index': index}

        # Check if prune by repos
        if repos or category_uid is not None:
            pruned_artifact_uids = []

            for artifact_uid in artifact_uids:
                if artifact_uid not in index['uids']:
                    return _error(f'corrupted index for {category_alias} UID "{artifact_uid}"', 1, None, self.fail_on_error)

                artifact_cmeta_ref_parts = index['uids'][artifact_uid]['cmeta_ref_parts']

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
                if artifact_uid not in index['uids']:
                    return _error(f'corrupted index for {category_alias} UID "{artifact_uid}"', 1, None, self.fail_on_error)

                artifact = index['uids'][artifact_uid].copy()

                if add_index_file:
                    artifact['index_file'] = index_file

                artifacts.append(artifact)


            result['artifacts'] = artifacts

        return result

    ###################################################################################################
    def find(self, cmeta_ref, add_index_file=False, tags=None, skip_uids=False):
        """
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

                        if all(tag.lower() in [ctag.lower() for ctag in ctags] for tag in tags):
                            add_artifacts.append(a)

                else:
                    add_artifacts = r['artifacts']

                # Adding artifacts
                artifacts.extend(add_artifacts)

        if len(artifacts) == 0:
            x_artifact_alias = "artifacts" if artifact_alias == '' or artifact_alias == None else f'"{artifact_alias}"'
            return _error(f'{category_alias} {x_artifact_alias} not found in the cMeta index', 16, None, False) #self.fail_on_error)

        return {'return':0, 'artifacts':artifacts}

    def reindex(self, repo=None, con=False):
        """
        Clean index and reindex all repos
        """

        return self.index(repo, clean=True, con=con)
    

    def index(self, repo=None, clean=False, con=False):
        """
        Index repos
        """

        import time
        time_start = time.time()

        key_uids = 'uids'
        key_ouids = 'ordered_uids'
        key_lalias = 'lowercase_aliases'

        index_path = self.index_path

        if con:
            print (f'Index path: {index_path}')


        # Recreating all repos
        index_repos = {key_uids:{}, key_ouids:[], key_lalias:{}}
        repos_meta = {}
        repo_uids_to_use = []
        repos_config_path = self.repos_config_path
        existing_paths_to_repos = []

        # Then internal repo
        this_module_path = os.path.dirname(os.path.abspath(__file__))
        this_internal_repo_path = os.path.join(this_module_path, 'internal-repo')
        existing_internal_repo_path = None

        if con:
            print (f'File with list of repos paths: {repos_config_path}')


        # Check repo list
        if repo != None:
            input('TBD ...')







        else:
            r = utils.files.safe_read_file(repos_config_path, retry_if_not_found=3, fail_on_error=self.fail_on_error, logger=self.logger)
            if r['return']>0: return r 

            paths_to_repos = r['data']

            update_repos_config_path = False

            paths_to_repos_with_updated_internal_repo = []

            for path in paths_to_repos:
                path_to_repo_desc = os.path.join(path, self.cfg['repo_meta_desc'])

                if path.endswith('internal-repo') and os.path.normpath(path) != this_internal_repo_path:
                    path = this_internal_repo_path

                    update_repos_config_path = True

                paths_to_repos_with_updated_internal_repo.append(path)

                if os.path.isfile(path_to_repo_desc):
                    r = utils.files.safe_read_file(path_to_repo_desc, retry_if_not_found=3, fail_on_error=self.fail_on_error, logger=self.logger)
                    if r['return']==0: 
                        repo_meta = r['data']

                        repos_meta[path] = repo_meta
                        existing_paths_to_repos.append(path)

            if paths_to_repos_with_updated_internal_repo:
                r = utils.files.safe_write_file(repos_config_path, paths_to_repos_with_updated_internal_repo, atomic=True, fail_on_error=self.fail_on_error, logger=self.logger)
                if r['return']>0: return r

            if len(existing_paths_to_repos) == 0:
                return {'return':1, 'error':f'could not find any repository in {repos_config_path}'}

            if con:
                print ('')
                print ('Indexing repositories ...')
                print ('')

            for path in existing_paths_to_repos:
                repo_meta = repos_meta[path]

                path_with_prefix = _get_path_with_prefix(path, repo_meta)
                      
                if con:
                    print (f'  Analyzing repository in {path_with_prefix} ...')
                    
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

                if con:
                    print (f"    CID = {lowercase_alias},{uid}")

                repo_uids_to_use.append(uid.lower())

                if lowercase_alias in index_repos[key_lalias]:
                    print (f'      Warning: repo "{alias}" is already in index!')

                    if uid is not None and uid in index_repos[key_lalias][lowercase_alias]:
                        return {'return':1, 'error': f'ambiguity - repo "{alias}" with the same UID "{uid}" alredy exists in the index - please fix it!'}

                index_repos[key_lalias][alias] = [uid]

                index_repos[key_ouids].append(uid)

                entry = {'path': path}

                cmeta_ref_parts = {'category_alias':'repo', 'category_uid':self.cfg['category_repo_uid'], 'artifact_alias':alias, 'artifact_uid':uid}

                if alias != alias.lower():
                    cmeta_ref_parts['artifact_alias_lowercase'] = alias.lower()

                entry['cmeta_ref_parts'] = cmeta_ref_parts

                entry['cmeta'] = repo_meta

                index_repos[key_uids][uid] = entry


            index_repo_file = os.path.join(index_path, 'repo' + self.index_extension)
            if con:
                print('')
                print(f'  Recording repo index file: {index_repo_file}')

            # Use atomic write to avoid corrupting large index files
            r = utils.files.safe_write_file(index_repo_file, index_repos, atomic=True, fail_on_error=self.fail_on_error, logger=self.logger)
            if r['return']>0: return r

        # Indexing categories
        index_categories = {key_uids:{}, key_ouids:[], key_lalias:{}}

        if con:
            print ('')
            print ('Indexing categories ...')
            print ('')

        categories = []

        for path in existing_paths_to_repos:
            repo_meta = repos_meta[path]

            repo_path_with_prefix = _get_path_with_prefix(path, repo_meta)
            category_path_with_prefix = os.path.join(repo_path_with_prefix, 'category')

            if os.path.isdir(category_path_with_prefix):
                if con:
                    print (f'  Analyzing categories in {category_path_with_prefix} ...')

                category_dirs = os.listdir(category_path_with_prefix)

                for category in category_dirs:
                    category_meta_desc_file_json = os.path.join(category_path_with_prefix, category, self.cfg['meta_filename_base'] + '.json')
                    category_meta_desc_file_yaml = os.path.join(category_path_with_prefix, category, self.cfg['meta_filename_base'] + '.yaml')

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
                        category_meta_desc_file_json = os.path.join(category_path_with_prefix, category, '_cm.json')
                        category_meta_desc_file_yaml = os.path.join(category_path_with_prefix, category, '_cm.yaml')

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

                            category_meta_desc_file_yaml = os.path.join(category_path_with_prefix, category, self.cfg['meta_filename_base'] + '.yaml')

                            r = utils.files.safe_write_file(category_meta_desc_file_yaml, category_meta, fail_on_error=self.fail_on_error, logger=self.logger)
                            if r['return']>0: return r

                    if category_meta:
                        categories.append({'category':category, 'meta':category_meta})

                        category_name = category_meta['artifact']
                        if con:
                            print (f'    Found category "{category}"')

                        r = utils.names.parse_cmeta_name(category_name)
                        if r['return']>0: return r
                        cmeta_name_parts = r['name']

                        uid = cmeta_name_parts.get('uid')
                        alias = cmeta_name_parts.get('alias')
                        if alias == None:
                            alias = category
                        if alias != None:
                            lowercase_alias = alias.lower()

                        if alias is not None and lowercase_alias in index_categories[key_lalias]:
                            print (f'      Warning: category "{alias}" already exists in the index!')

                            if uid is not None and uid in index_categories[key_lalias][lowercase_alias]:
                                xpath = index_categories[key_uids][uid]['path']
                                return {'return':1, 'error': f'ambiguity - category "{alias}" with the same UID "{uid}" and path "{xpath}" alredy exists in the index - please fix it!'}

                        cmeta_ref_parts = {'category_alias':'category', 'category_uid':'dd9ea50e7f76467f', 'artifact_uid':uid}

                        if alias is not None and alias != '':
                            uids = index_categories[key_lalias].get(lowercase_alias, [])
                            uids.append(uid)
                            index_categories[key_lalias][lowercase_alias] = uids

                            if len(uids)>1:
                                print (f'      Warning: AMBIGUITY for category "{alias}": more than 1 UID found !')

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

                        index_categories[key_ouids].append(uid)

                        entry = {'path': os.path.join(category_path_with_prefix, category)}

                        entry['cmeta_ref_parts'] = cmeta_ref_parts

                        entry['cmeta'] = category_meta

                        index_categories[key_uids][uid] = entry

        if index_categories[key_uids]:
            index_category_file = os.path.join(index_path, 'category' + self.index_extension)
            if con:
                print('')
                print(f'  Recording category index file: {index_category_file}')

            # Use atomic write to avoid corrupting large index files
            r = utils.files.safe_write_file(index_category_file, index_categories, atomic=True, fail_on_error=self.fail_on_error, logger=self.logger)
            if r['return']>0: return r




        # Clean index files besides repo and category
        if con:
            print(f'Cleaning existing index files in {index_path} ...')
        
        try:
            for filename in os.listdir(index_path):
                if filename.endswith(self.index_extension):
                    # Skip repo and category index files
                    if filename == f'repo{self.index_extension}' or filename == f'category{self.index_extension}':
                        continue
                    
                    file_path = os.path.join(index_path, filename)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        if con:
                            print(f'  Removed: {filename}')

        except Exception as e:
            if self.fail_on_error:
                return {'return': 1, 'error': f'Failed to clean index files: {str(e)}'}
            else:
                self.logger.warning(f'Failed to clean some index files: {str(e)}')

        # Indexing artifacts
        index_artifacts = {}

        artifact_num = 0

        if con:
            print ('')
            print ('Indexing artifacts in all repos for all categories ...')
            print ('')

        for path in existing_paths_to_repos:
            repo_meta = repos_meta[path]

            repo_name = repo_meta['artifact']

            r = utils.names.parse_cmeta_name(repo_name)
            if r['return']>0: return r
            cmeta_name_parts = r['name']

            repo_uid = cmeta_name_parts.get('uid')
            repo_alias = cmeta_name_parts.get('alias')

            repo_path_with_prefix = _get_path_with_prefix(path, repo_meta)

            if con:
                print (f'  Analyzing repo in {repo_path_with_prefix} ...')

            for category_mix in categories:

                category = category_mix['category']

                # Skip already index categories (repo and category)
                if category in ['category', 'repo']:
                    continue

                category_meta = category_mix['meta']

                category_name = category_meta['artifact']

                r = utils.names.parse_cmeta_name(category_name)
                if r['return']>0: return r
                cmeta_name_parts = r['name']

                category_uid = cmeta_name_parts.get('uid')
                category_alias = category

                full_category_name = f'{category},' + category_uid

                path_to_category = os.path.join(repo_path_with_prefix, category)

                if os.path.isdir(path_to_category):
                    print (f'    Analyzing category {category} ...')
                    
                    artifact_dirs = os.listdir(path_to_category)

                    for artifact in artifact_dirs:
                        path_to_artifact = os.path.join(path_to_category, artifact)

                        artifact_meta_desc_file_json = os.path.join(path_to_artifact, self.cfg['meta_filename_base'] + '.json')
                        artifact_meta_desc_file_yaml = os.path.join(path_to_artifact, self.cfg['meta_filename_base'] + '.yaml')

                        artifact_meta = {}

# Convertion from older CK/CM/CMX versions
#                        xartifact_meta_desc_file1 = os.path.join(path_to_artifact, self.cfg['meta_filename_base'] + '.yaml')
#                        xartifact_meta_desc_file2 = os.path.join(path_to_artifact, '_cm.json')
#                        xartifact_meta_desc_file3 = os.path.join(path_to_artifact, '_cm.yaml')
#                        if os.path.isfile(xartifact_meta_desc_file1): os.remove(xartifact_meta_desc_file1)
#                        if os.path.isfile(xartifact_meta_desc_file2): os.remove(xartifact_meta_desc_file2)
#                        if os.path.isfile(xartifact_meta_desc_file3): os.remove(xartifact_meta_desc_file3)

                        if os.path.isfile(artifact_meta_desc_file_yaml):
                            r = utils.files.safe_read_file(artifact_meta_desc_file_yaml, retry_if_not_found=3, fail_on_error=self.fail_on_error, logger=self.logger)
                            if r['return']==0: 
                                artifact_meta = r['data']
                        elif os.path.isfile(artifact_meta_desc_file_json):
                            r = utils.files.safe_read_file(artifact_meta_desc_file_json, retry_if_not_found=3, fail_on_error=self.fail_on_error, logger=self.logger)
                            if r['return']==0: 
                                artifact_meta = r['data']
                        else:
                            # Checking older format
                            artifact_meta_desc_file_json = os.path.join(path_to_artifact, '_cm.json')
                            artifact_meta_desc_file_yaml = os.path.join(path_to_artifact, '_cm.yaml')

                            if os.path.isfile(artifact_meta_desc_file_yaml):
                                r = utils.files.safe_read_file(artifact_meta_desc_file_yaml, retry_if_not_found=3, fail_on_error=self.fail_on_error, logger=self.logger)
                                if r['return']==0: 
                                    artifact_meta = r['data']
                            elif os.path.isfile(artifact_meta_desc_file_json):
                                r = utils.files.safe_read_file(artifact_meta_desc_file_json, retry_if_not_found=3, fail_on_error=self.fail_on_error, logger=self.logger)
                                if r['return']==0: 
                                    artifact_meta = r['data']

                            if artifact_meta:
                                # Update to new format
                                uid = artifact_meta['uid']
                                alias = artifact_meta.get('alias')

                                if uid is None or not utils.names.is_valid_cmeta_uid(uid):
                                    uid = utils.names.generate_cmeta_uid()

                                artifact_meta['artifact'] = uid
                                artifact_meta['category'] = full_category_name

                                for key in ['uid', 'alias', 'automation_uid', 'automation_alias']:
                                    if key in artifact_meta:
                                        del(artifact_meta[key])

                                artifact_meta_desc_file_yaml = os.path.join(path_to_category, artifact, self.cfg['meta_filename_base'] + '.json')

                                r = utils.files.safe_write_file(artifact_meta_desc_file_yaml, artifact_meta, fail_on_error=self.fail_on_error, logger=self.logger)
                                if r['return']>0: return r

                        if artifact_meta:
                            artifact_name = artifact_meta['artifact']
                            artifact_num += 1
                            if con:
                                print (f'      Found artifact {artifact_num}: "{category}::{artifact}"')

                            r = utils.names.parse_cmeta_name(artifact_name)
                            if r['return']>0: return r
                            cmeta_name_parts = r['name']

                            uid = cmeta_name_parts.get('uid')
                            if uid is None or not utils.names.is_valid_cmeta_uid(uid):
                                print (f"           Warning: {artifact} doesn't have proper {uid}")
                                input ('                Press Enter to continue ...')


                            alias = artifact
                            lowercase_alias = alias.lower()

                            if category not in index_artifacts:
                                index_artifacts[category] = {key_uids:{}, key_lalias:{}}

                            uids = index_artifacts[category][key_uids]
                            aliases_lower_case = index_artifacts[category][key_lalias]

                            if uid in uids:
                                xpath = uids[uid]['path']
                                return {'return':1, 'error': f'ambiguity -  artifact "{category_alias}" with the same "{uid}" and path "{xpath} " alredy exists in the index - please fix it!'}

                            else:
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

                                uids[uid] = entry

                            if alias is not None and alias != '':
                                alias_lower_case = alias.lower()
                                if alias_lower_case not in aliases_lower_case:
                                    aliases_lower_case[alias_lower_case] = []
                                name_uids = aliases_lower_case[alias_lower_case]
                                if uid not in name_uids:
                                    name_uids.append(uid)

                                if len(name_uids)>1:
                                    print (f'      Warning: Conflict for {category_alias}:{alias} - multiple UIDs: "{name_uids} ..."')

        if index_artifacts:
            if con:
                print ('')
                print ('Recording index files for artifacts ...')
                print ('')

            for category in sorted(index_artifacts):
                category_index = index_artifacts[category]

                index_artifact_file = os.path.join(index_path, category + self.index_extension)
                if con:
                    print(f'  Recording {category} index file: {index_artifact_file}')

                r = utils.files.safe_write_file(index_artifact_file, category_index, atomic=False, fail_on_error=self.fail_on_error, logger=self.logger)
                if r['return']>0: return r
                
        
        if con:
            time_end = time.time()
            elapsed = time_end - time_start
            print ('')
            print (f'Indexing time: {elapsed:.2f} sec.')
            print (f'Found artifacts: {artifact_num}')

        r = {'return':0}
        return r


################################################################################
def _get_path_with_prefix(path, repo_meta):
    """
    Get path with prefix if specified in repo metadata
    
    Args:
        path: Base repository path
        repo_meta: Repository metadata dictionary
        
    Returns:
        str: Path with prefix applied if exists, otherwise original path
    """
    path_with_prefix = path
    
    prefix = repo_meta.get('prefix')
    
    if prefix is not None:
        prefix = prefix.strip()
        if prefix != '':
            path_with_prefix = os.path.join(path, prefix)
    
    return path_with_prefix
