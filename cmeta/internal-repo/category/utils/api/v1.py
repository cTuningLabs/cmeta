"""
cMeta misc utilities

cMeta author and developer: (C) 2025 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
from cmeta.category import InitCategory

from cmeta.utils import names

from . import common

class Category(InitCategory):
    """
    Various Utils
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path = __file__, **kwargs)

    ############################################################
    def uid_(
        self,
        state           # [dict] cMeta state object
    ):
        """
        Generate UID

        Args:
            state (dict): cMeta state object.
        """

        self.logger.debug("running utils.uid")

        con = state['control'].get('con', False)

        uid = names.generate_cmeta_uid()

        if con:
            print (uid)

        return {'return':0, 'uid':uid}

    ############################################################
    def uuid_(
        self,
        state           # [dict] cMeta state object
    ):
        """
        Generate UUID

        Args:
            state (dict): cMeta state object.
        """

        import uuid

        self.logger.debug("running utils.uuid")

        con = state['control'].get('con', False)

        uuid = str(uuid.uuid4())

        if con:
            print (uuid)

        return {'return':0, 'uuid':uuid}

    ############################################################
    def find_by_cid_(
        self,
        state,          # [dict] cMeta state object
        arg1,           # [str] Standard CID
        tags = None,    # [str] tags
        ask = False,    # [bool] If True, ask for CID in console
    ):
        """
        Find artifacts by standard CID

        Args:
            state (dict): cMeta state object.
            arg1 (str): Standard CID.
            ask (bool): If True, ask for CID in console.
        """
        self.logger.debug("running utils.find_by_cid")

        con = state['control'].get('con', False)

        if ask:
            arg1 = input('Enter CID: ')

        r = names.parse_cmeta_ref(arg1, fail_on_error = self.fail_on_error)
        if r['return']>0: return r

        artifact_ref_parts = r['ref_parts']

        if self.cm.debug:
            self.logger.debug(f"artifact_ref_parts={artifact_ref_parts}")

        r = self.cm.repos.find(artifact_ref_parts, tags=tags)
        if r['return']>0: return r

        artifacts = r['artifacts']

        # if no artifact found, "find" function will return error
        # we need to check >1 for ambiguity
        if con:
            for artifact in artifacts:
                print (artifact['path'])

        return r

    ############################################################
    def smart_find_by_cid_(
        self,
        state,              # [dict] cMeta state object
        arg1 = None,        # [str] CID that can be wrapped with some text
        far = False,        # [bool] If True, open FAR in found artifact
        web = False,        # [bool] If True, remove cmeta:///? from CID (web request)
        ask = False,        # [bool] If True, ask for CID in console
        cid = None          # [str] Direct CID to use
    ):
        """
        Find artifacts by wrapped CID

        Args:
            state (dict): cMeta state object.
            arg1 (str): CID that can be wrapped with some text.
            far (bool): If True, open FAR in found artifact.
            web (bool): If True, remove cmeta:///? from CID (web request).
            ask (bool): If True, ask for CID in console.
            cid (str): Direct CID to use.
        """
        self.logger.debug("running utils.find_by_cid_smart")

        con = state['control'].get('con', False)

        if ask:
            arg1 = input('Enter complex CID: ')

        if web and arg1.startswith('cmeta:///?'):
            cid = arg1[10:]

            from urllib.parse import unquote
            cid = unquote(cid)
        elif cid is not None:
            cid = common._extract_category_artifact(cid) 
        elif arg1 is not None:
            cid = common._extract_category_artifact(arg1) 
        else:
            return {'return':1, 'error': 'CID is not specified'}

        if self.cm.debug:
            self.logger.debug(f"extracted_cid={cid}")

        if cid is None:
            return {'return':1, 'error':f'Could not extract CID from the input string (arg1)'}

        r = self.find_by_cid_(state, cid)
        if r['return']>0: return r

        artifacts = r['artifacts']

        path = artifacts[0]['path']

        if far:
            os.system(f'start far {path}')

        return r

    ############################################################
    def copy_text_to_clipboard_(
        self,
        state,                  # [dict] cMeta state object
        arg1 = "",              # [str] Text to copy to clipboard
        add_quotes = False,     # [bool] Add quotes to the text if True
        do_not_fail = True      # [bool] Do not fail on error if True
    ):
        """
        Copy text to clipboard

        Args:
            state (dict): cMeta state object.
            arg1 (str): Text to copy to clipboard.
            add_quotes (bool): Add quotes to the text if True.
            do_not_fail (bool): Do not fail on error if True.
        """

        return self.cm.utils.common.copy_text_to_clipboard(arg1, add_quotes)


    ############################################################
    def json2yaml_(
        self,
        state,                  # [dict] cMeta state object
        arg1,                   # [str] Input JSON file
        arg2 = None,            # [str] Output YAML file (if None, use {input file without ext}.yaml)
        force = False,          # [bool] If True and output file exists, overwrite it
        f = False,              # [bool] If True and output file exists, overwrite it
        sort_keys = False       # [bool] Sort keys in output if True
    ):
        """
        Convert JSON file to YAML file

        Args:
            state (dict): cMeta state object.
            arg1 (str): Input JSON file.
            arg2 (str): Output YAML file (if None, use {input file without ext}.yaml).
            force (bool): If True and output file exists, overwrite it.
            f (bool): If True and output file exists, overwrite it.
            sort_keys (bool): Sort keys in output if True.
        """

        self.logger.debug("running utils json2yaml")

        con = state['control'].get('con', False)

        r = self.cm.utils.files.safe_read_file(arg1)
        if r['return'] > 0: return r

        data = r['data']

        if arg2 is None:
            arg2 = f"{os.path.splitext(arg1)[0]}.yaml"

        if os.path.isfile(arg2) and not (force or f):
            return {'return':1, 'error':f'Output file already exists (use --force or --f option to overwrite): {arg2}'} 

        r = self.cm.utils.files.safe_write_file(arg2, data, sort_keys=sort_keys)
        if r['return'] > 0: return r

        return {'return':0}


    ############################################################
    def yaml2json_(
        self,
        state,                  # [dict] cMeta state object
        arg1,                   # [str] Input YAML file
        arg2 = None,            # [str] Output JSON file (if None, use {input file without ext}.json)
        force = False,          # [bool] If True and output file exists, overwrite it
        f = False,              # [bool] If True and output file exists, overwrite it
        sort_keys = False       # [bool] Sort keys in output if True
    ):
        """
        Convert YAML file to JSON file

        Args:
            state (dict): cMeta state object.
            arg1 (str): Input YAML file.
            arg2 (str): Output JSON file (if None, use {input file without ext}.json).
            force (bool): If True and output file exists, overwrite it.
            f (bool): If True and output file exists, overwrite it.
            sort_keys (bool): Sort keys in output if True.
        """

        self.logger.debug("running utils yaml2json")

        con = state['control'].get('con', False)

        r = self.cm.utils.files.safe_read_file(arg1)
        if r['return'] > 0: return r

        data = r['data']

        if arg2 is None:
            arg2 = f"{os.path.splitext(arg1)[0]}.json"

        if os.path.isfile(arg2) and not (force or f):
            return {'return':1, 'error':f'Output file already exists (use --force or --f option to overwrite): {arg2}'} 

        r = self.cm.utils.files.safe_write_file(arg2, data, sort_keys=sort_keys)
        if r['return'] > 0: return r

        return {'return':0}


    ############################################################
    def pkl2json(self, params):
        """
        @self.pickle2json_
        """

        return self.pickle2json_(**params)


    ############################################################
    def pickle2json_(
        self,
        state,                  # [dict] cMeta state object
        arg1,                   # [str] Pickle file
        arg2 = None,            # [str] JSON file (if not specified, use base of pickle file with .json)
        sort_keys = False       # [bool] Sort keys in output if True
    ):
        """
        Convert pickle file to JSON file

        Args:
            state (dict): cMeta state object.
            arg1 (str): Pickle file.
            arg2 (str): JSON file (if not specified, use base of pickle file with .json).
            sort_keys (bool): Sort keys in output if True.
        """

        import os
        import pickle
        import json

        con = state['control'].get('con', False)

        # Check if pickle file exists
        if not os.path.isfile(arg1):
            return {'return':1, 'error':f'Pickle file not found: {arg1}'}

        # Set default json filename if not provided
        if arg2 is None:
            base = os.path.splitext(arg1)[0]
            arg2 = f"{base}.json"

        # Load pickle file
        try:
            with open(arg1, 'rb') as f:
                data = pickle.load(f)
        except Exception as e:
            return {'return':1, 'error':f'Failed to load pickle file: {e}'}

        # Save to json file
        try:
            with open(arg2, 'w') as f:
                json.dump(data, f, sort_keys=sort_keys, indent=2)
                f.write('\n')
        except Exception as e:
            return {'return':1, 'error':f'Failed to save JSON file: {e}'}

        if con:
            print (f'Successfully converted {arg1} to {arg2}')

        return {'return':0, 'json_file': arg2}

    ############################################################
    def json2pickle_(
        self,
        state,              # [dict] cMeta state object
        arg1,               # [str] JSON file
        arg2 = None         # [str] Pickle file (if not specified, use base of json file with .pkl)
    ):
        """
        Convert JSON file to pickle file

        Args:
            state (dict): cMeta state object.
            arg1 (str): JSON file.
            arg2 (str): Pickle file (if not specified, use base of json file with .pkl).
        """

        import os
        import pickle
        import json

        con = state['control'].get('con', False)

        # Check if json file exists
        if not os.path.isfile(arg1):
            return {'return':1, 'error':f'JSON file not found: {arg1}'}

        # Set default pickle filename if not provided
        if arg2 is None:
            base = os.path.splitext(arg1)[0]
            arg2 = f"{base}.pkl"

        # Load json file
        try:
            with open(arg1, 'r') as f:
                data = json.load(f)
        except Exception as e:
            return {'return':1, 'error':f'Failed to load JSON file: {e}'}

        # Save to pickle file
        try:
            with open(arg2, 'wb') as f:
                pickle.dump(data, f)
        except Exception as e:
            return {'return':1, 'error':f'Failed to save pickle file: {e}'}

        if con:
            print (f'Successfully converted {arg1} to {arg2}')

        return {'return':0, 'pickle_file': arg2}

    ############################################################
    def utf8sig_to_utf8_(
        self,
        state,              # [dict] cMeta state object
        arg1,               # [str] Input file (UTF-8 with BOM)
        arg2 = None         # [str] Output file (if None, overwrites input file and creates .bak backup)
    ):
        """
        Convert UTF-8 with BOM (utf-8-sig) file to standard UTF-8

        Args:
            state (dict): cMeta state object.
            arg1 (str): Input file (UTF-8 with BOM).
            arg2 (str): Output file (if None, overwrites input file and creates .bak backup).
        """

        import os
        import shutil

        con = state['control'].get('con', False)

        # Check if input file exists
        if not os.path.isfile(arg1):
            return {'return':1, 'error':f'Input file not found: {arg1}'}

        # Read file with utf-8-sig encoding (strips BOM automatically)
        try:
            with open(arg1, 'r', encoding='utf-8-sig') as f:
                content = f.read()
        except Exception as e:
            return {'return':1, 'error':f'Failed to read file: {e}'}

        # Determine output file
        if arg2 is None:
            # Create backup of original file
            backup_file = f"{arg1}.bak"
            try:
                shutil.copy2(arg1, backup_file)
                if con:
                    print(f'Created backup: {backup_file}')
            except Exception as e:
                return {'return':1, 'error':f'Failed to create backup: {e}'}
            arg2 = arg1

        # Write file with standard utf-8 encoding (without BOM)
        try:
            with open(arg2, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)
        except Exception as e:
            return {'return':1, 'error':f'Failed to write file: {e}'}

        if con:
            print(f'Successfully converted {arg1} to UTF-8 (without BOM)')
            if arg2 != arg1:
                print(f'Output saved to: {arg2}')

        return {'return':0, 'output_file': arg2}


    ############################################################
    def convert_old_entries_(
        self,
        state,              # [dict] cMeta state object
        arg1 = '.',         # [str] path to entries to convert
        meta = {},          # [dict] Merge this meta
    ):
        """
        Convert legacy CK/CM/CMX entries in a path (arg1) by merging _cmeta.json or _cmeta.yaml with meta

        Args:
            state (dict): cMeta state object.
            arg1 (str): Path to search for entries to convert.
            meta (dict): Merge this meta with existing _cmeta files.
        """

        import os

        con = state['control'].get('con', False)

        # Check if path exists
        if not os.path.exists(arg1):
            return {'return':1, 'error':f'Path not found: {arg1}'}

        converted_count = 0
        error_count = 0
        errors = []

        # Recursively walk through all subdirectories
        for root, dirs, files in os.walk(arg1):
            # Look for _cmeta.json or _cmeta.yaml
            cmeta_file = None
            if '_cmeta.json' in files:
                cmeta_file = os.path.join(root, '_cmeta.json')
            elif '_cmeta.yaml' in files:
                cmeta_file = os.path.join(root, '_cmeta.yaml')

            if cmeta_file:
                if con:
                    print(f'Processing: {cmeta_file}')

                # Load existing meta file
                r = self.cm.utils.files.safe_read_file(cmeta_file)
                if r['return'] > 0:
                    error_msg = f"Failed to read {cmeta_file}: {r.get('error', 'Unknown error')}"
                    errors.append(error_msg)
                    error_count += 1
                    if con:
                        print(f'  ERROR: {error_msg}')
                    continue

                existing_data = r['data']

                # Merge with provided meta (meta takes precedence)
                merged_data = {**existing_data, **meta}

                # Save back to the same file
                r = self.cm.utils.files.safe_write_file(cmeta_file, merged_data)
                if r['return'] > 0:
                    error_msg = f"Failed to write {cmeta_file}: {r.get('error', 'Unknown error')}"
                    errors.append(error_msg)
                    error_count += 1
                    if con:
                        print(f'  ERROR: {error_msg}')
                    continue

                converted_count += 1
                if con:
                    print(f'  Successfully converted')
            
            else:
                # Check for legacy _cm.yaml or _cm.json files
                cm_yaml_file = os.path.join(root, '_cm.yaml') if '_cm.yaml' in files else None
                cm_json_file = os.path.join(root, '_cm.json') if '_cm.json' in files else None
                
                if cm_yaml_file or cm_json_file:
                    if con:
                        print(f'Processing legacy files in: {root}')
                    
                    merged_data = {}
                    
                    # First, try to read _cm.yaml
                    if cm_yaml_file:
                        if con:
                            print(f'  Reading: {cm_yaml_file}')
                        r = self.cm.utils.files.safe_read_file(cm_yaml_file)
                        if r['return'] > 0:
                            error_msg = f"Failed to read {cm_yaml_file}: {r.get('error', 'Unknown error')}"
                            errors.append(error_msg)
                            error_count += 1
                            if con:
                                print(f'  ERROR: {error_msg}')
                            continue
                        merged_data = r['data']
                    
                    # Then, try to read and merge _cm.json
                    if cm_json_file:
                        if con:
                            print(f'  Reading: {cm_json_file}')
                        r = self.cm.utils.files.safe_read_file(cm_json_file)
                        if r['return'] > 0:
                            error_msg = f"Failed to read {cm_json_file}: {r.get('error', 'Unknown error')}"
                            errors.append(error_msg)
                            error_count += 1
                            if con:
                                print(f'  ERROR: {error_msg}')
                            continue
                        merged_data = {**merged_data, **r['data']}
                    
                    # Finally, merge with provided meta (meta takes precedence)
                    merged_data = {**merged_data, **meta}

                    if 'artifact' not in merged_data and 'uid' in merged_data:
                        merged_data['artifact'] = merged_data['uid']

                    # Save to _cmeta.json
                    output_file = os.path.join(root, '_cmeta.json')
                    if con:
                        print(f'  Writing: {output_file}')
                    
                    r = self.cm.utils.files.safe_write_file(output_file, merged_data)
                    if r['return'] > 0:
                        error_msg = f"Failed to write {output_file}: {r.get('error', 'Unknown error')}"
                        errors.append(error_msg)
                        error_count += 1
                        if con:
                            print(f'  ERROR: {error_msg}')
                        continue
                    
                    converted_count += 1
                    if con:
                        print(f'  Successfully converted legacy files to _cmeta.json')

        if con:
            print(f'\nConversion complete:')
            print(f'  Files converted: {converted_count}')
            print(f'  Errors: {error_count}')

        result = {
            'return': 0 if error_count == 0 else 1,
            'converted_count': converted_count,
            'error_count': error_count
        }

        if errors:
            result['errors'] = errors

        return result

    ############################################################
    def artifacts_(self, state, arg1 = None, arg2 = None, skip_categories = None, func = None, func_params = {}):
        """
        Analyze all artifacts for all categories

        arg1: categories
        arg2: artifacts
        top_num: number of top artifacts to show in rankings (default: 30)
        slow: if False (default), use cached results when artifact hasn't changed; if True, always perform deep analysis

        @base.find_
        """

        import time
        from datetime import datetime

        start_time = time.time()

        con = state.get('control',{}).get('con', False)

        if skip_categories is None:
            skip_categories = ['repo', 'log', 'result']

        # First, find all categories
        p = {'category': 'category',
             'command':'find',
             'arg1': arg1}     
        
        r = self.cm.access(p)
        if r['return']>0: return r

        categories = r.get('artifacts', [])
        
        if con:
            print (f'Found {len(categories)} categories')
            print ('')

        all_artifacts = []
        num = 0

        # Process artifacts for each category
        for category in categories:
            category_cmeta = category['cmeta']
            category_cmeta_ref_parts = category['cmeta_ref_parts']
            
            category_alias = category_cmeta_ref_parts.get('artifact_alias')
            category_uid = category_cmeta_ref_parts['artifact_uid']

            if category_alias in skip_categories:
                continue

            if con:
                print ('-'*50)
                print (f'Processing category: {category_alias},{category_uid}')
                print ('')

            p = {'category':category_uid,
                 'command': 'find',
                 'arg1': arg2}
            
            r = self.cm.access(p)
            if r['return']==0:

                artifacts = r.get('artifacts', [])
                if len(artifacts)>0:
                    all_artifacts.extend(artifacts)

                    for artifact in artifacts:
                        num += 1
                        path = artifact['path']

                        if os.path.isdir(path):

                            mtime = os.path.getmtime(path)
                            modified_dt = datetime.fromtimestamp(mtime)

                            if con:
                                print ('='*80)
                                print (f' Artifact:      {num}')
                                print (f' Path:          {path}')
                                print (f' Last modified: {modified_dt}')


                            if func is not None:
                                r = func(artifact, num, func_params)
                                if r['return']>0: return r

                                add = r.get('add_to_artifact', {})
                                if len(add)>0:
                                    artifact['add'] = add 

                    if con and num > 0:
                        print ('')

        elapsed_time = time.time() - start_time

        if con:
            print ('*'*80)
            print (f'Total artifacts: {num}')
            print (f'Elasped time:    {elapsed_time:.1f} seconds')

        return {'return':0, 'artifacts': all_artifacts, 'elapsed_time': elapsed_time}


    ############################################################
    def create_artifact_with_date(self, params):
        """
        Create artifact with date

        @base.create_
        """

        from_category = params['from_category']

        category_alias = from_category['artifact_alias']

        self.logger.debug(f"From category: {category_alias}")

        con = params['state']['control'].get('con', False)

        from datetime import datetime
        yyyymmdd = datetime.now().strftime("%Y%m%d")

        p = self._prepare_input_from_params(params, base = True)

        # Check config if need to do something with a path, i.e. open it with some application
        r = self.cm.access({'category': 'config,cc6bfe174be847ed',
                            'command': 'get',
                            'arg1': self.cm.cfg['default_config_name']})
        if r['return'] > 0: return r

        config_cmeta = r['config_cmeta']

        key = f'{category_alias}'.replace('.','_') + '_create_cmd'
        key2 = f'{category_alias}'.replace('.','_') + '_create_repo'

        # Parse cMeta obj
        arg1 = p.get('arg1')

        r = self.cm.utils.names.parse_cmeta_obj(arg1)
        if r['return'] > 0: return r

        arg1_obj_parts = r['obj_parts']

        alias = arg1_obj_parts.get('alias')
        
        if alias is None:
            if con:
                alias = input(f'Enter {category_alias} name: ')
                alias = alias.strip()

        if alias is None or alias == '':
            alias = yyyymmdd
        else:
            if not (len(alias) >= 8 and alias[:8].isdigit()):
                alias = yyyymmdd + '.' + alias

        arg1_obj_parts['alias'] = alias

        # Check target repo
        repo_alias = arg1_obj_parts.get('repo_alias')
        if repo_alias is None:
            repo_alias = config_cmeta.get(key2)
            if repo_alias is not None and repo_alias != '':
                arg1_obj_parts['repo_alias'] = repo_alias

        # Restore cMeta obj
        r = self.cm.utils.names.restore_cmeta_obj(arg1_obj_parts)
        if r['return'] > 0: return r

        p['category'] = from_category
        p['command'] = 'get'
        p['arg1'] = r['obj']
        p['con'] = False
        del(p['from_category'])

        # Create artifact
        r = self.cm.access(p)
        if r['return'] > 0: return r

        path = r['artifact']['path']

        if con:
            print (f'Path to {category_alias}s: {path}')
        
        cmd = config_cmeta.get(key)

        if cmd is not None and cmd != '':
            cmd = cmd.replace('{path}', path)
            if con:
                print (f'Executing: {cmd}')
            
            os.system(cmd)

        return r



    ############################################################
    def access_ctuning_server_(self, state, query={}, headers={}, timeout=30, url=None, api_key=None, files={}):
        """
        Access cTuning server

        """

        import copy

        con = state['control'].get('con', False)

        # Check config if need to do something with a path, i.e. open it with some application
        r = self.cm.access({'category': 'config,cc6bfe174be847ed',
                            'command': 'get',
                            'arg1': 'ctuning_server'})
        if r['return'] > 0: return r

        config_cmeta = r['config_cmeta']

        if url is None or url == '':
            url = config_cmeta.get('url')
            if url is None or url == '':
                url = self.cm.cfg['default_ctuning_api']

        if api_key is None or api_key == '':
            api_key = config_cmeta.get('api_key')
        if api_key is not None and api_key != '':
            headers = copy.deepcopy(headers)
            headers['x-api-key'] = api_key

        if len(files)>0:
            r = self.cm.utils.files.files_encode(files)
            if r['return']>0: return r

            query['files_base64'] = r['files_base64']

        if con:
            print (f'Sending request to {url} ...')

        r = self.cm.utils.net.access_api(url, query, headers, timeout)
        if r['return']>0: return r

        if con:
            print ('')
            import json
            print (json.dumps(r, indent=2))

        return r

    ############################################################
    def x(self, params):
        """
        Create artifact with date

        @self.access_ctuning_server_
        """
        return self.access_ctuning_server_(**params)
