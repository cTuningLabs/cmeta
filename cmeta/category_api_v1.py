"""
CMeta base category class

cMeta author and developer: (C) 2025 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import logging
import os
import shutil
import copy
from pathlib import Path

from . import utils
from .category import InitCategory
from .utils.common import _error

class Category(InitCategory):
    """
    Standard Base Category with artifact management functions
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path = __file__, **kwargs)

    ############################################################
    def test(
            self,
            params: dict  # Parameters dictionary
    ):
        """
        Test category.

        Args:
            params (dict): Parameters dictionary.

        Returns:
            dict: A cMeta dictionary with the following keys:
                - **return** (int): 0 if success, >0 if error.
        """

        import json
        print (json.dumps(params, indent=2))

        return {'return':0}

    ############################################################
    def info_(
            self,
            state: dict,             # cMeta state
            arg1: str = None,        # Artifact alias or UID
            clip: bool = True,       # If True, copy cRef to clipboard
            url: bool = False,       # If True, copy URL with detected cRef to the clipboard
            name: bool = False,      # If True, copy artifact name to the clipboard
    ):
        """
        Get artifact info.

        Args:
            state (dict): cMeta state.
            arg1 (str | None): Artifact alias or UID.
            clip (bool): If True, copy cRef to clipboard.
            url (bool): If True, copy URL with detected cRef to the clipboard.
            name (bool): If True, copy artifact name to the clipboard

        Returns:
            dict: A cMeta dictionary with the following keys:
                - **return** (int): 0 if success, >0 if error.
                - **error** (str): Error message if `return > 0`.
                - **artifacts** (list): List of matched artifacts.
        """

        con = state['control'].get('con', False)

        state['control']['con'] = False

        result = self.find_(state, arg1)
        if result['return']>0: return result

        artifacts = result['artifacts']

        for artifact in artifacts:
            if con:
                if len(artifacts)>1:
                    print('='*80)

                print ('Artifact path: ' + artifact['path'])

            cmeta_ref_parts = artifact['cmeta_ref_parts']

            r = utils.names.restore_cmeta_ref(cmeta_ref_parts)
            if r['return']>0: return r

            cref = r['ref']

            cref_text = 'cRef='

            if con:
                print ('')
                print (f'{cref_text}{cref}')

                print ('')
                for k in sorted(cmeta_ref_parts):
                    print (k + ': ' + cmeta_ref_parts[k])

            if url:
                import urllib.parse
                clipboard_text = self.cm.cfg['env_var_cmeta_server_info_url'] + urllib.parse.quote(cref, safe="")

                if con:
                    print ('')
                    print (f'cRef URL: {clipboard_text}')
                     
            elif name:
                r = utils.names.restore_cmeta_name(cmeta_ref_parts, key='artifact', fail_on_error = self.fail_on_error)
                if r['return']>0: return r

                clipboard_text = r['name']

            elif clip:
                clipboard_text = f'{cref_text}{cref}'

            if clip:
                r = self.cm.utils.common.copy_text_to_clipboard(clipboard_text, do_not_fail = True)
                if r['return']>0: return r

        return result


    ############################################################
    def find_(
            self,
            state: dict,                 # cMeta state
            arg1: str = None,            # Artifact alias or UID
            tags: str = None,            # Comma-separated string or iterable of tags to match
            sort: bool = None,           # Sort by path
            add_index_file: bool = False,  # Add index file information
            skip_uids: bool = False      # Skip UIDs when using wildcards
    ):
        """
        Find artifacts.

        Args:
            state (dict): cMeta state.
            arg1 (str | None): Artifact alias or UID.
            tags (str | list | None): Comma-separated string or iterable of tags to match.
            sort (bool): Sort by path (True by default).
            add_index_file (bool): Add index file information.
            skip_uids (bool): Skip UIDs when using wildcards.

        Returns:
            dict: A cMeta dictionary with the following keys:
                - **return** (int): 0 if success, >0 if error.
                - **error** (str): Error message if `return > 0`.
                - **artifacts** (list): List of matched artifacts.
        """

        con = state['control'].get('con', False)

        artifact_ref_parts = {}

        if arg1 is not None:
            r = utils.names.parse_cmeta_obj(arg1, key="artifact", fail_on_error = self.fail_on_error)
            if r['return'] >0: return r
            artifact_ref_parts.update(r['obj_parts'])

        category_cmeta_ref_parts = state['category_artifact']['cmeta_ref_parts']
        category_cmeta = state['category_artifact']['cmeta']

        artifact_ref_parts['category_alias'] = category_cmeta_ref_parts['artifact_alias']
        artifact_ref_parts['category_uid'] = category_cmeta_ref_parts['artifact_uid']

        if self.cm.debug:
            self.logger.debug(f"  self.cm.repos.find({artifact_ref_parts})")

        r = self.cm.repos.find(artifact_ref_parts, add_index_file = add_index_file, tags = tags, skip_uids = skip_uids)
        if r['return']>0: return r

        artifacts = r['artifacts']

        if sort is None:
            sort = category_cmeta.get('find_sort', False)

        if sort:
            r['artifacts'].sort(key=lambda x: x['cmeta_ref_parts'].get('artifact_alias_lower', 
                                              x['cmeta_ref_parts'].get('artifact_alias', 
                                              x['cmeta_ref_parts'].get('artifact_uid', ''))).lower())

        if con:
            for a in r['artifacts']:
                print (a['path'])

        return r

    ############################################################
    def tags_(
            self,
            state: dict,                 # cMeta state
            arg1: str = None,            # Artifact alias or UID
            tags: str = None,            # Comma-separated string or iterable of tags to match
            sort: bool = False,          # Sort by name
    ):
        """
        Find unique tags in artifacts.

        Args:
            state (dict): cMeta state.
            arg1 (str | None): Artifact alias or UID.
            tags (str | list | None): Comma-separated string or iterable of tags to match.

        Returns:
            dict: A cMeta dictionary with the following keys:
                - **return** (int): 0 if success, >0 if error.
                - **error** (str): Error message if `return > 0`.
                - **artifacts** (list): List of matched artifacts.
        """

        con = state['control'].get('con', False)

        artifact_ref_parts = {}

        if arg1 is not None:
            r = utils.names.parse_cmeta_obj(arg1, key="artifact", fail_on_error = self.fail_on_error)
            if r['return'] >0: return r
            artifact_ref_parts.update(r['obj_parts'])

        category_cmeta_ref_parts = state['category_artifact']['cmeta_ref_parts']
        category_cmeta = state['category_artifact']['cmeta']

        artifact_ref_parts['category_alias'] = category_cmeta_ref_parts['artifact_alias']
        artifact_ref_parts['category_uid'] = category_cmeta_ref_parts['artifact_uid']

        if self.cm.debug:
            self.logger.debug(f"  self.cm.repos.tags({artifact_ref_parts})")

        r = self.cm.repos.find(artifact_ref_parts, tags = tags)
        if r['return']>0: return r

        artifacts = r['artifacts']

        unique_tags = {}

        for artifact in artifacts:
            xtags = artifact['cmeta'].get('tags',[])

            for xtag in xtags:
                xtag = xtag.strip()
                if xtag not in unique_tags:
                    unique_tags[xtag] = 0
                unique_tags[xtag] += 1

        if con:
            if sort:
                for utag in sorted(unique_tags):
                    freq = unique_tags[utag]
                    x = f'{utag} ({freq})'
                    print (x)

            else:
                for k, v in sorted(unique_tags.items(), key=lambda item: item[1], reverse=True):
                    print(f"{k} ({v})")

        return {'return':0, 'tags': unique_tags}

    ############################################################
    def update_(
            self,
            state: dict,                 # cMeta state
            arg1: str = None,            # cMeta artifact(s) with wildcards
            tags: str = None,            # Prune artifacts by tags
            sort: bool = True,           # Sort artifacts by alias and UID when updating in batch
            skip_uids: bool = False,     # Skip UIDs when using wildcards
            meta: dict = {},             # Meta dictionary to merge recursively with existing artifact
            new_tags: str = None,        # Add more tags
            replace_lists: bool = False,  # Replace lists during merging
            replace: bool = False,       # Replace existing meta dictionary entirely
            ignore_errors: bool = False,  # Ignore errors when updating multiple artifacts
            create: bool = False,        # If artifact doesn't exist attempt to create
            create_params: dict = {},     # Pass params to create function
            update_category: bool = False,
    ):
        """
        Update artifact(s).

            state (dict): cMeta state.
            arg1 (str | None): cMeta artifact(s) with wildcards.
            tags (str | list | None): Prune artifacts by tags.
            sort (bool): Sort artifacts by alias and UID when updating in batch.
            skip_uids (bool): Skip UIDs when using wildcards.
            meta (dict): Meta dictionary to merge recursively with existing artifact.
            new_tags (str | list | None): Add more tags.
            replace_lists (bool): Replace lists during merging.
            replace (bool): Replace existing meta dictionary entirely.
            ignore_errors (bool): Ignore errors when updating multiple artifacts.
            create (bool): If artifact doesn't exist attempt to create.
            create_params (dict): Pass params to create function.
            update_category (bool): Allow category update in meta

        Returns:
            dict: A cMeta dictionary with the following keys:
                - **return** (int): 0 if success, >0 if error.
                - **error** (str): Error message if `return > 0`.
                - **artifacts** (list): All matched artifacts.
                - **updated_artifacts** (list): Updated artifacts.
        """

        # First, find artifact(s)
        con = state.get('control',{}).get('con', False)

        state['control']['con'] = False

        r = self.find_(state, arg1, tags, sort, add_index_file=True, skip_uids=skip_uids)
        if r['return']>0:
            if r['return']!=16 or not create: 
                return r

            r = self.create_(state, arg1, **create_params)
            if r['return']>0: return r

            r = self.find_(state, arg1, tags, sort, add_index_file=True, skip_uids=skip_uids)
            if r['return']>0: return r

        artifacts = r['artifacts']
        updated_artifacts = []

        category_cmeta = state['category_artifact']['cmeta']
        no_index = category_cmeta.get('no_index', False)

        ignore_root_keys = ['artifact']
        if not update_category:
            ignore_root_keys.append('category')

        for artifact in artifacts:
            updated = False

            artifact_path = artifact['path']

            # Read real meta file
            found_cmeta_filename = None
            for ext in ['json', 'yaml']:
                cmeta_filename = os.path.join(artifact_path, self.cm.cfg['meta_filename_base'] + '.' + ext)

                if os.path.isfile(cmeta_filename):
                    found_cmeta_filename = cmeta_filename
                    break

            if found_cmeta_filename is None:
                if not ignore_errors:
                    return {'return':1, 'error':f'artifact meta file not found in "{artifact_path}"'}

            if found_cmeta_filename is not None:
               # Safe updating of meta data
               r = utils.files.safe_read_file(found_cmeta_filename, lock=True, keep_locked=True, fail_on_error=self.fail_on_error, logger=self.logger)
               if r['return']>0: 
                   if r['return']!=16: return r

                   cmeta = {}
                   cmeta_file_lock = None
               else:
                   cmeta = r['data']
                   cmeta_file_lock = r['file_lock']

               # Replace or merge
               if replace:
                   orig_artifact = cmeta.get('artifact')
                   orig_category = cmeta.get('category')

                   cmeta = meta

                   if 'artifact' not in cmeta: cmeta['artifact'] = orig_artifact
                   if 'category' not in cmeta: cmeta['category'] = orig_category

               else:                                     
                   cmeta = utils.common.deep_merge(cmeta, meta, append_lists=not replace_lists, ignore_root_keys=ignore_root_keys)


               if new_tags is not None:
                   meta_tags = cmeta.get('tags', [])

                   r = utils.common.normalize_tags(new_tags)
                   if r['return']>0: return r
                     
                   for t in r['tags']:
                       if t not in meta_tags:
                           meta_tags.append(t)

                   cmeta['tags'] = meta_tags

               r = utils.files.safe_write_file(found_cmeta_filename, cmeta, file_lock=cmeta_file_lock, fail_on_error=self.fail_on_error, logger=self.logger)
               if r['return']>0: return r

               updated = True

               # Update index
               if not no_index:
                   artifact_index_file = artifact['index_file']

                   artifact_cmeta_ref_parts = artifact['cmeta_ref_parts']

                   r = self.cm.repos.add_to_index(cmeta, artifact_cmeta_ref_parts, artifact_path)
                   if r['return']>0: return r

            # Provide info
            if updated:
                updated_artifacts.append(artifact)

            if con:
                if updated:
                    x = 'Artifact was updated'
                else:
                    x = 'Skipped updating artifact'

                print (x + ' in ' + artifact_path)

        return {'return':0, 'artifacts': artifacts, 'updated_artifacts': updated_artifacts}

    ############################################################
    def list_(
            self,
            state: dict,             # cMeta state
            arg1: str = None,        # Artifact alias or UID
            tags: str = None,        # Optional tag filter
            sort: bool = None,       # Sort by alias or UID
            skip_uids: bool = False  # Skip UIDs when using wildcards
    ):
        """
        List artifact names.

        Args:
            state (dict): cMeta state.
            arg1 (str | None): Artifact alias or UID.
            tags (str | list | None): Optional tag filter.
            sort (bool): Sort by alias or UID.
            skip_uids (bool): Skip UIDs when using wildcards.

        Returns:
            dict: A cMeta dictionary with the following keys:
                - **return** (int): 0 if success, >0 if error.
                - **error** (str): Error message if `return > 0`.
                - **artifacts** (list): List of matched artifacts.
        """
        con = state['control'].get('con', False)

        state['control']['con'] = False

        r = self.find_(state, arg1, tags=tags, sort=sort, skip_uids = skip_uids)
        if r['return']>0: return r

        if sort:
            r['artifacts'].sort(key=utils.names.get_sort_key_cmeta_obj_alias_or_uid)

        if con:
            for a in r['artifacts']:
                cmeta_ref_parts = a['cmeta_ref_parts']
                artifact_alias_or_uid = cmeta_ref_parts.get('artifact_alias', cmeta_ref_parts.get('artifact_uid'))

                print (artifact_alias_or_uid)

        return r

    ############################################################
    def read_(
            self,
            state: dict,             # cMeta state
            arg1: str = None,        # Artifact alias or UID
            tags: str = None,        # Optional tag filter
            extra: bool = False,     # Show extra info
            skip_uids: bool = False, # Skip UIDs when using wildcards
            yaml: bool = False,      # Output as YAML instead of JSON
            load_files = [],         # Attempt to load files
    ):
        """
        Read artifact meta.

        Args:
            state (dict): cMeta state.
            arg1 (str | None): Artifact alias or UID.
            tags (str | list | None): Optional tag filter.
            extra (bool): Show extra info.
            skip_uids (bool): Skip UIDs when using wildcards.
            yaml (bool): Output as YAML instead of JSON.

        Returns:
            dict: A cMeta dictionary with the following keys:
                - **return** (int): 0 if success, >0 if error.
                - **error** (str): Error message if `return > 0`.
                - **artifact** (dict): Matched artifact.
                - **cmeta** (dict): Artifact metadata.
        """
        con = state['control'].get('con', False)

        if arg1 is None:
            return {'return':1, 'error':'artifact (arg1) is not specified'}

        state['control']['con'] = False

        r = self.find_(state, arg1, tags=tags, skip_uids=skip_uids)
        if r['return']>0: return r

        artifacts = r['artifacts']

        if len(artifacts)>1:
            return {'return':1, 'error':f'more than 1 artifact found for "{arg1}"'}

        artifact = artifacts[0]

        сmeta = artifact['cmeta']

        result = {'return':0, 'artifact': artifact, 'cmeta': сmeta}

        if len(load_files) > 0:
            loaded_files = {}
            path = artifact['path']
            for filename in load_files:
                file_path = os.path.join(path, filename)
                loaded_files[filename] = {'path': file_path}
                if os.path.isfile(file_path):
                    r = self.cm.utils.files.safe_read_file(file_path, fail_on_error=self.fail_on_error)
                    if r['return']>0: return r
                    loaded_files[filename]['data'] = r['data']

            result['loaded_files'] = loaded_files

        if con:
            data = artifact if extra else сmeta

            if yaml:
                import yaml
                print (yaml.dump(data, indent=2, sort_keys=True))
            else:
                import json
                print (json.dumps(data, indent=2, sort_keys=True))
        
        return result

    ############################################################
    def delete_(
            self,
            state: dict,                 # cMeta state
            arg1: str = None,            # Artifact alias or UID
            tags: str = None,            # Optional tag filter
            sort: bool = True,           # Sort artifacts by alias and UID
            force: bool = False,         # Force deletion without confirmation
            f: bool = False,             # Shorthand for force
            skip_uids: bool = False,     # Skip UIDs when using wildcards
            ignore_errors: bool = False,  # Ignore errors when deleting multiple artifacts
            print_time: bool = False     # Print time per deletion
    ):
        """
        Delete and unindex artifact(s).

        Args:
            state (dict): cMeta state.
            arg1 (str | None): Artifact alias or UID.
            tags (str | list | None): Optional tag filter.
            sort (bool): Sort artifacts by alias and UID.
            force (bool): Force deletion without confirmation.
            f (bool): Shorthand for force.
            skip_uids (bool): Skip UIDs when using wildcards.
            ignore_errors (bool): Ignore errors when deleting multiple artifacts.
            print_time (bool): Print time per deletion.

        Returns:
            dict: A cMeta dictionary with the following keys:
                - **return** (int): 0 if success, >0 if error.
                - **error** (str): Error message if `return > 0`.
                - **artifacts** (list): All matched artifacts.
                - **deleted_artifacts** (list): Deleted artifacts.
        """

        # First, find artifact(s)
        con = state.get('control',{}).get('con', False)

        state['control']['con'] = False

        r = self.find_(state, arg1, tags, sort, add_index_file=True, skip_uids=skip_uids)
        if r['return']>0: return r

        artifacts = r['artifacts']

        deleted_artifacts = []

        force = force or f
    
        category_cmeta = state['category_artifact']['cmeta']
        sharding_slices = category_cmeta.get('sharding_slices')
        no_index = category_cmeta.get('no_index', False)

        for artifact in artifacts:
            artifact_path = artifact['path']
            artifact_cmeta = artifact['cmeta']

            if artifact_cmeta.get('permanent', False):
                if con:
                    print (f'Skipping permanent artifact located at "{artifact_path}" ...')

                continue

            if print_time:
                import time
                start_time = time.perf_counter()                

            if con:
                print (f'Deleting artifact located at "{artifact_path}" ...')
                if not force:
                    x = input('  Proceed (y/N)? ')
                    x = x.strip().lower()

                    if x not in ['y', 'yes']:
                        print ('    Skipped!')
                        continue

            artifact_cmeta_ref_parts = artifact['cmeta_ref_parts']
            artifact_uid = artifact_cmeta_ref_parts['artifact_uid']
            artifact_alias_lowercase = artifact_cmeta_ref_parts.get('artifact_alias_lowercase', artifact_cmeta_ref_parts.get('artifact_alias'))

            # Remove from index first
            error = False
            if not no_index:
                artifact_index_file = artifact['index_file']

                r = self.cm.repos.remove_from_index(artifact_index_file, artifact_uid, artifact_alias_lowercase)
                if r['return']>0:
                    error = True

            # Delete directory if exists (if was not deleted already by another process)
            if not error:
                r = self.cm.utils.files.safe_delete_directory(artifact_path)
                if r['return']>0:
                    error = True

            # Delete root if empty
            if not error:
                r = utils.files.safe_delete_directory_if_empty_with_sharding(artifact_path, sharding_slices)
                if r['return'] > 0:
                    error = True

            if error:
                if not ignore_errors:
                    return r

                if con:
                    print(f'    Skipped deletion or partially deleted due to error: {r["error"]}')

            if not error:
                deleted_artifacts.append(artifact)

            if print_time:
                print ('        Elapsed time: %.3f sec.' % (time.perf_counter() - start_time))


        return {'return':0, 'artifacts': artifacts, 'deleted_artifacts': deleted_artifacts}

    ############################################################
    def create_(
            self,
            state: dict,             # cMeta state
            arg1: str = None,        # Artifact alias or UID
            tags: str = None,        # Tags to add to the artifact
            meta: dict = {},         # Initial metadata dictionary
            yaml: bool = False,      # Save metadata as YAML instead of JSON
            virtual: bool = False,   # Virtual artifact created only in index (such as repo)
            path: str = None         # Use this path for artifact (useful for virtual artifacts)
    ):
        """
        Create and index an artifact.

        Args:
            state (dict): cMeta state.
            arg1 (str | None): Artifact alias or UID.
            tags (str | list | None): Tags to add to the artifact.
            meta (dict): Initial metadata dictionary.
            yaml (bool): Save metadata as YAML instead of JSON.
            virtual (bool): Virtual artifact created only in index (such as repo).
            path (str | None): Use this path for artifact (useful for virtual artifacts such as repo).

        Returns:
            dict: A cMeta dictionary with the following keys:
                - **return** (int): 0 if success, >0 if error.
                - **error** (str): Error message if `return > 0`.
                - **path** (str): Path to the created artifact.
                - **meta** (dict): Artifact metadata.
        """

        con = state.get('control',{}).get('con', False)

        state['control']['con'] = False

        if tags is not None:
            if type(tags) != str and type(tags) != list:
                return {'return':1, 'error': f'"tags" should be str or list but got {type(tags).__name__}'}

        # Use UID if arg1 is None
        if arg1 is None:
            artifact_obj_parts = {}

        else:
            # Parse artifact
            r = utils.names.parse_cmeta_obj(arg1, key = "artifact", fail_on_error = self.fail_on_error)
            if r['return'] >0: return r

            artifact_obj_parts = r['obj_parts']

        # Check artifact path
        artifact_alias = artifact_obj_parts.get('artifact_alias')
        artifact_uid = artifact_obj_parts.get('artifact_uid')

        if artifact_alias is not None or artifact_uid is not None:
            # Check that artifact doesn't have wildcards
            if artifact_alias is not None and ('*' in artifact_alias or '?' in artifact_alias):
                return {'return':1, 'error':f"artifact can't have wildcards during creation ({arg1})"}

            # Check if artifact already exists (relatively fast - should be in index)
            r = self.find_(state, arg1, tags)
            if r['return'] == 0:
               artifacts = r['artifacts']
               if len(artifacts)>0:
                   if len(artifacts) == 1:
                       return {'return':8, 'error':f'artifact already exists in "{artifacts[0]["path"]}"'}
                   else:
                       paths = ', '.join([a['path'] for a in artifacts])
                       return {'return':8, 'error':f'artifacts already exist in "{paths}"'}
               
            elif r['return'] != 16:
               return r

        # Find path to target repository or local if not specified
        artifact_repo_alias = artifact_obj_parts.get('artifact_repo_alias')
        artifact_repo_uid = artifact_obj_parts.get('artifact_repo_uid')

        repo_cmeta_ref = {'category_alias': 'repo', 'category_uid': self.cm.cfg['category_repo_uid']}
        
        if artifact_repo_uid == None and artifact_repo_alias == None:
            repo_cmeta_ref['artifact_alias'] = 'local'
        else:
            if artifact_repo_uid != None: repo_cmeta_ref['artifact_uid'] = artifact_repo_uid
            if artifact_repo_alias != None: repo_cmeta_ref['artifact_alias'] = artifact_repo_alias

        r = self.cm.repos.find(repo_cmeta_ref)
        if r['return']>0: return r

        repo_artifacts = r['artifacts']

        if len(repo_artifacts)>1:
            paths = ', '.join([a['path'] for a in repo_artifacts])
            return {'return':1, 'error': f'more than one target repo found during artifact creation in "{paths}"'} 

        repo_artifact = repo_artifacts[0]
        repo_path = repo_artifact['full_path']

        repo_cmeta = repo_artifact['cmeta']

        repo_cmeta_ref_parts = repo_artifact['cmeta_ref_parts']

        artifact_repo_alias = repo_cmeta_ref_parts.get('artifact_alias')
        artifact_repo_uid = repo_cmeta_ref_parts['artifact_uid']

        if not virtual:
            os.makedirs(repo_path, exist_ok=True)

        # Check category path
        category = state['category']
        category_alias = category['artifact_alias']
        category_uid = category['artifact_uid']

        category_cmeta = state['category_artifact']['cmeta']
        no_index = category_cmeta.get('no_index', False)

        category_path = os.path.join(repo_path, category_alias)

        if not virtual:
            os.makedirs(category_path, exist_ok=True)

        # Check artifact path
        if artifact_uid == None:
            artifact_uid = utils.names.generate_cmeta_uid()

        artifact_dir = artifact_alias if artifact_alias != None and artifact_alias != '' else artifact_uid

        if category_uid in repo_cmeta.get('sharding_slices', {}):
            sharding_slices = repo_cmeta['sharding_slices'][category_uid]
        else:
            sharding_slices = category_cmeta.get('sharding_slices')

        if sharding_slices is not None:
            r = utils.files.apply_sharding_to_path(category_path, artifact_dir, sharding_slices)
            if r['return']>0: return r

            artifact_path = r['sharded_path']
        else:
            artifact_path = os.path.join(category_path, artifact_dir)

        cmeta_filename_json = os.path.join(artifact_path, self.cm.cfg['meta_filename_base'] + '.json')
        cmeta_filename_yaml = os.path.join(artifact_path, self.cm.cfg['meta_filename_base'] + '.yaml')

        if not virtual:
            if os.path.isdir(artifact_path):
                if os.path.isfile(cmeta_filename_json) or os.path.isfile(cmeta_filename_yaml):
                    return {'return':8, 'error':f'artifact already exists in "{artifact_path}"'}

            os.makedirs(artifact_path, exist_ok=True)

        # Prepare meta
        cmeta = copy.deepcopy(meta)

        if 'artifact' not in cmeta:
            cmeta['artifact'] = artifact_uid

        if 'category' not in cmeta:
            r = utils.names.restore_cmeta_name(category, key='artifact', fail_on_error = self.fail_on_error)
            if r['return'] >0: return r

            cmeta['category'] = r['name']

        if tags is not None:
            meta_tags = cmeta.get('tags', [])

            r = utils.common.normalize_tags(tags)
            if r['return']>0: return r
              
            for t in r['tags']:
                if t not in meta_tags:
                    meta_tags.append(t)

            cmeta['tags'] = meta_tags

        if 'creation_timestamp' not in cmeta:
            from datetime import datetime, timezone
            cmeta['creation_timestamp'] = datetime.now(timezone.utc).isoformat()

        if 'authors' not in cmeta and os.environ.get(self.cm.cfg['env_var_cmeta_authors'], '') != '':
            cmeta['authors'] = os.environ[self.cm.cfg['env_var_cmeta_authors']]

        if 'copyright' not in cmeta and os.environ.get(self.cm.cfg['env_var_cmeta_copyright'], '') != '':
            cmeta['copyright'] = os.environ[self.cm.cfg['env_var_cmeta_copyright']]

        # Save meta
        if not virtual:
            tmp_cmeta_filename = cmeta_filename_yaml if yaml else cmeta_filename_json

            r = utils.files.safe_write_file(tmp_cmeta_filename, data=cmeta, fail_on_error = self.fail_on_error)
            if r['return']>0: return r

        if path is not None:
            artifact_path = path 

        # Update index
        if not no_index:
            cmeta_ref_parts = {}

            if artifact_alias is not None: 
                cmeta_ref_parts['artifact_alias'] = artifact_alias
                artifact_alias_lowercase = artifact_alias.lower()
                if artifact_alias_lowercase != artifact_alias:
                    cmeta_ref_parts['artifact_alias_lowercase'] = artifact_alias_lowercase

            cmeta_ref_parts['artifact_uid'] = artifact_uid

            cmeta_ref_parts['category_alias'] = category_alias
            cmeta_ref_parts['category_uid'] = category_uid

            cmeta_ref_parts['repo_alias'] = artifact_repo_alias
            cmeta_ref_parts['repo_uid'] = artifact_repo_uid


            r = self.cm.repos.add_to_index(cmeta, cmeta_ref_parts, artifact_path)
            if r['return']>0: return r

        # Print artifact path
        if con:
            x = 'Virtual a' if virtual else 'A'
            print (f'{x}rtifact was created in "{artifact_path}"')

        return {'return':0, 'path':artifact_path, 'meta':cmeta}

    ############################################################
    def move_(
            self,
            state: dict,                 # cMeta state
            arg1: str,                   # cMeta artifact(s) with wildcards to be renamed or moved
            arg2: str,                   # New cMeta artifact name and/or new repository
            tags: str = None,            # Prune source artifacts by tags
            sort: bool = True,           # Sort artifacts by alias and UID when updating in batch
            skip_uids: bool = False,     # Skip UIDs when using wildcards
            ignore_errors: bool = False,  # Ignore errors when updating multiple artifacts
            copy: bool = False           # If True, copy artifact instead of moving
    ):
        """
        Rename and/or move artifact(s).

        Args:
            state (dict): cMeta state.
            arg1 (str): cMeta artifact(s) with wildcards to be renamed or moved.
            arg2 (str): New cMeta artifact name and/or new repository.
            tags (str | list | None): Prune source artifacts by tags.
            sort (bool): Sort artifacts by alias and UID when updating in batch.
            skip_uids (bool): Skip UIDs when using wildcards.
            ignore_errors (bool): Ignore errors when updating multiple artifacts.
            copy (bool): If True, copy artifact instead of moving.

        Returns:
            dict: A cMeta dictionary with the following keys:
                - **return** (int): 0 if success, >0 if error.
                - **error** (str): Error message if `return > 0`.
                - **artifacts** (list): All matched artifacts.
                - **updated_artifacts** (list): Updated artifacts.
        """

        import shutil

        # First, find artifact(s)
        con = state.get('control',{}).get('con', False)

        state['control']['con'] = False

        r = self.find_(state, arg1, tags, sort, add_index_file=True, skip_uids=skip_uids)
        if r['return']>0: return r

        artifacts = r['artifacts']

        num_found_artifacts = len(artifacts)

        # Process second argument to decide if it's one artifact to be renames 
        # or multiple artifacts to be moved somewhere ...

        r = utils.names.parse_cmeta_obj(arg2)
        if r['return'] >0: return r

        target_obj_parts = r['obj_parts']

        target_repo_alias = target_obj_parts.get('repo_alias')
        target_repo_uid = target_obj_parts.get('repo_uid')
        target_alias = target_obj_parts.get('alias')
        target_uid = target_obj_parts.get('uid')

        if target_alias is not None and ('*' in target_alias or '?' in target_alias):
            return {'return':1, 'error':'new artifact alias should not have wildcards'}

        if num_found_artifacts > 1 and (target_alias is not None or target_uid is not None):
            return {'return':1, 'error':'only new repository can be specified for multiple source artifacts'}

        if copy and num_found_artifacts > 1 and target_uid is not None:
            return {'return':1, 'error':'can\'t specify the same UID when copying multiple artifacts'}

        if copy:
            command = 'copy'
            command2 = 'copying'
        else:    
            if num_found_artifacts > 1 or target_alias is not None or target_uid is not None:
                command = 'move'
                command2 = 'moving' 
            else:
                command = 'rename'
                command2 = 'renaming'


        # Check if new target repo
        target_repo_path = None
        target_repo_cmeta = None
        if target_repo_alias is not None or target_repo_uid is not None:
            repo_cmeta_ref = {'category_alias': 'repo', 'category_uid': self.cm.cfg['category_repo_uid']}
            
            if target_repo_uid is not None: repo_cmeta_ref['artifact_uid'] = target_repo_uid
            if target_repo_alias is not None: repo_cmeta_ref['artifact_alias'] = target_repo_alias

            r = self.cm.repos.find(repo_cmeta_ref)
            if r['return']>0: return r

            repo_artifacts = r['artifacts']

            if len(repo_artifacts)>1:
                paths = '\n'.join(['* '+a['path'] for a in repo_artifacts])
                return {'return':1, 'error': f'more than one target repo found when {command2} artifacts:\n{paths}'} 

            target_repo_artifact = repo_artifacts[0]
            target_repo_path = target_repo_artifact['full_path']
            target_repo_cmeta = target_repo_artifact['cmeta']

            repo_cmeta_ref_parts = target_repo_artifact['cmeta_ref_parts']

            target_repo_alias = repo_cmeta_ref_parts.get('artifact_alias')
            target_repo_uid = repo_cmeta_ref_parts['artifact_uid']

        # Iterate over artifacts
        tmp_target_uid = None

        category_cmeta = state['category_artifact']['cmeta']
        sharding_slices = category_cmeta.get('sharding_slices')
        target_sharding_slices = category_cmeta.get('sharding_slices')
        no_index = category_cmeta.get('no_index', False)

        for artifact in artifacts:
            # Get path to the original original artifact
            path = os.path.normpath(artifact['path'])

            if not os.path.isdir(path):
                return {'return':1, 'error':f'artifact not found in path {path}'}

            cmeta = artifact['cmeta']

            # Copy next dict to update it further
            cmeta_ref_parts = artifact['cmeta_ref_parts'].copy()

            category_alias = cmeta_ref_parts['category_alias']
            category_uid = cmeta_ref_parts['category_uid']

            artifact_alias = cmeta_ref_parts.get('artifact_alias')
            artifact_uid = cmeta_ref_parts['artifact_uid']

            # Get meta of the current repository if no target to get sharding_slices per repo if needed
            if target_repo_cmeta is None:
                tmp_repo_cmeta_ref = {'category_alias': 'repo', 'category_uid': self.cm.cfg['category_repo_uid']}
                
                if cmeta_ref_parts.get('repo_uid') is not None: tmp_repo_cmeta_ref['artifact_uid'] = cmeta_ref_parts['repo_uid']
                if cmeta_ref_parts.get('repo_alias') is not None: tmp_repo_cmeta_ref['artifact_alias'] = cmeta_ref_parts['repo_alias']

                r = self.cm.repos.find(tmp_repo_cmeta_ref)
                if r['return']>0: return r

                tmp_repo_artifacts = r['artifacts']

                if len(tmp_repo_artifacts)>1:
                    paths = '\n'.join(['* '+a['path'] for a in tmp_repo_artifacts])
                    return {'return':1, 'error': f'more than one target repo found when {command2} artifacts:\n{paths}'} 

                tmp_target_repo_artifact = tmp_repo_artifacts[0]
                target_repo_cmeta = tmp_target_repo_artifact['cmeta']

            if category_uid in target_repo_cmeta.get('sharding_slices', {}):
                target_sharding_slices = target_repo_cmeta['sharding_slices'][category_uid]

            if copy:
                if tmp_target_uid is None and target_uid is not None:
                    tmp_target_uid = target_uid
                else:
                    tmp_target_uid = utils.names.generate_cmeta_uid()

                target_uid = tmp_target_uid

            update_uid = target_uid is not None and target_uid != artifact_uid

            if num_found_artifacts == 1:
                if target_repo_path is None and artifact_alias is not None and artifact_alias == target_alias:
                    if not update_uid:
                        return {'return':1, 'error':f"can't {command} artifact {artifact_alias} to itself"}

            # Find path to a category of the original artifact
            normal_path = os.path.normpath(path)

            path_parts = normal_path.split(os.sep)

            if category_alias not in path_parts:
                return {'return':1, 'error':f'category_alias "{category_alias}" not found in path "{path}"'}

            idx = path_parts.index(category_alias)
            path_to_category = os.sep.join(path_parts[:idx+1])

            # Prepare target path
            path_to_target_category = path_to_category if target_repo_path is None else os.path.join(target_repo_path, category_alias)

            if target_alias is not None:
                target_artifact_dir = target_alias
            else:
                if artifact_alias is not None:
                    target_artifact_dir = artifact_alias
                elif target_uid is not None:
                    target_artifact_dir = target_uid
                else:
                    target_artifact_dir = artifact_uid

            if target_sharding_slices is not None:
                r = utils.files.apply_sharding_to_path(path_to_target_category, target_artifact_dir, target_sharding_slices)
                if r['return']>0: return r

                path_to_target_artifact = r['sharded_path']
            else:
                path_to_target_artifact = os.path.join(path_to_target_category, target_artifact_dir)

            if path == path_to_target_artifact and not update_uid:
                return {'return':1, 'error':f"can't {command} artifact {artifact_alias} to itself"}

            if os.path.isdir(path_to_target_artifact) and (copy or not update_uid):
                return {'return':1, 'error':f"artifact already exists in path {path_to_target_artifact}"}

            if update_uid:
                cmeta_ref_parts['artifact_uid'] = target_uid
            if target_alias is not None:
                cmeta_ref_parts['artifact_alias'] = target_alias
            if target_repo_path is not None:
                for key in ['repo_alias', 'repo_uid']:
                    if key in cmeta_ref_parts:
                        del(cmeta_ref_parts[key])

                if target_repo_alias is not None:
                    cmeta_ref_parts['repo_alias'] = target_repo_alias
                if target_repo_uid is not None:
                    cmeta_ref_parts['repo_uid'] = target_repo_uid

            # Move/copy artifact
            if con:
                print (command2.capitalize() + f" {path} -> {path_to_target_artifact} ...")

            if not os.path.isdir(path_to_target_artifact):
                if target_sharding_slices is not None:
                    # Check if target sub-directories exists:
                    sub_path_to_target_artifact = os.path.dirname(path_to_target_artifact)
                    os.makedirs(sub_path_to_target_artifact, exist_ok=True)

                try:
                    if copy:
                        shutil.copytree(path, path_to_target_artifact, copy_function=shutil.copy2, ignore_dangling_symlinks=False)
                    else:
                        shutil.move(path, path_to_target_artifact)
                except Exception as e:
                    return {'return':1, 'error': f'error {command2} artifact {path} to {path_to_target_artifact} - {e}'}

            # Update meta if update_uid
            if update_uid:
                # Read real meta file
                found_cmeta_filename = None
                for ext in ['json', 'yaml']:
                    cmeta_filename = os.path.join(path_to_target_artifact, self.cm.cfg['meta_filename_base'] + '.' + ext)

                    if os.path.isfile(cmeta_filename):
                        found_cmeta_filename = cmeta_filename
                        break

                if found_cmeta_filename is None:
                    if not ignore_errors:
                        return {'return':1, 'error':f'artifact meta file not found in "{path_to_target_artifact}"'}

                if found_cmeta_filename is not None:
                   # Safe updating of meta data
                   r = utils.files.safe_read_file(found_cmeta_filename, lock=True, keep_locked=True, fail_on_error=self.fail_on_error, logger=self.logger)
                   if r['return']>0: return r

                   cmeta = r['data']
                   cmeta_file_lock = r['file_lock']

                   cmeta['artifact'] = target_uid

                   r = utils.files.safe_write_file(found_cmeta_filename, cmeta, file_lock=cmeta_file_lock, fail_on_error=self.fail_on_error, logger=self.logger)
                   if r['return']>0: return r

            # Delete root if empty
            if not copy:
                r = utils.files.safe_delete_directory_if_empty_with_sharding(path, sharding_slices)
                # Ignore errors when deleting empty directories during move

            # Update index
            if not no_index:
                artifact_index_file = artifact['index_file']

                kwargs = {}
                if not copy:
                    kwargs.update(original_alias=artifact_alias, original_uid=artifact_uid)

                r = self.cm.repos.add_to_index(cmeta, cmeta_ref_parts, path_to_target_artifact, **kwargs)
                if r['return']>0: return r

        return {'return':0, 'artifacts': artifacts}

    ############################################################
    def copy__(
            self,
            params: dict  # cMeta params
    ):
        """
        Copy artifact(s).

        @base.move_(**params, copy=True)

        Args:
            params (dict): cMeta params.

        Returns:
            dict: A cMeta dictionary (see move_ for details).
        """

        p = self._prepare_input_from_params(params)

        p['command'] = 'move'
        p['copy'] = True

        return self.cm.access(p)

    ############################################################
    def get_(
            self,
            state: dict,             # cMeta state
            arg1: str = None,        # Artifact alias or UID
            tags: str = None,        # Tags to add to the artifact (for creation)
            skip_uids: bool = False,  # Skip UIDs when using wildcards
            yaml: bool = False,      # Save/output metadata as YAML instead of JSON
            meta: dict = {},         # Initial metadata dictionary (for creation)
            virtual: bool = False,   # Virtual artifact created only in index (for creation)
            path: str = None,        # Use this path for artifact (for creation)
            show_path: bool = False,
            load_files = [],
    ):
        """
        Get artifact meta. Read if exists, create and read if doesn't exist.

        Args:
            state (dict): cMeta state.
            arg1 (str | None): Artifact alias or UID.
            tags (str | list | None): Tags to add to the artifact (used during creation).
            skip_uids (bool): Skip UIDs when using wildcards.
            yaml (bool): Save/output metadata as YAML instead of JSON.
            meta (dict): Initial metadata dictionary (used during creation).
            virtual (bool): Virtual artifact created only in index (used during creation).
            path (str | None): Use this path for artifact (used during creation).
            show_path (bool): Print path instead of meta 

        Returns:
            dict: A cMeta dictionary with the following keys:
                - **return** (int): 0 if success, >0 if error.
                - **error** (str): Error message if `return > 0`.
                - **artifact** (dict): Matched artifact.
                - **cmeta** (dict): Artifact metadata.
                - **created** (bool): True if artifact was created, False if it already existed.
        """
        
        # Try to read the artifact first
        con = state.get('control',{}).get('con', False)

        if con and show_path:
            import copy
            state = copy.deepcopy(state)
            state['control']['con'] = False

        r = self.read_(state, arg1, tags=tags, skip_uids=skip_uids, load_files=load_files)
        
        # If artifact exists, return it
        if r['return'] == 0:
            r['created'] = False

        else:
            
            # If error is not "artifact not found", return the error
            if r['return'] != 16:
                return r
            
            # Artifact doesn't exist, create it
            r = self.create_(state, arg1, tags=tags, meta=meta, yaml=yaml, virtual=virtual, path=path)
            if r['return'] > 0:
                return r
            
            # Read the newly created artifact
            r = self.read_(state, arg1, tags=tags, skip_uids=skip_uids, yaml=yaml, load_files=load_files)
            if r['return'] > 0:
                return r
            
            r['created'] = True

        if con and show_path:
            print (r['artifact']['path'])

        return r

    ############################################################
    def set_(
            self,
            state: dict,             # cMeta state
            arg1: str = None,        # Artifact alias or UID
            tags: str = None,        # Tags to add to the artifact (for creation)
            skip_uids: bool = False,  # Skip UIDs when using wildcards
            yaml: bool = False,      # Save/output metadata as YAML instead of JSON
            meta: dict = {},         # Initial metadata dictionary (for creation)
            virtual: bool = False,   # Virtual artifact created only in index (for creation)
            path: str = None,        # Use this path for artifact (for creation)
            show_path: bool = False
    ):
        """
        Set artifact meta. Update and read if exists, create and read if doesn't exist.

        Args:
            state (dict): cMeta state.
            arg1 (str | None): Artifact alias or UID.
            tags (str | list | None): Tags to add to the artifact (used during creation).
            skip_uids (bool): Skip UIDs when using wildcards.
            yaml (bool): Save/output metadata as YAML instead of JSON.
            meta (dict): Initial metadata dictionary (used during creation).
            virtual (bool): Virtual artifact created only in index (used during creation).
            path (str | None): Use this path for artifact (used during creation).
            show_path (bool): Print path instead of meta 

        Returns:
            dict: A cMeta dictionary with the following keys:
                - **return** (int): 0 if success, >0 if error.
                - **error** (str): Error message if `return > 0`.
                - **artifact** (dict): Matched artifact.
                - **cmeta** (dict): Artifact metadata.
                - **created** (bool): True if artifact was created, False if it already existed.
        """
        
        # Try to read the artifact first
        con = state.get('control',{}).get('con', False)

        import copy
        state = copy.deepcopy(state)

        state['control']['con'] = False

        r = self.read_(state, arg1, tags=tags, skip_uids=skip_uids)
        
        # If artifact exists, return it
        created = False

        if r['return'] == 0:
            # Artifact doesn't exist, create it
            r = self.update_(state, arg1, tags=tags, meta=meta)
            if r['return'] > 0:
                return r

        else:
            # If error is not "artifact not found", return the error
            if r['return'] != 16:
                return r
            
            # Artifact doesn't exist, create it
            r = self.create_(state, arg1, tags=tags, meta=meta, yaml=yaml, virtual=virtual, path=path)
            if r['return'] > 0:
                return r

            created = True
            
        # Read the newly created artifact
        if con and not show_path:
            state['control']['con'] = True

        r = self.read_(state, arg1, tags=tags, skip_uids=skip_uids, yaml=yaml)
        if r['return'] > 0:
            return r
            
        r['created'] = created

        if con and show_path:
            print (r['artifact']['path'])

        return r
