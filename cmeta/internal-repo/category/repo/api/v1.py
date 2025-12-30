"""
cMeta repo functions

cMeta author and developer: (C) 2025 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
from cmeta.category import InitCategory

from cmeta import utils
from datetime import datetime

from . import common

class Category(InitCategory):
    """
    Various Utils
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path = __file__, **kwargs)


    ###############################################################################################
    def get_(
            self, 
            state:                  dict,                # cMeta state.
            arg1:                   str = None,          # Repo name (alias and/or UID).
            url:                    str = None,          # Repo URL (optional)
            path:                   str = None,          # Repo path (optional. $HOME/CMETA/{repo alias} by default)
            folder:                 str = None,          # Force this folder to store repository inside $HOME/CMETA (skiped if path is set)
            subdir:                 str = None,          # Repository is stored in this 
            method:                 str = None,          # Method (git, zip, local) - will be detected automatically if not specified
            local:                  bool = False,        # If True, set method to 'local'
            meta:                   dict = None,         # Repo meta data 
            update:                 bool = False,        # Force update git repos
            status:                 bool = False,        # Check status of git repos
            checkout:               str = None,          # git checkout to this branch or commit

            pre:                    str = '',
            post:                   str = '',
            hide:                   bool = False,        # hide git clone command print (if PAT/secret is present) 

            skip_parent_dir_in_zip: bool = False,

            zip_file:               str = None,
    ):
        """
        Clone or pull CM repository.

        Args:
          (CM input dict): 

          (out) (str): if 'con', output to console

          (artifact) (str): repository name (alias)
          (url) (str): URL of a repository
          (pat) (str): Personal Access Token (if supported and url=='')
          (branch) (str): Git branch
          (new_branch) (str): Create new Git branch
          (checkout) (str): Git checkout
          (checkout_only) (bool): only checkout existing repo
          (dir) (str): use repository in this directory
          (dir2) (str): use repository in this "directory/directory"
          (depth) (int): Git depth
          (desc) (str): brief repository description (1 line)
          (prefix) (str): extra directory to keep CM artifacts
          (skip_zip_parent_dir) (bool): skip parent dir in CM ZIP repo (useful when 
                                        downloading CM repo archives from GitHub)
          (extra_cmd_git) (str): add this string to git clone
          (extra_cmd_pip) (str): add this string to pip install when installing
                                 requirements from CM repositories

        Returns:
          (CM return dict):

          * return (int): return code == 0 if no error and >0 if error
          * (error) (str): error string if return>0
        """

        con = state.get('control',{}).get('con', False)
        verbose = state.get('control',{}).get('verbose', False)

        repos_path = self.cm.repos_path
        repos_config_path = self.cm.repos_config_path

        command = state['command']

        cur_dir = os.getcwd()

        # Process arg1 and URL to extract repo name and understand what to do with repositories ...
        repo_name = None
        repo_alias = None
        repo_uid = None

        if (url is not None and url != ''):
            repo_name = arg1
        else:
            if arg1 is not None and not (arg1.startswith('https://') or arg1.startswith('git@')):
                repo_name = arg1
            else:
                url = arg1

        if local:
            method = 'local'

        if zip_file is not None:
            if not os.path.isfile(zip_file):
                return {'return':1, 'error':f'zip file {zip_file} not found'}

            method = 'local_zip'

        # Search for an artifact
        repo_artifacts = []

        search = False

        reindex = False

        add_repo_paths_to_index = []

        ######################################################################################################################
        if (repo_name is not None and repo_name != '') or (path is None and url is None and zip_file is None):
            # Call base find function to find an artifact
            p = {'category':state['category'], 
                 'command':'find',
                 'sort':False,
                 'base':True}

            if repo_name is not None:
                p['arg1'] = repo_name

            r = self.cm.access(p)
            if r['return']>0 and r['return']!=16: return r

            repo_artifacts = r.get('artifacts',[])

        ######################################################################################################################
        if len(repo_artifacts)>0:
            # If some rep   os are already registered
            # try to update them (pull/checkout/branch if git)

            if command in ['init']:
                return {'return':1, 'error':f'repository {arg1} already exists'}

            r = utils.files.safe_read_file(repos_config_path, lock=False, fail_on_error=self.fail_on_error, logger=self.logger)
            if r['return']>0: return r

            repos_paths = r['data']

            for repo in repo_artifacts:
                repo_path = repo['path']
                repo_meta = repo['cmeta']

                repo_cmeta_ref_parts = repo['cmeta_ref_parts']
                repo_alias = repo_cmeta_ref_parts.get('artifact_alias')
                repo_uid= repo_cmeta_ref_parts['artifact_uid']

                xmethod = repo_meta.get('method')

                if repo_path not in repos_paths:
                    caller = state.get('origin',{}).get('cli',{}).get('caller','')
                    return {'return':1, 'error':f'File {repos_config_path} may be corrupted - it doesn\'t contain {repo_path}! Try "{caller} --reindex"'}

                if os.path.isdir(repo_path):
                    if con:
                        print ('='*80)
                        print (f'{repo_alias} ({repo_uid}): {repo_path}')

                    if xmethod == 'git':

                        if status:
                            print ('')
                            print ('Checking repository status ...')

                            cmds = ['git remote get-url origin', 'git status']

                            for cmd in cmds:

                                r = utils.sys.run(cmd, work_dir=repo_path, con=con, verbose=True)
                                if r['return']>0: return r

                                rc = r['returncode']
                                if rc != 0:
                                    return {'return':1, 'error':f'System command "{cmd}" failed with exit code {rc}'}


                        else:
                            if checkout is not None and checkout != '':
                                cmd = f'git checkout {checkout}'

                                if con:
                                    print ('')
                                    print (f'Checking out repository in {repo_path} ...')

                                r = utils.sys.run(cmd, work_dir=repo_path, con=con)
                                if r['return']>0: return r

                                rc = r['returncode']
                                if rc != 0:
                                    return {'return':1, 'error':f'System command "{cmd}" failed with exit code {rc}'}

                            else:
                                print ('')
                                print ('Updating git repository ...')

                                cmd = 'git pull'

                                r = utils.sys.run(cmd, work_dir=repo_path, con=con)
                                if r['return']>0: return r

                                rc = r['returncode']
                                if rc != 0:
                                    print (f'Warning: system command "{cmd}" failed with exit code {rc}')
#                                    return {'return':1, 'error':f'"System command {cmd}" failed with exit code {rc}'}


                            add_repo_paths_to_index.append(repo_path)

                            reindex= True

                    if con:
                        r = self.cm.utils.sys.get_disk_space(path=repo_path, nice=True, unit='GB')
                        if r['return']>0: return r

                        nice_free = r['nice_free']

                        print ('')
                        print (f'Free space in this repo: {nice_free}')

        ######################################################################################################################
        elif update or status:
            if con:
                print ('No repositories found ...')

            return {'return':0}

        ######################################################################################################################
        else:
            # It's a new repo
            if zip_file is not None:
                repo_name = zip_file

            if repo_name is not None and repo_name != '':
                # Spread into alias and UID
                r = utils.names.parse_cmeta_name(repo_name)
                if r['return']>0: return r

                repo_alias = r.get('name',{}).get('alias')
                repo_uid = r.get('name',{}).get('uid')


            if path is None or path == '':
                # Need to figure out path

                if repo_name is not None and repo_name != '':
                    if method != 'local':
                        if url is None or url == '':
                            if '@' not in repo_alias:
                                repo_alias = self.cm.cfg['default_git_repo'] + '@' + repo_alias

                            url = self.cm.cfg['default_git'] + '/' + repo_alias.replace('@','/')

                    if folder is None or folder == '':
                        folder = repo_alias if repo_alias is not None else repo_uid

                elif folder is None or folder == '':
                    r = self.get_alias_from_url_(state, url)
                    if r['return']>0: return r

                    repo_alias = r['alias']
                    folder = repo_alias
                else:
                    if repo_alias is None or repo_alias == '':
                        repo_alias = folder

                path = os.path.join(repos_path, folder)

            # Check method
            if not method and url:
                if url.endswith('.zip'):
                    method = 'zip'
                else:
                    method = 'git'

            ######################################################################################################################
            # Check what to do depending on whether the path exists or not
            if os.path.isdir(path) and method != 'local':
                return {'return':1, 'error':f'directory {path} already exists'}

            if not os.path.isdir(path):
                if method == 'git':
                    xpre = '' if pre == '' else ' ' + pre
                    xpost = '' if post == '' else ' ' + post

                    cmd = f'git clone{xpre} "{url}" "{path}"{xpost}'

                    if con:
                        print ('')
                        print (f'Cloning repository in {path} ...')

                    xcon = False if hide else con
                    r = utils.sys.run(cmd, con=xcon)
                    if r['return']>0: return r

                    rc = r['returncode']
                    if rc != 0:
                        return {'return':1, 'error':f'System command "{cmd}" failed with exit code {rc}'}

                    if checkout is not None and checkout != '':
                        cmd = f'git checkout {checkout}'

                        if con:
                            print ('')
                            print (f'Checking out repository in {path} ...')

                        r = utils.sys.run(cmd, work_dir=path, con=con)
                        if r['return']>0: return r

                        rc = r['returncode']
                        if rc != 0:
                            return {'return':1, 'error':f'System command "{cmd}" failed with exit code {rc}'}
                    

                elif method == 'local_zip':
                    # Unzip with cleaning
                    r = utils.files.unzip(zip_file, path=path, overwrite=False, clean=False, fail_on_error = self.fail_on_error)
                    if r['return'] >0: return r

                elif method == 'zip':
                    # Download zip
                    r = utils.net.download(url, path=path, show_progress=con, fail_on_error = self.fail_on_error)
                    if r['return'] >0: return r

                    full_path_to_zip_file = r['path']

                    # Unzip with cleaning
                    r = utils.files.unzip(full_path_to_zip_file, path=path, overwrite=False, clean=True, fail_on_error = self.fail_on_error)
                    if r['return'] >0: return r

                elif method == 'local':
                    if con:
                        print ('')
                        print (f'Creating local repository in {path} ...')

                    try:
                        os.makedirs(path)
                    except Exception as e:
                        return {'return':1, 'error':f'Failed to create directory: {e}'}

                else:
                    return {'return':1, 'error':f'unsupported method {method}'}

            ######################################################################################################################
            # Check if repository was created
            if os.path.isdir(path):
                path = os.path.abspath(os.path.normpath(path))
                # Try to read _cmr.yaml or create it (if already exists, to get correct artifact name and UID)
                repo_meta_desc_path = os.path.join(path, self.cm.cfg['repo_meta_desc'])

                repo_meta = {}
                repo_meta_file_lock = None
                repo_updated = False

                repo_meta_to_index = {'method':method}

                if os.path.isfile(repo_meta_desc_path):
                    r = utils.files.safe_read_file(repo_meta_desc_path, lock=True, keep_locked=True, fail_on_error=self.fail_on_error, logger=self.logger)
                    if r['return']>0: return r

                    repo_meta = r['data']
                    repo_meta_file_lock = r['file_lock']

                if meta is not None and len(meta)>0:
                    repo_meta = utils.common.deep_merge(repo_meta, meta, append_lists=True)
                    repo_updated = True

                if 'category' not in repo_meta:
                    r = utils.names.restore_cmeta_name(state['category'], key='artifact')
                    if r['return']>0: return r
                    repo_meta['category'] = r['name']
                    repo_updated = True

                if repo_alias is None:
                    repo_alias = os.path.basename(path)

                final_repo_name = repo_meta.get('artifact')
                if final_repo_name is None or final_repo_name == '':
                    final_repo_name = ''
                    if repo_alias != '': 
                        final_repo_name = repo_alias + ','
                    if repo_uid == None or repo_uid == '':
                        repo_uid = utils.names.generate_cmeta_uid()
                    final_repo_name += repo_uid

                    repo_meta['artifact'] = final_repo_name

                    if subdir is not None:
                        repo_meta_to_index['subdir'] = subdir
                        repo_meta['subdir'] = subdir
#                    repo_meta.update(repo_meta_to_index)

                    repo_update = True

                if repo_updated:
                    r = utils.files.safe_write_file(repo_meta_desc_path, repo_meta, file_lock=repo_meta_file_lock, atomic=True, fail_on_error=self.fail_on_error, logger=self.logger)
                    if r['return']>0: return r
                elif repo_meta_file_lock is not None:
                    r = utils.files.unlock_path(repo_meta_desc_path, file_lock=repo_meta_file_lock, fail_on_error=self.fail_on_error, logger=self.logger)
                    if r['return']>0: return r

                # Check if repo already registered
                repo_name2 = repo_meta.get('artifact')

                if repo_name2 is not None and repo_name2 != '':
                    # Call base find function to find an artifact with a website
                    p = {'category':state['category'], 
                         'command':'find',
                         'arg1':repo_name2,
                         'sort':False,
                         'base':True}
                    r = self.cm.access(p)
                    if r['return']>0 and r['return']!=16: return r

                    if len(r.get('artifacts',[]))>0:
                        return {'return':1, 'error':f'repository {repo_name2} already registered'}


                # Append to the list of repos
                r = utils.files.safe_read_file(repos_config_path, lock=True, keep_locked=True, fail_on_error=self.fail_on_error, logger=self.logger)
                if r['return']>0: return r

                repos_paths = r['data']
                repos_paths_file_lock = r['file_lock']
                
                if path not in repos_paths:
                    repos_paths[path] = {'meta':repo_meta_to_index}

                    # I decided not to add params to avoid exposing sensitite info such as PAT in URL, 'params':state['origin']['params']}}

                # Do not sort keys - preserve order!
                r = utils.files.safe_write_file(repos_config_path, repos_paths, file_lock=repos_paths_file_lock, atomic=True, 
                                                fail_on_error=self.fail_on_error, logger=self.logger, sort_keys=False)
                if r['return']>0: return r

                # Check subdir
                if repo_meta_to_index.get('subdir','') != '':
                    full_path = os.path.join(path, repo_meta_to_index['subdir'])
                    if not os.path.isdir(full_path):
                        try:
                            os.makedirs(full_path)
                        except Exception as e:
                            return {'return':1, 'error':f'Failed to create directory: {e}'}

                # Reindex
                add_repo_paths_to_index.append(path)

                reindex = True

#                    # Add to index
#                    p = {'category': state['category'], 
#                         'command': 'create',
#                         'arg1': final_repo_name,
#                         'meta': {'method':method, '_cmr':repo_meta},
#                         'virtual': True,
#                         'path': path,
#                         'con': con}
#
#                    r = self.cm.access(p)
#                    if r['return']>0: return r



            if con:
                r = self.cm.utils.sys.get_disk_space(path=path, nice=True, unit='GB')
                if r['return']>0: return r

                nice_free = r['nice_free']

                print ('')
                print (f'Free space in this repo: {nice_free}')

        ######################################################################################################################
        if reindex:
            # Reindex
            if con:
                print('')

            r = self.cm.repos.index(clean=False, con=con, verbose=verbose, add_repo_paths = add_repo_paths_to_index)
            if r['return']>0: return r

        return {'return':0}


    ###############################################################################################
    def list__(self, params):
        """
        List cMeta repositories

        @base.list_
        """

        # p will be deep copied from params
        p = self._prepare_input_from_params(params, base = True)

        p['sort'] = False

        result = self.cm.access(p)

        return result

    ###############################################################################################
    def create(self, params):
        """
        Create local cMeta repository

        @self.get_
        """

        return self.get_(**params, local=True)


    ###############################################################################################
    def update__(self, params):
        """
        Update cMeta Git repositories

        @self.get_
        """

        return self.get_(**params, update=True)


    ###############################################################################################
    def find(self, params):
        """
        Find cMeta repositories

        @base.find_
        """

        # p will be deep copied from params
        p = self._prepare_input_from_params(params, base = True)

        p['sort'] = False

        result = self.cm.access(p)

        return result

    ###############################################################################################
    def delete(self, params):
        """
        Delete cMeta repositories

        @base.delete_

        Args:
            (unplug) (bool): if True, only unregister repository but don't delete!

        """

        state = params['state']
        con = state.get('control',{}).get('con', False)
        verbose = state.get('control',{}).get('verbose', False)

        unplug = params.get('unplug', False)

        # Check if some repos exists
        p = self._prepare_input_from_state(state, base = True)

        p['command'] = 'find'
        p['con'] = False

        if 'arg1' in params:
            p['arg1'] = params['arg1']

        result = self.cm.access(p)
        if result['return']>0: return result

        if unplug:
            result['deleted_artifacts'] = result.pop('artifacts', [])

        else:
            # Attempt to delete allowed ones
            p = self._prepare_input_from_params(params, base = True)

            result = self.cm.access(p)
            if result['return']>0: return result

        deleted_artifacts = result.get('deleted_artifacts', [])

        if len(deleted_artifacts)>0:
            # Delete from the list of repos
            repos_config_path = self.cm.repos_config_path

            delete_repo_paths_from_index = []

            r = utils.files.safe_read_file(repos_config_path, lock=True, keep_locked=True, fail_on_error=self.fail_on_error, logger=self.logger)
            if r['return']>0: return r

            repos_paths = r['data']
            repos_paths_file_lock = r['file_lock']
            
            for deleted_artifact in deleted_artifacts:
                path = deleted_artifact['path']
                if path in repos_paths:
                    del(repos_paths[path])

                delete_repo_paths_from_index.append(path)

            # Do not sort keys - preserve order
            r = utils.files.safe_write_file(repos_config_path, repos_paths, file_lock=repos_paths_file_lock, atomic=True, 
                                            fail_on_error=self.fail_on_error, logger=self.logger, sort_keys=False)
            if r['return']>0: return r

            # Reindex
            if con:
                print('')

            r = self.cm.repos.index(clean=False, con=con, verbose=verbose, delete_repo_paths = delete_repo_paths_from_index)
            if r['return']>0: return r

        return result


    ###############################################################################################
    def move(self, params):
        """
        Move cMeta repositories - not supported
        """

        return {'return':1, 'error':'moving/renaming repositories is not supported'}


    ###############################################################################################
    def get_alias_from_url_(self, state, arg1):
        """
        Get alias from URL
        """

        url = arg1

        # Get alias from URL
        alias = url

        # Check if zip file
        j = alias.find('.zip')
        if j > 0:
            j1 = alias.rfind('/')
            if j1>0:
                alias = alias[j1+1:j]
            else:
                alias = alias[:-4]
        else:
            if alias.endswith('.git'):
                alias = alias[:-4]

            if alias.startswith('git@'):
                j = alias.find(':')
                if j >= 0:
                    alias = alias[j+1:].replace('/', '@')
            else:
                j = alias.find('//')
                if j >= 0:
                    j1 = alias.find('/', j+2)
                    if j1 >= 0:
                        alias = alias[j1+1:].replace('/', '@')

        if alias == url:
            return {'return':1, 'error':f'Couldn\'t detect repo name in "{url}"'}

        return {'return':0, 'alias':alias}


    ###############################################################################################
    def status(self, params):
        """
        Update cMeta Git repositories

        @self.get_
        """

        return self.get_(**params, status=True)

    ###############################################################################################
    def pull(self, params):
        """
        Pull cMeta Git repositories

        @self.get_
        """

        return self.get_(**params)

    ###############################################################################################
    def clone(self, params):
        """
        Clone cMeta Git repositories

        @self.get_
        """

        return self.get_(**params)

    ###############################################################################################
    def checkout(self, params):
        """
        Checkout cMeta Git repositories

        @self.get_
        """

        if 'arg2' not in params:
            return {'return':1, 'error': 'checkout name is not specified in arg2'}

        import copy
        copy_params = params.copy()

        checkout = copy_params.pop('arg2')

        return self.get_(**copy_params, update=True, checkout = checkout)

    ###############################################################################################
    def clone(self, params):
        """
        Clone cMeta Git repositories

        @self.get_
        """

        return self.get_(**params, method='git')

    ###############################################################################################
    def init(self, params):
        """
        Init local cMeta repository

        @self.get_
        """

        return self.get_(**params, method='local')

    ###############################################################################################
    def unzip(self, params):
        """
        Unzip local cMeta repository

        @self.get_
        """

        import copy
        copy_params = params.copy()

        zip_file = copy_params.pop('arg1')

        return self.get_(**copy_params, zip_file=zip_file, method='local_zip')


    ###############################################################################################
    def zip_(
            self,
            state:                  dict,                # cMeta state.
            arg1:                   str,                 # Repo name (alias and/or UID).
            skip_date:              bool = False,        # Skip date and time from filename
            skip_dirs:              list = None,         # Directories to skip (default: ['.venv', '__pycache__'])
            output_path:            str = None,          # Output path for zip file (current directory by default)
    ):
        """
        Zip cMeta repository.

        Args:
          state (dict): cMeta state
          arg1 (str): repository name (alias and/or UID)
          skip_date (bool): if True, skip date and time from filename
          skip_dirs (list): directories to skip from zipping
          output_path (str): output path for zip file

        Returns:
          (CM return dict):

          * return (int): return code == 0 if no error and >0 if error
          * (error) (str): error string if return>0
          * (zip_path) (str): path to created zip file
        """

        con = state.get('control',{}).get('con', False)
        
        if skip_dirs is None:
            skip_dirs = ['.venv', '__pycache__']

        # Find the repository
        p = {'category': state['category'], 
             'command': 'find',
             'arg1': arg1,
             'sort': False,
             'base': True}

        r = self.cm.access(p)
        if r['return']>0: return r

        repo_artifacts = r.get('artifacts',[])
        
        if len(repo_artifacts) == 0:
            return {'return':1, 'error':f'repository {arg1} not found'}
        
        if len(repo_artifacts) > 1:
            return {'return':1, 'error':f'multiple repositories found for {arg1}, please specify exact name'}

        repo = repo_artifacts[0]
        repo_path = repo['path']
        repo_meta = repo['cmeta']
        repo_cmeta_ref_parts = repo['cmeta_ref_parts']
        repo_alias = repo_cmeta_ref_parts.get('artifact_alias', '')
        repo_uid = repo_cmeta_ref_parts['artifact_uid']

        # Generate repo name for filename
        repo_name = repo_alias if repo_alias else repo_uid

        # Generate filename
        if skip_date:
            zip_filename = f'cmr-{repo_name}.zip'
        else:
            now = datetime.now()
            date_str = now.strftime('%Y%m%d')
            time_str = now.strftime('%H%M%S')
            zip_filename = f'cmr-{repo_name}-{date_str}-{time_str}.zip'

        # Determine output path
        if output_path is None:
            output_path = os.getcwd()
        
        zip_path = os.path.join(output_path, zip_filename)

        if con:
            print('')
            print(f'Zipping repository {repo_name} from {repo_path}')
            print(f'Output file: {zip_path}')
            if skip_dirs:
                print(f'Skipping directories: {", ".join(skip_dirs)}')

        # Zip the directory
        r = utils.files.zip_directory(
            repo_path,
            zip_path,
            skip_directories=skip_dirs,
            fail_on_error=self.fail_on_error
        )
        if r['return']>0: return r

        if con:
            print(f'Repository successfully zipped to: {zip_path}')

        return {'return':0, 'zip_path': zip_path}

    ###############################################################################################
    def plug(self, params):
        """
        Plug local cMeta repository 
        If arg1 is None, use current directory
        If arg1 is not None:
           If existing path -> use that path
           If path does't exist, use as alias


        @self.get_
        """

        arg1 = params.get('arg1', None)

        if arg1 == '' or arg1 == '.':
            arg1 = os.getcwd()

        else:
            arg1 = os.path.abspath(os.path.normpath(arg1))

        p = params.copy()
        p['arg1'] = None
        p['local'] = True
        p['path'] = arg1

        return self.get_(**p)

    ###############################################################################################
    def unplug(self, params):
        """
        UnPlug local cMeta repository 
        If arg1 is None, use current directory
        If arg1 is not None:
           If existing path -> use that path
           If path does't exist, use as alias

        @self.delete
        """

        arg1 = params.get('arg1', None)
        if arg1 is None:
            return {'return':1, 'error':'repo name is not specified'}

        p = params.copy()
        p['unplug'] = True

        return self.delete(p)

    ###############################################################################################
    def space(self, params):
        """
        Get space of a give repo
        @self.find
        """

        state = params['state']
        con = state.get('control',{}).get('con', False)

        # Check if some repos exists
        p = self._prepare_input_from_state(state, base = True)

        p['command'] = 'find'
        p['con'] = False

        if 'arg1' in params:
            p['arg1'] = params['arg1']

        result = self.cm.access(p)
        if result['return']>0: return result

        artifacts = result['artifacts']

        if len(artifacts)>0 and con:
            print ('Free disk space for cMeta repositories:')
            print ('')

        for artifact in artifacts:
            repo_path = artifact['path']

            if os.path.isdir(repo_path):
                cmeta_ref_parts = artifact['cmeta_ref_parts']

                repo_alias = cmeta_ref_parts['artifact_alias']

                r = self.cm.utils.sys.get_disk_space(path=repo_path, nice=True, unit='GB')
                if r['return']>0: return r

                artifact['space_info'] = r

                nice_free = r['nice_free']

                if con:
                    x = f'{repo_alias} ({repo_path}): {nice_free}'
                    print (x)


        return result
