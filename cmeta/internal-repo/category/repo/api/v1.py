"""
CMeta repo functions

cMeta author and developer: (C) 2025 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
from cmeta.category import InitCategory

from cmeta import utils

class Category(InitCategory):
    """
    Various Utils
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path = __file__, **kwargs)




    ############################################################
    def get_(
            self, 
            state:                  dict,                       # cMeta state.
            arg1:                   str | None = None,          # Repo name (alias and/or UID).
            url:                    str | None = None,
            path:                   str | None = None,
            folder:                 str | None = None,          # Force this folder to store repository
            method:                 str | None = None,          # Method (git, zip) - will be detected automatically if not specified
            meta:                   dict | None = None,         # Repo meta data 

            desc:                   str | None = None,
            prefix:                 str | None = None,
            pat:                    str | None = None,
            extra_cmd_git:          str | None = None,
            extra_cmd_pip:          str | None = None,
            checkout_only:          bool = False,
            skip_parent_dir_in_zip: bool = False,
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

        repos_path = self.cm.repos_path
        repos_config_path = self.cm.repos_config_path

        cur_dir = os.getcwd()

        # Process arg1 and URL to extract repo name and understand what to do with repositories ...
        repo_name = None
        repo_alias = None
        repo_uid = None
        folder = None

        if (url is not None and url != ''):
            repo_name = arg1
        else:
            if arg1 is not None and not (arg1.startswith('https://') or arg1.startswith('git@')):
                repo_name = arg1
            else:
                url = arg1

        # Search for an artifact
        repo_artifacts = []

        search = False

        if (repo_name is not None and repo_name != '') or (path is None and url is None):
            # Call base find function to find an artifact with a website
            p = {'category':state['category'], 
                 'command':'find',
                 'sort':False,
                 'base':True}

            if repo_name is not None:
                p['arg1'] = repo_name

            r = self.cm.access(p)
            if r['return']>0 and r['return']!=16: return r

            repo_artifacts = r.get('artifacts',[])

        if len(repo_artifacts)>0:
            # If some repos are already registered
            # try to update them (pull/checkout/branch if git)
            for repo in repo_artifacts:
                print (repo['path'])
            


        else:
            # It's a new repo
            if path is None or path == '':
                # Need to figure out path

                if repo_name is not None and repo_name != '':
                    # Spread into alias and UID
                    r = utils.names.parse_cmeta_name(repo_name)
                    if r['return']>0: return r

                    repo_alias = r.get('name',{}).get('alias')
                    repo_uid = r.get('name',{}).get('uid')

                    if url is None or url == '':
                        if '@' not in repo_alias:
                            repo_alias = self.cm.cfg['default_git_repo'] + '@' + repo_alias

                        url = self.cm.cfg['default_git'] + '/' + repo_alias.replace('@','/')

                    folder = repo_alias if repo_alias is not None else repo_uid

                else:
                    r = self.get_alias_from_url_(state, url)
                    if r['return']>0: return r

                    repo_alias = r['alias']
                    folder = repo_alias
                    
                path = os.path.join(repos_path, folder)

            # Check method
            if not method and url:
                if url.endswith('.zip'):
                    method = 'zip'
                else:
                    method = 'git'

            print (method)
            print (repo_alias)
            print (url)
            print (path)


            # Check what to do depending on whether the path exists or not
            if not os.path.isdir(path):
                if method == 'git':
                    cmd = f'git clone "{url}" "{path}"'
                    if con:
                        print ('')
                        print ('cd ' + os.getcwd())
                        print (cmd)
                        print ('')
                    ec = os.system(cmd)
                    if ec != 0:
                        return {'return':1, 'error':f'"System command {cmd}" failed with exit code {ec}'}


                # Check if repository was created
                if os.path.isdir(path):
                    # Append to the list of repos
                    r = utils.files.safe_read_file(repos_config_path, lock=True, keep_locked=True, fail_on_error=self.fail_on_error, logger=self.logger)
                    if r['return']>0: return r

                    repos_paths = r['data']
                    repos_paths_file_lock = r['file_lock']
                    
                    if path not in repos_paths:
                        repos_paths.append(path)

                    r = utils.files.safe_write_file(repos_config_path, repos_paths, file_lock=repos_paths_file_lock, atomic=True, fail_on_error=self.fail_on_error, logger=self.logger)
                    if r['return']>0: return r

                    # Try to read _cmr.yaml or create it (if already exists, to get correct artifact name and UID)
                    repo_meta_desc_path = os.path.join(path, self.cm.cfg['repo_meta_desc'])

                    repo_meta = {}
                    repo_meta_file_lock = None
                    repo_updated = False

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

                    final_repo_name = repo_meta.get('artifact')
                    if final_repo_name is None or final_repo_name == '':
                        final_repo_name = ''
                        if repo_alias != '': 
                            final_repo_name = repo_alias + ','
                        if repo_uid == None or repo_uid == '':
                            repo_uid = utils.names.generate_cmeta_uid()
                        final_repo_name += repo_uid

                        repo_meta['artifact'] = final_repo_name

                        repo_update = True

                    if repo_updated:
                        r = utils.files.safe_write_file(repo_meta_desc_path, repo_meta, file_lock=repo_meta_file_lock, atomic=True, fail_on_error=self.fail_on_error, logger=self.logger)
                        if r['return']>0: return r
                    elif repo_meta_file_lock is not None:
                        r = utils.files.unlock_path(repo_meta_desc_path, file_lock=repo_meta_file_lock, fail_on_error=self.fail_on_error, logger=self.logger)
                        if r['return']>0: return r

                    # Add to index
                    p = {'category': state['category'], 
                         'command': 'create',
                         'arg1': final_repo_name,
                         'meta': {'method':method, '_cmr':repo_meta},
                         'virtual': True,
                         'path': path,
                         'con': con}

                    r = self.cm.access(p)
                    if r['return']>0: return r


            else:
                if method == 'git':
                    os.chdir(path)
                    cmd = f'git pull'
                    c = os.system(cmd)
                    print (c)
                    os.chdir(cur_dir)



        return {'return':0}


    def list__(self, params):
        """
        List cMeta repositories

        @base.list_
        """

        params_copy = params.copy()
        params_copy['sort'] = False

        p = self._prepare_input_from_params(params_copy, base = True)

        result = self.cm.access(p)

        return result

    def find(self, params):
        """
        Find cMeta repositories

        @base.find_
        """


        params_copy = params.copy()
        params_copy['sort'] = False

        p = self._prepare_input_from_params(params_copy, base = True)

        result = self.cm.access(p)

        return result

    def delete(self, params):
        """
        Delete cMeta repositories

        @base.delete_
        """

        params_copy = params.copy()

        p = self._prepare_input_from_params(params_copy, base = True)

        result = self.cm.access(p)

        return result


    def reindex(self, params):
        """
        ReIndex repos

        @base.index_
        """

        p = self._prepare_input_from_params(params)

        p['command'] = 'index'
        p['clean'] = True

        return self.cm.access(p)

    def index_(self, state, arg1=None, clean=False):
        """
        Index repos
        """

        con = state['control'].get('con', False)

        return self.cm.repos.reindex(con=con)


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


    ############################################################
    def status_(
            self, 
            state:                  dict,                       # cMeta state.
            arg1:                   str | None = None,          # Repo name (alias and/or UID).
    ):

        """
        Print status of repositories.

        """

        con = state.get('control',{}).get('con', False)


        return {'return':0}
    