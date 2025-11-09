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

        cur_dir = os.getcwd()

        # Process arg1 and URL to extract repo name and understand what to do with repositories ...
        repo_name = None
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




# Check if can get self category name with UID

            p = {'category':'repo', 
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

                    folder = repo_alias if repo_alias is not None else repo_uid

                    if url is None or url == '':
                        repo_split = repo_alias.split('@')

                        if len(repo_split)==1:
                            url = self.cm.cfg['default_git_with_repo']
                            url += '/' + repo_split[0]
                        else:
                            url = self.cm.cfg['default_git']
                            url += '/' + '/'.join(repo_split)

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
                    c = os.system(cmd)
                    print (c)

                    if c == 0:
                        p = {'category':'repo', 
                             'command':'create',
                             'arg1':repo_alias,
                             'con':True,
                             'base':True}

                        r = self.cm.access(p)
                        if r['return']>0: return r


            else:
                if method == 'git':
                    os.chdir(path)
                    cmd = f'git pull'
                    c = os.system(cmd)
                    print (c)
                    os.chdir(cur_dir)


            input('xyz')


        return {'return':0}


        skip_zip_parent_dir = skip_parent_dir_in_zip

        dir2 = i.get('dir2', '')
        if dir2 != '':
            i['dir'] = dir2 + '/' + dir2
            del (i['dir2'])

        # Check alias is URL
        if url == '' and (alias.startswith('https://') or alias.startswith('git@')):
            url = alias
            alias = ''

        # Process URL and alias
        if url == '':
            if alias != '':
                url = self.cmind.cfg['repo_url_prefix']

                if '@' not in alias:
                    alias = self.cmind.cfg['repo_url_org'] + '@' + alias

                url += alias.replace('@', '/')

        else:
            if alias == '':
                # Get alias from URL
                alias = url

                # Check if zip file
                j = alias.find('.zip')
                if j > 0:
                    j1 = alias.rfind('/')
                    alias = alias[j1+1:j+4]
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

        if pat != '' and url != '' and url.startswith('https://'):
            patx = pat
            urlx = url[8:]

            j = urlx.find('@')
            if j > 0:
                username = urlx[:j]
                patx = username + ':' + pat
                urlx = urlx[j+1:]

            url = url[:8] + patx + '@' + urlx

        if url == '':
            pull_repos = []

            for repo in sorted(self.cmind.repos.lst, key=lambda x: x.meta.get('alias', '')):
                meta = repo.meta

                if meta.get('git', False):
                    # Note that internal repo alias may not be the same as the real pulled alias since it can be a fork
                    # Pick it up from the path

                    repo_path = repo.path

                    pull_repos.append({'alias': os.path.basename(repo_path),
                                       'path_to_repo': repo_path})
        else:
            # Migration has been completed
            branch = i.get('branch', '')
            new_branch = i.get('new_branch', '')
            checkout = i.get('checkout', '')
            _dir = i.get('dir', '')

            if alias == 'mlcommons@ck' and branch == '' and checkout == '' and _dir == '':
                print(
                    '=========================================================================')
                print(
                    'Warning: mlcommons@ck was automatically changed to mlcommons@cm4mlops.')
                print(
                    'If you want to use older mlcommons@ck repository, use branch or checkout.')
                print(
                    '=========================================================================')

                alias = 'mlcommons@cm4mlops'
                url = url.replace('mlcommons/ck', 'mlcommons/cm4mlops')

            pull_repos = [{'alias': alias,
                           'url': url,
                           'branch': branch,
                           'new_branch': new_branch,
                           'checkout': checkout,
                           'dir': _dir,
                           'depth': i.get('depth', '')}]

        # Go through repositories and pull
        repo_meta = {}
        repo_metas = {}

        warnings = []

#        if not self.cmind.xlogger == None:
#            self.cmind.log(f"x repo log: {pull_repos}", "debug")

        for repo in pull_repos:
            alias = repo['alias']
            url = repo.get('url', '')
            branch = repo.get('branch', '')
            new_branch = repo.get('new_branch', '')
            checkout = repo.get('checkout', '')
            depth = repo.get('depth', '')
            path_to_repo = repo.get('path_to_repo', None)
            _dir = repo.get('dir', '')

            if con:
                print(self.cmind.cfg['line'])
                print('Alias:      {}'.format(alias))
                if url != '':
                    print('URL:        {}'.format(url))
                if branch != '':
                    print('Branch:     {}'.format(branch))
                if new_branch != '':
                    print('New branch: {}'.format(new_branch))
                if checkout != '':
                    print('Checkout:   {}'.format(checkout))
                if _dir != '':
                    print('Directory:  {}'.format(_dir))
                if depth != '' and depth != None:
                    print('Depth:      {}'.format(str(depth)))
                print('')

            # Prepare path to repo
            repos = self.cmind.repos

            r = repos.pull(alias=alias,
                           url=url,
                           branch=branch,
                           new_branch=new_branch,
                           checkout=checkout,
                           _dir=_dir,
                           con=con,
                           desc=desc,
                           prefix=prefix,
                           depth=depth,
                           path_to_repo=path_to_repo,
                           checkout_only=checkout_only,
                           skip_zip_parent_dir=skip_zip_parent_dir,
                           extra_cmd_git=extra_cmd_git,
                           extra_cmd_pip=extra_cmd_pip)
            if r['return'] > 0:
                return r

            repo_meta = r['meta']

            repo_metas[alias] = repo_meta

            if len(r.get('warnings', [])) > 0:
                warnings += r['warnings']

        if len(pull_repos) > 0 and self.cmind.use_index:
            if con:
                print(self.cmind.cfg['line'])

            ii = {'out': 'con'} if con else {}
            rx = self.reindex(ii)

        print_warnings(warnings)

        return {'return': 0, 'meta': repo_meta, 'metas': repo_metas}
















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
