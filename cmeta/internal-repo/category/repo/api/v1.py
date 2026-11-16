"""
cMeta repo functions

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import json
import os
import shutil
import subprocess
import sys
from cmeta.category import InitCategory

from cmeta import utils
from datetime import datetime

from . import common

class Category(InitCategory):
    """
    Various Utils
    """

    def __init__(
        self,
        *args,  # Positional argument value.
        **kwargs,  # Value for kwargs.
    ):
        """
        __init__ function.

        Args:
            *args: Positional argument value.
            **kwargs: Value for kwargs.

        Returns:
            dict: Operation result.

        Raises:
            Exception: Propagated runtime errors, if any.
        """
        super().__init__(*args, module_file_path = __file__, **kwargs)


    ###############################################################################################
    def get_(
        self,
        ctx: dict,  # cMeta context.
        arg1: str = None,  # Repo alias or UID.
        url: str = None,  # Source URL for git or zip repositories.
        path: str = None,  # Target path for repository checkout.
        folder: str = None,  # Folder name under repos root when `path` is not set.
        subdir: str = None,  # Optional repository subdirectory to use.
        method: str = None,  # Retrieval method (`git`, `zip`, or `local`).
        local: bool = False,  # If True, force local method.
        meta: dict = None,  # Metadata to merge into repository cmeta.
        update: bool = False,  # If True, update existing repository.
        status: bool = False,  # If True, only query git status.
        checkout: str = None,  # Branch, tag, or commit to checkout.
        depth: int = None,  # Shallow git clone: fetch only the last N commits (a branch, a tag or a full SHA with --checkout).
        keep: bool = False,  # If True, keep existing repo metadata on reindex.
        pre: str = '',  # Command to run before repository retrieval.
        post: str = '',  # Command to run after repository retrieval.
        hide: bool = False,  # If True, hide sensitive command output.
        skip_parent_dir_in_zip: bool = False,  # If True, skip parent directory in zip extraction.
        zip_file: str = None,  # Path to a local zip file to import.
        identity: str = None,  # The identity of the clone: a secret alias (cx secret: kind git or ssh for a git clone, a token for hf://), <category>::<artifact>/<key or token file>, or the file's path.
    ):
        """
            Clone or pull CM repository.

            Args:
                                ctx (dict): cMeta context.
                                arg1 (str): Repo alias or UID.
                                url (str): Source URL for git or zip repositories.
                                path (str): Target path for repository checkout.
                                folder (str): Folder name under repos root when `path` is not set.
                                subdir (str): Optional repository subdirectory to use.
                                method (str): Retrieval method (`git`, `zip`, or `local`).
                                local (bool): If True, force local method.
                                meta (dict): Metadata to merge into repository cmeta.
                                update (bool): If True, update existing repository.
                                status (bool): If True, only query git status.
                                checkout (str): Branch, tag, or commit to checkout.
                                depth (int): Shallow git clone with only the last N commits - no older history is
                                    downloaded. With --checkout, a branch or a tag is cloned directly and a commit
                                    (full SHA) is fetched after the clone. A later pull keeps a shallow clone shallow,
                                    and a checkout of a ref that is not there yet fetches it at the same depth.
                                keep (bool): If True, keep existing repo metadata on reindex.
                                pre (str): Command to run before repository retrieval.
                                post (str): Command to run after repository retrieval.
                                hide (bool): If True, hide sensitive command output.
                                skip_parent_dir_in_zip (bool): If True, skip parent directory in zip extraction.
                                zip_file (str): Path to a local zip file to import.
                                identity (str): The git identity the clone is given and keeps: the alias of a
                                    secret of kind git or ssh (the secret category of cmeta-aops: name, e-mail,
                                    the transport key, the signing key), a cMeta reference
                                    <category>::<artifact>/<file> to a key file inside an artifact, or a path to
                                    a key file. The clone runs with that key (GIT_SSH_COMMAND), the settings are
                                    written into the clone's own git configuration (git config --local), and the
                                    identity's name is kept in the repository's registration on this machine
                                    (never in the shared _cmr.yaml). On an existing clone the identity is
                                    (re)applied before the pull. Nothing of a key's content is printed or stored.
                                    For a repository of the Hugging Face Hub (hf://<owner>/<name>, or a clone
                                    pulled from it), the identity is where its access token comes from: the alias
                                    of a token secret (its value opened by cx secret call at the fetch, never
                                    returned), <category>::<artifact>/<token file>, or a token file; without it,
                                    the token of this machine (HF_TOKEN, the hf login) when there is one. The
                                    name is kept the same way and used by every later pull of that clone.

            Returns:
              (CM return dict):

              * return (int): return code == 0 if no error and >0 if error
              * (error) (str): error string if return>0
              * (failed) (list): the repositories an update could not update ({repo, path, error}): every
                    repository is tried, and the command fails at the end, after the reindex, when this is not empty
              * (nothing_to_pull) (list): the clones a pull found nothing to pull from ({repo, path, why}: no
                    remote, a detached HEAD, a branch without an upstream, a remote without any commit yet)

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        con = ctx.get('control',{}).get('con', False)
        verbose = ctx.get('control',{}).get('verbose', False)

        # meta takes keys: a text ("--meta=@file.yaml" reads no file) is refused before anything is fetched or locked
        meta, r = utils.cli.keys_param('meta', meta, None)
        if r: return r

        if depth is not None and depth != '':
            try:
                depth = int(depth)
            except (TypeError, ValueError):
                depth = 0
            if depth < 1:
                return {'return':1, 'error':'--depth must be a positive number of commits'}
        else:
            depth = None

        # --identity: resolved below, once the repository is known - as a git identity, or as the token of a
        # repository of the Hugging Face Hub - and before anything is cloned or pulled, so that a wrong name
        # leaves nothing behind
        ident_pairs, ident_env, ident_name, ident_hf = [], {}, '', None

        repos_path = self.cm.repos_path
        repos_config_path = self.cm.repos_config_path

        command = ctx['command']

        cur_dir = os.getcwd()

        # Get default config
        r = self.cm.access({'category': self.cmeta['uses_categories']['config'],
                            'command': 'get',
                            'arg1': self.cm.cfg['default_config_name']})
        if r['return'] > 0: return r

        config_cmeta = r['config_cmeta']

        # Process arg1 and URL to extract repo name and understand what to do with repositories ...
        repo_name = None
        repo_alias = None
        repo_uid = None

        if (url is not None and url != ''):
            repo_name = arg1
        else:
            if arg1 and arg1.startswith('cmeta://'):
                default_cmeta_repo_url = config_cmeta.get('default_cmeta_repo_url')
                if not default_cmeta_repo_url:
                    default_cmeta_repo_url = self.cm.cfg['default_cmeta_repo_url']

                if not repo_name:
                    repo_name = arg1[8:]

                url = default_cmeta_repo_url + repo_name + '-'

                if checkout:
                    url += checkout
                else:
                    url += 'last'

                url += '.zip'

            elif arg1 is not None and not (arg1.startswith('https://') or arg1.startswith('git@') or arg1.startswith('hf://')):
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

        # Each repository is tried - a failure never stops the others -, and the command fails at the end, after
        # the reindex, naming the ones it could not update; a clone with nothing to pull from is not a failure
        failed = []
        nothing_to_pull = []
        tried = 0


        ######################################################################################################################
        if repo_name is None and url is not None and url!='':
            if path is None or path == '':
                # Try to check if repo with this url is already registered
                r = self.get_alias_from_url_(ctx, url)
                if r['return']>0: return r

                xalias = r['alias']
                xpath = os.path.join(repos_path, xalias)
            else:
                xpath = path

            if os.path.isdir(xpath):
                xpath_to_repo_desc = os.path.join(xpath, self.cm.cfg['repo_meta_desc'])

                if os.path.isfile(xpath_to_repo_desc):
                    r = utils.files.safe_read_file(xpath_to_repo_desc, retry_if_not_found=3, fail_on_error=self.fail_on_error, logger=self.logger)
                    if r['return']==0: 
                        xrepo_meta = r['data']
                        repo_name = xrepo_meta.get('artifact', '')

        ######################################################################################################################
        if (repo_name is not None and repo_name != '') or (path is None and url is None and zip_file is None):
            # Call base find function to find an artifact
            p = {'category':ctx['category'], 
                 'command':'find',
                 'sort':False,
                 'base':True}

            if repo_name is not None:
                p['arg1'] = repo_name

            r = self.cm.access(p)
            if r['return']>0 and r['return']!=16: return r

            repo_artifacts = r.get('artifacts',[])

            # A short name ("cmeta-aops") becomes the alias "<default_git_repo>@<name>" when it is
            # cloned (below). Look that alias up too, so that "cx repo pull <name>" and a second
            # "cx repo get <name>" update the clone instead of trying to clone it again
            if len(repo_artifacts) == 0 and command != 'init' and repo_name and \
               (url is None or url == '') and zip_file is None and method != 'local' and \
               not any(c in repo_name for c in '@*?,:'):
                default_git_repo = config_cmeta.get('default_git_repo')
                if not default_git_repo:
                    default_git_repo = self.cm.cfg['default_git_repo']

                p['arg1'] = default_git_repo + '@' + repo_name

                r = self.cm.access(p)
                if r['return']>0 and r['return']!=16: return r

                repo_artifacts = r.get('artifacts',[])

        ######################################################################################################################
        # --identity, resolved before anything is cloned or pulled (a wrong name leaves nothing behind): the token
        # of a repository of the Hugging Face Hub (an hf:// URL, or a clone pulled from the Hub), else a git identity
        if identity is not None and str(identity).strip() != '':
            hub = bool(url and utils.net.hf_repo(url))
            if not hub and len(repo_artifacts) == 1:
                a = repo_artifacts[0]
                hub = (a.get('cmeta') or {}).get('method') == 'hf' or \
                      os.path.isfile(os.path.join(a.get('path', ''), utils.net.HF_RECORD))
            if hub:
                r = self._hf_identity(identity)
                if r['return']>0: return r

                ident_hf, ident_name = r['source'], r['name']
            else:
                r = self._git_identity(identity)
                if r['return']>0: return r

                ident_pairs, ident_env, ident_name = r['pairs'], r['env'], r['name']

        ######################################################################################################################
        if len(repo_artifacts)>0:
            # If some rep   os are already registered
            # try to update them (pull/checkout/branch if git)

            if command in ['init']:
                return {'return':1, 'error':f'repository {arg1} already exists'}

            # --identity belongs to ONE repository: never written into every clone a pull-all or a pattern finds
            if ident_name and len(repo_artifacts) > 1:
                return {'return':1, 'error':f'--identity is given to one repository: name it ({len(repo_artifacts)} match'
                                            f'{"" if repo_name else " a pull of every repository"})'}

            # No name: every git repository is about to be updated. Ask first in a terminal
            # (Enter means yes); --quiet (-q), a script or a pipe goes ahead without asking
            if (repo_name is None or repo_name == '') and not status and con and \
               not ctx['control'].get('quiet', False) and sys.stdin is not None and sys.stdin.isatty():
                git_repos = [a['cmeta_ref_parts'].get('artifact_alias', a['cmeta_ref_parts'].get('artifact_uid'))
                             for a in repo_artifacts if (a.get('cmeta') or {}).get('method') == 'git']

                if len(git_repos) > 0:
                    print (f'This updates all {len(git_repos)} git repositories: {", ".join(git_repos)}')
                    x = input('Continue [Y/n]? ').strip().lower()

                    if x not in ['', 'y', 'yes']:
                        print ('Nothing updated.')
                        return {'return':0, 'skipped': True}

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
                if not xmethod and os.path.isfile(os.path.join(repo_path, utils.net.HF_RECORD)):
                    xmethod = 'hf'              # pulled from the Hugging Face Hub (the index tells git clones alone)

                if repo_path not in repos_paths:
                    caller = ctx.get('origin',{}).get('cli',{}).get('caller','')
                    return {'return':1, 'error':f'File {repos_config_path} may be corrupted - it doesn\'t contain {repo_path}! Try "{caller} --reindex"'}

                if os.path.isdir(repo_path):
                    if con:
                        print ('='*80)
                        print (f'{repo_alias} ({repo_uid}): {repo_path}')

                    if xmethod == 'hf':
                        # A repository of the Hugging Face Hub: brought up to date by its API from the record the
                        # first pull left in the folder (.cmeta-hf.json); --checkout takes another revision
                        tried += 1
                        hf_record = {}
                        try:
                            with open(os.path.join(repo_path, utils.net.HF_RECORD), encoding = 'utf-8') as f:
                                hf_record = json.load(f)
                        except (OSError, ValueError):
                            pass
                        if not hf_record.get('repo'):
                            failed.append({'repo':repo_alias, 'path':repo_path, 'error':f'no {utils.net.HF_RECORD} in the folder: which repository of the Hub it came from is not known - pull it again with its hf:// name into a new folder'})
                            continue
                        if status:
                            print ('')
                            print (f'Hugging Face: {hf_record.get("type", "dataset")} {hf_record["repo"]}, revision {hf_record.get("revision", "main")}, commit {str(hf_record.get("commit") or "")[:8]}, synced {hf_record.get("synced", "?")}')
                            if repo_meta.get('identity'):
                                print (f'Identity: {repo_meta["identity"]} (given with cx repo pull --identity)')
                            continue

                        # --identity on an existing clone: remembered in its registration, used by this pull and the
                        # next ones; without it, the identity the clone was given before
                        source = ident_hf
                        if ident_name:
                            r = self._record_identity(repos_config_path, repo_path, ident_name)
                            if r['return']>0: return r
                        elif repo_meta.get('identity'):
                            r = self._hf_identity(repo_meta['identity'])
                            if r['return']>0:
                                failed.append({'repo':repo_alias, 'path':repo_path, 'error':r.get('error', '')})
                                continue
                            source = r['source']

                        r = self._hf_pull(ctx, source, hf_record['repo'], hf_record.get('type', 'dataset'),
                                          checkout or hf_record.get('revision', 'main'), repo_path, con)
                        if r['return'] > 0:
                            failed.append({'repo':repo_alias, 'path':repo_path, 'error':r.get('error', '')})
                            continue
                        if r['downloaded'] == 0 and r['removed'] == 0:
                            nothing_to_pull.append({'repo':repo_alias, 'path':repo_path, 'why':'up to date'})
                        if con:
                            print (f'cMeta info: {hf_record["repo"]}: {r["files"]} files, {r["downloaded"]} downloaded, {r["removed"]} removed (commit {str(r.get("commit") or "")[:8]})')
                        if r['removed'] > 0:
                            # An artifact the repository dropped keeps its record in an incremental index: the
                            # repository is indexed again from its folder
                            rr = self.cm.access({'category':'repo', 'command':'reindex', 'arg1':repo_path, 'con':False})
                            if rr['return']>0: return rr
                        else:
                            add_repo_paths_to_index.append(repo_path)
                            reindex = True
                        continue

                    if xmethod == 'git':

                        if status:
                            print ('')
                            print ('Checking repository status ...')

                            if repo_meta.get('identity'):
                                print (f'Identity: {repo_meta["identity"]} (given with cx repo pull --identity)')

                            cmds = ['git remote get-url origin', 'git status']

                            for cmd in cmds:

                                r = utils.sys.run(cmd, work_dir=repo_path, con=con, verbose=True)
                                if r['return']>0: return r

                                rc = r['returncode']
                                if rc != 0:
                                    return {'return':1, 'error':f'System command "{cmd}" failed with exit code {rc}'}


                        else:
                            # --identity on an existing clone: written into its configuration before the pull
                            # or the checkout, and remembered in its registration
                            if ident_pairs:
                                if con:
                                    print ('')
                                    print (f'Setting the git identity {ident_name} in {repo_path} ...')

                                r = self._git_config(repo_path, ident_pairs, con)
                                if r['return']>0: return r

                                r = self._record_identity(repos_config_path, repo_path, ident_name)
                                if r['return']>0: return r

                            tried += 1

                            if checkout is not None and checkout != '':
                                if con:
                                    print ('')
                                    print (f'Checking out repository in {repo_path} ...')

                                r = self._git_checkout(repo_path, checkout, depth, con)
                                if r['return']>0:
                                    # one repository: its own error at once, as always; several: the others go on
                                    if len(repo_artifacts) == 1: return r

                                    failed.append({'repo':repo_alias, 'path':repo_path, 'error':r.get('error', '')})

                                    if con:
                                        print (f'cMeta warning: the checkout failed in {repo_alias} - the other repositories go on')

                            else:
                                print ('')
                                print ('Updating git repository ...')

                                # No --depth here even when it is given: a plain "git pull" keeps a shallow
                                # clone shallow (only the new commits are fetched), while "git pull --depth N"
                                # moves the shallow boundary past local commits and git then refuses to merge
                                # them ("refusing to merge unrelated histories")
                                cmd = 'git pull'

                                r = utils.sys.run(cmd, work_dir=repo_path, con=con, env=ident_env)
                                if r['return']>0: return r

                                # A failed pull never stops the others: the command fails at the end with the list.
                                # A clone with nothing to pull from (no remote, a detached HEAD, a branch without an
                                # upstream, a remote without any commit yet) is not a failure
                                rc = r['returncode']
                                if rc != 0:
                                    why = self._nothing_to_pull(repo_path, ident_env)

                                    if why:
                                        nothing_to_pull.append({'repo':repo_alias, 'path':repo_path, 'why':why})

                                        if con:
                                            print (f'cMeta info: nothing to pull in {repo_alias}: {why}')
                                    else:
                                        failed.append({'repo':repo_alias, 'path':repo_path, 'error':f'git pull: exit code {rc}'})

                                        if con:
                                            print (f'cMeta warning: "{cmd}" failed in {repo_alias} with exit code {rc} - the other repositories go on')


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
                                default_git_repo = config_cmeta.get('default_git_repo')
                                if not default_git_repo:
                                    default_git_repo = self.cm.cfg['default_git_repo']

                                repo_alias = default_git_repo + '@' + repo_alias

                            default_git = config_cmeta.get('default_git')
                            if not default_git:
                                default_git = self.cm.cfg['default_git']

                            url = default_git + repo_alias.replace('@','/')

                    if folder is None or folder == '':
                        folder = repo_alias if repo_alias is not None else repo_uid

                elif folder is None or folder == '':
                    r = self.get_alias_from_url_(ctx, url)
                    if r['return']>0: return r

                    repo_alias = r['alias']
                    folder = repo_alias
                else:
                    if repo_alias is None or repo_alias == '':
                        repo_alias = folder

                path = os.path.join(repos_path, folder)

            # Never the folder of the repositories of this home, nor the home itself: a repository there holds every
            # other one. A bare "cx repo plug" typed in ~/CMETA/repos registered that folder as the repository "repos"
            # (a P14s Gen 4, 2026-09-18), and every incremental index of it could take the records of the other
            # repositories out of the index. A folder further up can be a repository of its own that holds the home:
            # a project with its virtual environment inside it (the home <project>/.venv/CMETA)
            if path:
                xpath = os.path.normcase(os.path.abspath(os.path.normpath(str(path))))
                xrepos = os.path.normcase(os.path.abspath(os.path.normpath(str(repos_path))))
                if xpath in (xrepos, os.path.dirname(xrepos)):
                    what = 'the folder of the repositories of this cMeta home' if xpath == xrepos else 'this cMeta home (it holds the folder of the repositories)'
                    return {'return':1, 'error':f'{path} is {what}: a repository there would hold every other one - plug the folder '
                                               f'of one repository ("cx repo plug <folder>"), or make a new one with "cx repo init <name>"'}

            # Check method
            if not method and url:
                if url.endswith('.zip'):
                    method = 'zip'
                elif utils.net.hf_repo(url):
                    method = 'hf'               # a repository of the Hugging Face Hub, by its API (no git, no git-lfs)
                else:
                    method = 'git'

            ######################################################################################################################
            # Check what to do depending on whether the path exists or not
            if os.path.isdir(path) and method != 'local':
                if not self.cm.utils.files.is_dir_empty(path, clean=True):
                    return {'return':1, 'error':f'directory {path} already exists'}

            if not os.path.isdir(path):
                if method == 'git':
                    xpre = '' if pre == '' else ' ' + pre
                    xpost = '' if post == '' else ' ' + post

                    # --depth: a branch or a tag is cloned directly (only that ref, no older history);
                    # a commit is fetched after the clone, since git clone cannot start at a SHA
                    xdepth = ''
                    checkout_after_clone = checkout is not None and checkout != ''
                    if depth:
                        xdepth = f' --depth {depth}'
                        if checkout_after_clone and not self._is_commit_sha(checkout):
                            xdepth += f' --branch {checkout}'
                            checkout_after_clone = False

                    cmd = f'git clone{xdepth}{xpre} "{url}" "{path}"{xpost}'

                    if con:
                        print ('')
                        print (f'Cloning repository in {path} ...')

                    xcon = False if hide else con
                    r = utils.sys.run(cmd, con=xcon, env=ident_env)
                    if r['return']>0: return r

                    rc = r['returncode']
                    if rc != 0:
                        return {'return':1, 'error':f'System command "{cmd}" failed with exit code {rc}'}

                    # --identity: kept by the clone itself (git config --local), so that every later pull, fetch
                    # and commit in it uses it without being told again
                    if ident_pairs:
                        if con:
                            print ('')
                            print (f'Setting the git identity {ident_name} in {path} ...')

                        r = self._git_config(path, ident_pairs, con)
                        if r['return']>0: return r

                    if checkout_after_clone:
                        if con:
                            print ('')
                            print (f'Checking out repository in {path} ...')

                        r = self._git_checkout(path, checkout, depth, con)
                        if r['return']>0: return r
                    

                elif method == 'local_zip':
                    # Unzip with cleaning
                    r = utils.files.unzip(zip_file, path=path, overwrite=False, clean=False, fail_on_error = self.fail_on_error)
                    if r['return'] >0: return r

                elif method == 'zip':

                    # Get default params
                    r = self.cm.access({'category': self.cmeta['uses_categories']['config'],
                                        'command': 'get',
                                        'arg1': 'ctuning_server'})
                    if r['return'] > 0: return r

                    ctuning_server_config_cmeta = r['config_cmeta']

                    api_key = ctuning_server_config_cmeta.get('api_key')
                    skip_ssl_certificate = ctuning_server_config_cmeta.get('skip_ssl_certificate', False)

                    # Download zip
                    r = utils.net.download(url, path = path, show_progress = con, fail_on_error = self.fail_on_error, 
                                           skip_ssl_certificate = skip_ssl_certificate, api_key = api_key)
                    if r['return'] >0: 
                        # Clean path if empty
                        self.cm.utils.files.is_dir_empty(path, clean=True)
                        return r

                    full_path_to_zip_file = r['path']

                    # Unzip with cleaning
                    r = utils.files.unzip(full_path_to_zip_file, path=path, overwrite=False, clean=True, fail_on_error = self.fail_on_error)
                    if r['return'] >0: return r

                elif method == 'hf':
                    # A repository of the Hugging Face Hub: its files at the revision (--checkout) by the Hub's API,
                    # each checked against the digest the Hub names; the record .cmeta-hf.json in the folder keeps
                    # what was fetched, so that the next pull takes the changes alone
                    hf = utils.net.hf_repo(url)
                    r = self._hf_pull(ctx, ident_hf, hf['id'], hf['type'], checkout or hf['revision'], path, con)
                    if r['return'] > 0:
                        self.cm.utils.files.is_dir_empty(path, clean=True)
                        return r
                    if con:
                        print (f'cMeta info: {hf["id"]} ({hf["type"]}, {checkout or hf["revision"]}, commit {str(r.get("commit") or "")[:8]}): '
                               f'{r["files"]} files, {r["downloaded"]} downloaded ({r["bytes"] / 1e6:.1f} MB) in {r["seconds"]:.0f} s')

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

                # the identity's name travels with the registration of this machine, never with _cmr.yaml
                if ident_name and method in ('git', 'hf'):
                    repo_meta_to_index['identity'] = ident_name

                if os.path.isfile(repo_meta_desc_path):
                    r = utils.files.safe_read_file(repo_meta_desc_path, lock=True, keep_locked=True, fail_on_error=self.fail_on_error, logger=self.logger)
                    if r['return']>0: return r

                    repo_meta = r['data']
                    repo_meta_file_lock = r['file_lock']

                if meta is not None and len(meta)>0:
                    repo_meta = utils.common.deep_merge(repo_meta, meta, append_lists=True)
                    repo_updated = True

                if 'category' not in repo_meta:
                    r = utils.names.restore_cmeta_name(ctx['category'], key='artifact')
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

                    # (was "repo_update", a typo: a descriptor with a category but no artifact got its new name in
                    # memory only, and the next index found a repository that "names no artifact")
                    repo_updated = True

                if keep:
                    repo_meta['keep'] = True
                    repo_meta_to_index['keep'] = True

                if repo_updated:
                    if con and not os.path.isfile(repo_meta_desc_path):
                        # A folder without a descriptor becomes a repository: said, not done silently
                        print (f'cMeta info: {path} has no {self.cm.cfg["repo_meta_desc"]}: it becomes the repository "{repo_meta.get("artifact", "")}"')

                    r = utils.files.safe_write_file(repo_meta_desc_path, repo_meta, file_lock=repo_meta_file_lock, atomic=True, fail_on_error=self.fail_on_error, logger=self.logger)
                    if r['return']>0: return r
                elif repo_meta_file_lock is not None:
                    r = utils.files.unlock_path(repo_meta_desc_path, file_lock=repo_meta_file_lock, fail_on_error=self.fail_on_error, logger=self.logger)
                    if r['return']>0: return r

                # Check if repo already registered
                repo_name2 = repo_meta.get('artifact')

                if repo_name2 is not None and repo_name2 != '':
                    # Call base find function to find an artifact with a website
                    p = {'category':ctx['category'], 
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
                    # I decided not to add params to avoid exposing sensitite info such as PAT in URL, 'params':ctx['origin']['params']}}
                    # Unless "keep" is used for USB-like or network drives
                    repos_paths[path] = {'meta':repo_meta_to_index}

                    if keep:
                        repos_paths[path]['keep_repo_meta'] = repo_meta

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
#                    p = {'category': ctx['category'], 
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
                print (f'Free disk space for this repo: {nice_free}')

        ######################################################################################################################
        if reindex:
            # Reindex
            if con:
                print('')

            r = self.cm.repos.index(clean=False, con=con, verbose=verbose, add_repo_paths = add_repo_paths_to_index)
            if r['return']>0: return r

        # Every repository was tried: the command fails now if any of them could not be updated, naming each
        if len(failed) > 0:
            names = ', '.join(f"{x['repo']} ({x['error']})" for x in failed)

            error = f'{len(failed)} of {tried} repositories not updated: {names}'
            if tried > len(failed):
                error += f' - the other {tried - len(failed)} went through'

            return {'return':1, 'error':error, 'failed':failed, 'nothing_to_pull':nothing_to_pull}

        if len(nothing_to_pull) > 0:
            return {'return':0, 'nothing_to_pull':nothing_to_pull}

        return {'return':0}


    ###############################################################################################
    def _nothing_to_pull(
        self,
        repo_path: str,  # The clone whose "git pull" failed.
        env: dict = None,  # The environment of the clone's identity (GIT_SSH_COMMAND), if any.
    ):
        """
            Why a clone whose "git pull" failed had nothing to pull from - it has no remote, its HEAD is detached (a
            clone pinned at a commit or a tag), its branch has no upstream, or its remote has no commit yet (an
            empty repository just made) -, or '' when the failure is a real one: local changes in the way, a
            conflict, a diverged branch, no network or no key. Asked only after a failed pull, so a pull that
            works costs nothing more; the remote is asked (git ls-remote) only for a clone without any commit.

            Args:
                repo_path (str): The clone.
                env (dict): The environment of the clone's identity (GIT_SSH_COMMAND), if any.

            Returns:
                str: The reason, or '' for a real failure.
        """

        run_env = dict(os.environ, **env) if env else None

        def git(*args):
            try:
                p = subprocess.run(['git', *args], cwd=repo_path, capture_output=True, stdin=subprocess.DEVNULL,
                                   env=run_env, timeout=60)
            except (OSError, subprocess.SubprocessError):
                return 1, ''

            return p.returncode, p.stdout.decode('utf-8', 'replace').strip()

        rc, remotes = git('remote')
        if rc == 0 and remotes == '':
            return 'it has no remote'

        rc, branch = git('symbolic-ref', '-q', '--short', 'HEAD')
        if rc != 0 or branch == '':
            return 'its HEAD is detached (pinned at a commit or a tag)'

        rc, remote = git('config', '--get', f'branch.{branch}.remote')
        if rc != 0 or remote == '':
            return f'its branch {branch} has no upstream'

        rc, _ = git('rev-parse', '-q', '--verify', 'HEAD')
        if rc != 0:
            rc, heads = git('ls-remote', '--heads', remote)
            if rc == 0 and heads == '':
                return 'its remote has no commits yet'

        return ''


    ###############################################################################################
    @staticmethod
    def _is_commit_sha(
        ref: str,  # Branch, tag or commit.
    ):
        """
            Tell whether a checkout reference looks like a commit SHA (7 to 40 hex digits).

            Args:
                ref (str): Branch, tag or commit.

            Returns:
                bool: True for a SHA, False for anything else.
        """

        import re

        return re.fullmatch(r'[0-9a-fA-F]{7,40}', ref or '') is not None


    ###############################################################################################
    def _hf_identity(
        self,
        identity: str,  # A secret alias, <category>::<artifact>/<token file>, or a token file path.
    ):
        """
            Resolve the identity given with --identity for a repository of the Hugging Face Hub: where its access
            token comes from. Three forms, as for a git identity: the alias of a token secret (the secret category
            of cmeta-aops, when it is plugged: the value is opened by "cx secret call" at the fetch, inside that
            call, and never kept or returned), a cMeta reference <category>::<artifact>/<file> to a file that holds
            the token inside an artifact, or a path to such a file (~ and environment variables expanded; its first
            non-empty line is the token). Resolved before anything is fetched, so that a wrong name leaves nothing
            behind; the token itself is read when the repository is fetched.

            Args:
                identity (str): The identity as given (None or '' = none).

            Returns:
                dict: return (int), error (str), source (dict: {'file': path} or {'secret': alias}, None for
                    no identity), name (str).
        """

        identity = str(identity or '').strip()

        if identity == '':
            return {'return':0, 'source':None, 'name':''}

        if '::' in identity:
            # A token file inside an artifact: <category>::<artifact>/<file>
            i = identity.find('::')
            j = identity.find('/', i)
            if j < 0:
                return {'return':1, 'error':f'--identity "{identity}" must be <category>::<artifact>/<token file in the artifact>, a secret alias or a token file'}

            cref, rel = identity[:j], identity[j+1:]

            r = self.cm.access({'category':'utils', 'command':'find_by_cid', 'arg1':cref, 'con':False})
            arts = r.get('artifacts', []) if r.get('return', 1) == 0 else []
            if len(arts) != 1:
                return {'return':1, 'error':f'--identity "{identity}": the artifact "{cref}" ' +
                                            ('is not on this machine' if len(arts) == 0 else f'resolves to {len(arts)} artifacts')}

            token_path = os.path.join(arts[0]['path'], *rel.split('/'))
            if not os.path.isfile(token_path):
                return {'return':1, 'error':f'--identity "{identity}": the token file {token_path} does not exist'}

            return {'return':0, 'source':{'file':token_path}, 'name':identity}

        token_path = os.path.expanduser(os.path.expandvars(identity))

        if os.path.isfile(token_path):
            # A token file
            return {'return':0, 'source':{'file':token_path}, 'name':identity}

        # The alias of a token secret (cmeta-aops): it must be there - its value is opened at the fetch
        r = self.cm.access({'category':'secret', 'command':'find', 'arg1':identity, 'con':False})
        arts = r.get('artifacts', []) if r.get('return', 1) == 0 else []
        if len(arts) == 0:
            why = str(r.get('error', '') or '')
            if 'category "secret" not found' in why:
                why = ('a secret alias needs the secret category of cMeta AOps: cx repo pull cmeta-aops; a token file '
                       'or <category>::<artifact>/<token file> works without it')
            return {'return':1, 'error':f'--identity "{identity}" is neither a token file nor a secret of that name' + (f' ({why})' if why else '')}
        if len(arts) > 1:
            return {'return':1, 'error':f'--identity "{identity}" matches {len(arts)} secrets: name one'}

        return {'return':0, 'source':{'secret':identity}, 'name':identity}


    ###############################################################################################
    def _hf_pull(
        self,
        ctx: dict,  # cMeta context.
        source: dict,  # Where the token comes from ({'file': path} or {'secret': alias}), or None.
        repo_id: str,  # The repository of the Hub (<owner>/<name>).
        repo_type: str,  # dataset, model or space.
        revision: str,  # The branch, tag or commit.
        folder: str,  # The folder of the clone.
        con: bool = False,  # If True, print the progress.
    ):
        """
            Bring a folder in step with a repository of the Hugging Face Hub (utils.net.hf_sync) with the token
            of the identity: read from its token file, or opened by the secret category - "cx secret call" runs
            the fetch inside the call that holds the value, which is never returned - and, without an identity,
            the token of this machine (HF_TOKEN, the hf login), if any.

            Returns:
                dict: what hf_sync returns (return, error, downloaded, removed, files, commit, bytes, seconds).
        """

        def sync(token):
            return utils.net.hf_sync(repo_id, repo_type, revision, folder, token = token, con = con)

        if not source:
            return sync(utils.net.hf_token())

        if source.get('file'):
            try:
                with open(source['file'], encoding = 'utf-8') as f:
                    token = next((line.strip() for line in f if line.strip()), '')
            except OSError as e:
                return {'return':1, 'error':f'the token file {source["file"]} cannot be read: {e}'}
            if token == '':
                return {'return':1, 'error':f'the token file {source["file"]} is empty'}
            return sync(token)

        return self.cm.access({'category':'secret', 'command':'call', 'arg1':source['secret'], 'func':sync,
                               'con':con, 'quiet':ctx.get('control', {}).get('quiet', False)})


    ###############################################################################################
    def _git_identity(
        self,
        identity: str,  # A secret alias, <category>::<artifact>/<key file>, or a key file path.
    ):
        """
            Resolve the git identity given with --identity: the git settings as (key, value) pairs - user.name,
            user.email, core.sshCommand, the signing keys: paths and names, never a key's content -, the
            environment of the clone (GIT_SSH_COMMAND from the transport key) and the name kept for the
            repository. Three forms: the alias of a secret of kind git or ssh (the secret category of cmeta-aops,
            when it is plugged), a cMeta reference <category>::<artifact>/<file> to a key file inside an artifact,
            or a path to a key file (~ and environment variables expanded). Resolved before anything is cloned,
            so that a wrong name leaves nothing behind.

            Args:
                identity (str): The identity as given (None or '' = none).

            Returns:
                dict: return (int), error (str), pairs (list of [key, value]), env (dict), name (str).
        """

        identity = str(identity or '').strip()

        if identity == '':
            return {'return':0, 'pairs':[], 'env':{}, 'name':''}

        def ssh_command(key_path):
            return f'ssh -i "{os.path.abspath(key_path).replace(os.sep, "/")}" -o IdentitiesOnly=yes'

        pairs = []

        if '::' in identity:
            # A key file inside an artifact: <category>::<artifact>/<file>
            i = identity.find('::')
            j = identity.find('/', i)
            if j < 0:
                return {'return':1, 'error':f'--identity "{identity}" must be <category>::<artifact>/<key file in the artifact>, a secret alias or a key file'}

            cref, rel = identity[:j], identity[j+1:]

            r = self.cm.access({'category':'utils', 'command':'find_by_cid', 'arg1':cref, 'con':False})
            arts = r.get('artifacts', []) if r.get('return', 1) == 0 else []
            if len(arts) != 1:
                return {'return':1, 'error':f'--identity "{identity}": the artifact "{cref}" ' +
                                            ('is not on this machine' if len(arts) == 0 else f'resolves to {len(arts)} artifacts')}

            key_path = os.path.join(arts[0]['path'], *rel.split('/'))
            if not os.path.isfile(key_path):
                return {'return':1, 'error':f'--identity "{identity}": the key file {key_path} does not exist'}

            pairs = [['core.sshCommand', ssh_command(key_path)]]

        else:
            key_path = os.path.expanduser(os.path.expandvars(identity))

            if os.path.isfile(key_path):
                # A key file
                pairs = [['core.sshCommand', ssh_command(key_path)]]

            else:
                # The alias of a secret (cmeta-aops): its git settings - paths and names only
                r = self.cm.access({'category':'secret', 'command':'settings', 'arg1':identity, 'con':False})
                if r.get('return', 1) > 0:
                    why = str(r.get('error', '') or '')
                    if 'category "secret" not found' in why:
                        why = ('a secret alias needs the secret category of cMeta AOps: cx repo pull cmeta-aops; a key file '
                               'or <category>::<artifact>/<key file> works without it')
                    return {'return':1, 'error':f'--identity "{identity}" is neither a key file nor a secret of that name' + (f' ({why})' if why else '')}

                pairs = [list(p) for p in (r.get('pairs') or [])]
                if len(pairs) == 0:
                    return {'return':1, 'error':f'--identity "{identity}": the secret gives no git settings'}

        env = {}
        for k, v in pairs:
            if k == 'core.sshCommand':
                env['GIT_SSH_COMMAND'] = v

        return {'return':0, 'pairs':pairs, 'env':env, 'name':identity}


    ###############################################################################################
    def _git_config(
        self,
        repo_path: str,  # Path to the git clone.
        pairs: list,  # The (key, value) pairs of the identity.
        con: bool = False,  # If True, print what is set.
    ):
        """
            Write a git identity into a clone's own configuration (git config --local), so that every later pull,
            fetch, push and commit in it - by cx or by the person - uses it without being told again. Prints keys,
            names and paths, never a key's content.

            Args:
                repo_path (str): Path to the git clone.
                pairs (list): The (key, value) pairs.
                con (bool): If True, print what is set.

            Returns:
                dict: return (int), error (str).
        """

        git = shutil.which('git')
        if not git:
            return {'return':1, 'error':'git is not found'}

        for k, v in pairs:
            p = subprocess.run([git, '-C', repo_path, 'config', '--local', str(k), str(v)], stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            if p.returncode != 0:
                return {'return':1, 'error':f'git config {k} failed in {repo_path}: {p.stderr.decode("utf-8", "replace").strip()}'}

            if con:
                print (f'  {k} = {v}')

        return {'return':0}


    ###############################################################################################
    def _record_identity(
        self,
        repos_config_path: str,  # The registration file of the repositories (repos.json).
        repo_path: str,  # The registered path of the repository.
        name: str,  # The identity as given.
    ):
        """
            Keep the identity's name in the repository's registration (repos.json - this machine's, never the
            shared _cmr.yaml), so that the index and "cx repo status" say which identity a clone uses.

            Args:
                repos_config_path (str): The registration file.
                repo_path (str): The registered path.
                name (str): The identity's name.

            Returns:
                dict: return (int), error (str).
        """

        r = utils.files.safe_read_file(repos_config_path, lock=True, keep_locked=True, fail_on_error=self.fail_on_error, logger=self.logger)
        if r['return']>0: return r

        repos_paths = r['data']
        file_lock = r['file_lock']

        entry = repos_paths.get(repo_path)
        if entry is None:
            return utils.files.unlock_path(repos_config_path, file_lock=file_lock, fail_on_error=self.fail_on_error, logger=self.logger)

        entry.setdefault('meta', {})['identity'] = name

        return utils.files.safe_write_file(repos_config_path, repos_paths, file_lock=file_lock, atomic=True,
                                           fail_on_error=self.fail_on_error, logger=self.logger, sort_keys=False)


    ###############################################################################################
    def _git_checkout(
        self,
        repo_path: str,  # Path to the git repository.
        checkout: str,  # Branch, tag, or commit to checkout.
        depth: int = None,  # Depth to fetch a missing ref at in a shallow clone (default: 1).
        con: bool = False,  # If True, print progress.
    ):
        """
            Run "git checkout <ref>", fetching the ref first when a shallow clone does not have it.

            A full clone behaves exactly as before: just "git checkout <ref>". A shallow clone
            only holds what was fetched, so a branch, a tag or a commit that is not there yet is
            fetched at the given depth (1 by default) - as a branch, then as a tag, then as a
            commit (a full SHA) - and then checked out.

            Args:
                repo_path (str): Path to the git repository.
                checkout (str): Branch, tag, or commit to checkout.
                depth (int): Depth to fetch a missing ref at in a shallow clone (default: 1).
                con (bool): If True, print progress.

            Returns:
                dict: A cMeta dictionary with the following keys:
                    - **return** (int): 0 if success, >0 if error.
                    - **error** (str): Error message if `return > 0`.
        """

        def quiet_run(cmd):
            r = utils.sys.run(cmd, work_dir=repo_path, con=False, capture_output=True)
            return r['return'] == 0 and r.get('returncode') == 0, r

        ok, r = quiet_run('git rev-parse --is-shallow-repository')
        shallow = ok and (r.get('stdout') or '').strip() == 'true'

        cmd = f'git checkout {checkout}'

        if shallow:
            local_ref, _ = quiet_run(f'git rev-parse --verify --quiet "{checkout}^{{commit}}"')
            remote_branch = False
            if not local_ref:
                remote_branch, _ = quiet_run(f'git rev-parse --verify --quiet "refs/remotes/origin/{checkout}^{{commit}}"')

            if not local_ref and not remote_branch:
                xdepth = depth if depth else 1

                fetches = [('branch', f'git fetch --depth {xdepth} origin +refs/heads/{checkout}:refs/remotes/origin/{checkout}'),
                           ('tag', f'git fetch --depth {xdepth} origin +refs/tags/{checkout}:refs/tags/{checkout}'),
                           ('commit', f'git fetch --depth {xdepth} origin {checkout}')]

                fetched = None
                for kind, xcmd in fetches:
                    ok, _ = quiet_run(xcmd)
                    if ok:
                        fetched = kind
                        if con:
                            print (f'Fetched {kind} "{checkout}" into the shallow clone: {xcmd}')
                        break

                if fetched is None:
                    return {'return':1, 'error':f'"{checkout}" is not in this shallow clone and could not be fetched '
                                                f'as a branch, a tag or a commit (a commit needs its full SHA)'}

                if fetched == 'branch':
                    # A shallow clone is also a single-branch clone: its fetch refspec maps only the
                    # branch it was cloned at, so later fetches and pulls would ignore this one
                    quiet_run(f'git remote set-branches --add origin {checkout}')
                    remote_branch = True

            if remote_branch:
                # "git checkout <branch>" guesses the remote branch only through the remote's
                # fetch refspec - create the tracking branch explicitly instead
                cmd = f'git checkout -b {checkout} --track origin/{checkout}'

        r = utils.sys.run(cmd, work_dir=repo_path, con=con)
        if r['return']>0: return r

        rc = r['returncode']
        if rc != 0:
            return {'return':1, 'error':f'System command "{cmd}" failed with exit code {rc}'}

        return {'return':0}


    ###############################################################################################
    def list__(
        self,
        params,  # Input parameters dictionary.
    ):
        """
            List cMeta repositories

            @base.list_

            Args:
                params: Input parameters dictionary.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        # p will be deep copied from params
        p = self._prepare_input_from_params(params, base = True)

        p['sort'] = False

        result = self.cm.access(p)

        return result

    ###############################################################################################
    def create(
        self,
        params,  # Input parameters dictionary.
    ):
        """
            Create local cMeta repository

            @self.get_

            Args:
                params: Input parameters dictionary.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        return self.get_(**params, local=True)


    ###############################################################################################
    def update__(
        self,
        params,  # Input parameters dictionary.
    ):
        """
            Update cMeta Git repositories

            @self.get_

            Args:
                params: Input parameters dictionary.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        return self.get_(**params, update=True)


    ###############################################################################################
    def find(
        self,
        params,  # Input parameters dictionary.
    ):
        """
            Find cMeta repositories

            @base.find_

            Args:
                params: Input parameters dictionary.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        # p will be deep copied from params
        p = self._prepare_input_from_params(params, base = True)

        p['sort'] = False

        result = self.cm.access(p)

        return result

    ###############################################################################################
    def delete(
        self,
        params,  # Input parameters dictionary.
    ):
        """
            Delete cMeta repositories

            @base.delete_

            Args:
                params (dict): Input parameters dictionary.
                (unplug) (bool): if True, only unregister repository but don't delete!

            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        ctx = params['ctx']
        con = ctx.get('control',{}).get('con', False)
        verbose = ctx.get('control',{}).get('verbose', False)

        unplug = params.get('unplug', False)

        # Check if some repos exists
        p = self._prepare_input_from_ctx(ctx, base = True)

        p['command'] = 'find'
        p['con'] = False

        if 'arg1' in params:
            p['arg1'] = params['arg1']

        result = self.cm.access(p)
        if result['return']>0:
            if unplug and result['return'] == 16:
                # Not in the index by that name: a registered FOLDER - a repository that is out of reach (a
                # detached drive: registered, not indexed) or simply named by its path - is forgotten by its path
                path = self._registered_path(params.get('arg1'))
                if path is not None:
                    return self._forget_registered_path(path, con, verbose)

            return result

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
    def _registered_path(
        self,
        name,  # A folder: the path of a registered repository (or, with inside=True, a folder inside one).
        inside = False,  # If True, a folder inside a registered repository names that repository too (the deepest one).
    ):
        """
            The path, as repos.json has it, of the registered repository that `name` is (or, with
            inside=True, lies in) - whether that repository is in the index or not. None when `name` is no
            such folder.
        """

        if name is None or str(name).strip() == '':
            return None

        wanted = os.path.abspath(os.path.normpath(str(name).strip()))

        r = utils.files.safe_read_file(self.cm.repos_config_path, lock=False, fail_on_error=False, logger=self.logger)
        if r['return']>0 or not isinstance(r.get('data'), dict):
            return None

        best = None
        best_full = None

        for path in r['data']:
            full = os.path.abspath(os.path.normpath(path))

            if os.path.normcase(full) == os.path.normcase(wanted) or (inside and utils.files.is_path_within(full, wanted)):
                if best is None or len(full) > len(best_full):
                    best = path
                    best_full = full

        return best


    ###############################################################################################
    def _forget_registered_path(
        self,
        path,  # The path of the repository as repos.json has it.
        con = False,  # If True, print output to console.
        verbose = False,  # If True, enable verbose output.
    ):
        """
            Unregister a repository by its path: its line leaves repos.json and its records leave the
            index; its folder, reachable or not, is left as it is.
        """

        repos_config_path = self.cm.repos_config_path

        r = utils.files.safe_read_file(repos_config_path, lock=True, keep_locked=True, fail_on_error=self.fail_on_error, logger=self.logger)
        if r['return']>0: return r

        repos_paths = r['data']
        repos_paths_file_lock = r['file_lock']

        repos_paths.pop(path, None)

        # Do not sort keys - preserve order
        r = utils.files.safe_write_file(repos_config_path, repos_paths, file_lock=repos_paths_file_lock, atomic=True,
                                        fail_on_error=self.fail_on_error, logger=self.logger, sort_keys=False)
        if r['return']>0: return r

        if con:
            print('')

        r = self.cm.repos.index(clean=False, con=con, verbose=verbose, delete_repo_paths = [path])
        if r['return']>0: return r

        if con:
            print (f'Unregistered the repository in "{path}" (its folder is left as it is)')

        return {'return':0, 'deleted_artifacts':[], 'unregistered_paths':[path]}


    ###############################################################################################
    def move(
        self,
        params,  # Input parameters dictionary.
    ):
        """
            Move cMeta repositories - not supported

            Args:
                params: Input parameters dictionary.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        return {'return':1, 'error':'moving/renaming repositories is not supported'}


    ###############################################################################################
    def get_alias_from_url_(
        self,
        ctx,  # Execution context dictionary with category, command, and control data.
        arg1,  # First positional argument from command input.
    ):
        """
            Get alias from URL

            Args:
                ctx: Execution context dictionary with category, command, and control data.
                arg1: First positional argument from command input.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        url = arg1

        # A repository of the Hugging Face Hub: hf-<owner>@<name>, as the aops datasets that point at the Hub are named
        hf = utils.net.hf_repo(url)
        if hf:
            return {'return': 0, 'alias': 'hf-' + hf['id'].replace('/', '@')}

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
    def status(
        self,
        params,  # Input parameters dictionary.
    ):
        """
            Update cMeta Git repositories

            @self.get_

            Args:
                params: Input parameters dictionary.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        return self.get_(**params, status=True)

    ###############################################################################################
    def pull(
        self,
        params,  # Input parameters dictionary.
    ):
        """
            Pull cMeta Git repositories

            @self.get_

            Args:
                params: Input parameters dictionary.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        return self.get_(**params)

    ###############################################################################################
    def clone(
        self,
        params,  # Input parameters dictionary.
    ):
        """
            Clone cMeta Git repositories

            @self.get_

            Args:
                params: Input parameters dictionary.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        return self.get_(**params)

    ###############################################################################################
    def checkout(
        self,
        params,  # Input parameters dictionary.
    ):
        """
            Checkout cMeta Git repositories

            @self.get_

            Args:
                params: Input parameters dictionary.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        if 'arg2' not in params:
            return {'return':1, 'error': 'checkout name is not specified in arg2'}

        import copy
        copy_params = params.copy()

        checkout = copy_params.pop('arg2')

        return self.get_(**copy_params, update=True, checkout = checkout)

    ###############################################################################################
    def clone(
        self,
        params,  # Input parameters dictionary.
    ):
        """
            Clone cMeta Git repositories

            @self.get_

            Args:
                params: Input parameters dictionary.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        return self.get_(**params, method='git')

    ###############################################################################################
    def init(
        self,
        params,  # Input parameters dictionary.
    ):
        """
            Init local cMeta repository

            @self.get_

            Args:
                params: Input parameters dictionary.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        return self.get_(**params, method='local')

    ###############################################################################################
    def unzip(
        self,
        params,  # Input parameters dictionary.
    ):
        """
            Install or update a cMeta repository from a local .zip archive.

                cx repo unzip <file.zip>              # first time: extract + register (plug) + index
                cx repo unzip <file.zip>              # again later: extract over + reindex (an update)
                cx repo unzip <file.zip> --path=<dir> # extract to a specific folder

            The repository's own alias is read from the `_cmr.yaml` (or `_cmr.json`) inside the
            archive - at its root, or one directory down - so the destination is `<repos>/<alias>`
            whatever the zip file is called. If that repository is not registered yet, it is plugged
            (registered and indexed); if it already is, its index is refreshed. So one command both
            installs a repository the first time and updates it afterwards, with no separate plug or
            reindex step.

            Note: an update replaces the files carried in the archive; a file you added locally is
            kept, and a file deleted upstream is not removed (unplug + delete the folder + unzip for an
            exact copy). Use `cx repo zip <alias>` to produce a compatible archive.

            Args:
                params: Input parameters dictionary (arg1 = path to the .zip file; path = optional target).
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        import json
        import re
        import zipfile

        ctx = params.get('ctx', {}) or {}
        con = ctx.get('control', {}).get('con', False)

        zip_file = params.get('arg1')
        if zip_file is None or zip_file == '':
            return {'return': 1, 'error': 'path to a .zip archive is required: cx repo unzip <file.zip>'}

        zip_file = os.path.abspath(os.path.normpath(zip_file))
        if not os.path.isfile(zip_file):
            return {'return': 1, 'error': f'zip file {zip_file} not found'}

        # Read the repository descriptor (_cmr.yaml / _cmr.json) nearest the archive root to learn the
        # repository's own name - never the name of the zip file (which is what the old code used).
        desc_basenames = ('_cmr.yaml', '_cmr.json')
        desc_member = None
        desc_raw = ''
        try:
            with zipfile.ZipFile(zip_file) as zf:
                files_in_zip = [m.filename.replace('\\', '/') for m in zf.infolist() if not m.is_dir()]

                # the descriptor closest to the root (fewest path separators) wins
                for member in sorted(files_in_zip, key=lambda x: (x.count('/'), len(x))):
                    if member.rsplit('/', 1)[-1] in desc_basenames:
                        desc_member = member
                        break
                if desc_member is not None:
                    desc_raw = zf.read(desc_member).decode('utf-8', 'ignore')
        except Exception as e:
            return {'return': 1, 'error': f'cannot read archive {zip_file}: {e}'}

        if desc_member is None:
            return {'return': 1, 'error': f'{zip_file} is not a cMeta repository archive '
                                          f'(no _cmr.yaml / _cmr.json at or near its root)'}

        # the repository name from the descriptor's `artifact:` field
        repo_name = ''
        if desc_member.endswith('.json'):
            try:
                repo_name = (json.loads(desc_raw) or {}).get('artifact', '')
            except Exception:
                repo_name = ''
        else:
            m = re.search(r'(?m)^[ \t]*artifact[ \t]*:[ \t]*(.+?)[ \t]*$', desc_raw)
            if m:
                repo_name = m.group(1).strip().strip('"\'')
        if repo_name is None or repo_name == '':
            return {'return': 1, 'error': f'the descriptor {desc_member} in {zip_file} has no "artifact" name'}

        r = utils.names.parse_cmeta_name(repo_name)
        if r['return'] > 0:
            return r
        repo_alias = r.get('name', {}).get('alias') or r.get('name', {}).get('uid')
        if not repo_alias:
            return {'return': 1, 'error': f'could not read a repository alias from "{repo_name}"'}

        # how many leading directories to strip so the descriptor lands at the extraction root
        remove_directories = desc_member.count('/')

        # the destination folder: an explicit --path, else <repos>/<alias>
        path = params.get('path')
        if path is None or path == '':
            path = os.path.join(self.cm.repos_path, repo_alias)
        path = os.path.abspath(os.path.normpath(path))

        # is a repository at this path already registered?
        already_registered = False
        r = utils.files.safe_read_file(self.cm.repos_config_path, lock=False,
                                       fail_on_error=self.fail_on_error, logger=self.logger)
        if r['return'] == 0:
            already_registered = path in (r['data'] or {})

        if con:
            print('')
            print(f'Repository "{repo_alias}" from {zip_file}')
            print(f'{"Updating" if already_registered else "Installing"} in {path} ...')

        # extract; overwrite so an update replaces changed files
        r = utils.files.unzip(zip_file, path=path, remove_directories=remove_directories,
                              overwrite=True, clean=False, fail_on_error=self.fail_on_error)
        if r['return'] > 0:
            return r

        if already_registered:
            # an update: refresh the index (re-scans the repo, so new artifacts are picked up too)
            if con:
                print('')
                print('Reindexing ...')
            return self.cm.repos.index(clean=False, con=con, add_repo_paths=[path])

        # first time: register and index in one step (reuses the tested `plug` path)
        if con:
            print('')
            print('Registering (plug) and indexing ...')
        return self.plug({'ctx': ctx, 'arg1': path})


    ###############################################################################################
    def zip_(
        self,
        ctx: dict,  # cMeta context
        arg1: str,  # repository name (alias and/or UID)
        skip_date: bool = False,  # if True, skip date and time from filename
        skip_dirs: list = None,  # directories to skip from zipping
        skip_files: list = None,  # files to skip from zipping
        output_path: str = None,  # output path for zip file
        zip_name: str = None,  # explicit output zip filename
        force: bool = False,  # if True, overwrite existing zip file
    ):
        """
            Zip cMeta repository.

            Args:
              ctx (dict): cMeta context
              arg1 (str): repository name (alias and/or UID)
              skip_date (bool): if True, skip date and time from filename
              skip_dirs (list): directories to skip from zipping
                            skip_files (list): files to skip from zipping
              output_path (str): output path for zip file
                            zip_name (str): explicit output zip filename
                            force (bool): if True, overwrite existing zip file

            Returns:
              (CM return dict):

              * return (int): return code == 0 if no error and >0 if error
              * (error) (str): error string if return>0
              * (zip_path) (str): path to created zip file

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        con = ctx.get('control',{}).get('con', False)
        
        # from the command line the lists arrive as comma-separated strings
        if isinstance(skip_dirs, str):
            skip_dirs = [x.strip() for x in skip_dirs.split(',') if x.strip()]
        if isinstance(skip_files, str):
            skip_files = [x.strip() for x in skip_files.split(',') if x.strip()]
        if not skip_dirs:
            skip_dirs = ['.venv', '__pycache__', 'tmp*']

        if not skip_files:
            skip_files = []

        # Find the repository
        p = {'category': ctx['category'], 
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
        if zip_name:
            zip_filename = zip_name
        else:
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
            if skip_files:
                print(f'Skipping files: {", ".join(skip_files)}')

        if os.path.isfile(zip_path):
            r = utils.files.ask_to_delete(con, force, output_path, name=zip_filename, space=True)

            if con:
                print ('')

            if r['return']>0: return r

            if not r['confirmed']:
                return {'return':1, 'error':f'zip file already exists: {zip_path}'}

            os.remove(zip_path)

        # Zip the directory
        r = utils.files.zip_directory(
            repo_path,
            zip_path,
            skip_directories=skip_dirs,
            fail_on_error=self.fail_on_error,
            skip_files=skip_files,
        )
        if r['return']>0: return r

        if con:
            print(f'Repository successfully zipped to: {zip_path}')

        return {'return':0, 'zip_path': zip_path}

    ###############################################################################################
    def plug(
        self,
        params,  # Input parameters dictionary.
    ):
        """
            Plug local cMeta repository
            If arg1 is None, use current directory
            If arg1 is not None:
               If existing path -> use that path
               If path does't exist, use as alias


            @self.get_

            Args:
                params: Input parameters dictionary.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        arg1 = params.get('arg1', None)

        if arg1 is None or arg1 == '' or arg1 == '.':
            arg1 = os.getcwd()
        else:
            arg1 = os.path.abspath(os.path.normpath(arg1))

        p = params.copy()
        p['arg1'] = None
        p['local'] = True
        p['path'] = arg1

        return self.get_(**p)

    ###############################################################################################
    def unplug(
        self,
        params,  # Input parameters dictionary.
    ):
        """
            UnPlug local cMeta repository
            If arg1 is None, use current directory
            If arg1 is not None:
               If existing path -> use that path
               If path does't exist, use as alias

            @self.delete

            Args:
                params: Input parameters dictionary.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        arg1 = params.get('arg1', None)

        if arg1 is None or arg1 == '' or arg1 == '.':
            # Attempt to detect in current
            r = utils.common.detect_cid_in_the_current_directory(self.cm, debug = self.cm.debug, logger = self.cm.logger)
            if r['return'] >0: return r

            artifact_repo_alias = r['artifact_repo_alias']

            if artifact_repo_alias is None or artifact_repo_alias == '':
                return {'return':1, 'error':'couldn\'t detect repo in the current path'}

            arg1 = artifact_repo_alias

        p = params.copy()
        p['arg1'] = arg1
        p['unplug'] = True

        return self.delete(p)

    ###############################################################################################
    def reindex_(
        self,
        ctx: dict,  # cMeta context.
        arg1: str = None,  # The repository: alias, UID or alias,UID (wildcards allowed), the path of its folder, or "." for the repository of the current directory.
    ):
        """
            Reindex registered repositories: re-read their `_cmr.yaml` and index their artifacts again,
            as `pull`, `plug` and `unzip` do when they bring a repository in, leaving the records of the
            other repositories as they are. Use it after files were copied or pulled into a repository by
            other means, after its `_cmr.yaml` was edited, or when its artifacts look stale - instead of
            `cx --reindex`, which rebuilds the index of every repository.

            A repository whose folder is not there (a detached drive) is refused and nothing is changed.

            Args:
                ctx (dict): cMeta context.
                arg1 (str): The repository: alias, UID or alias,UID (wildcards allowed), the path of its
                    folder, or "." for the repository of the current directory. Required.

            Returns:
                dict: A cMeta dictionary with the following keys:
                    - **return** (int): 0 if success, >0 if error (16: no such repository).
                    - **error** (str): Error message if `return > 0`.
                    - **artifacts** (list): The repositories reindexed (their records as they were before).
                    - **paths** (list): Their registered paths.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        con = ctx.get('control',{}).get('con', False)
        verbose = ctx.get('control',{}).get('verbose', False)

        if arg1 is None or str(arg1).strip() == '':
            return {'return':1, 'error':'name the repository to reindex: its alias, UID or path, or "." for the repository of the current directory '
                                        '(to rebuild the index of every repository, run "cx --reindex")'}

        arg1 = str(arg1).strip()

        repo_artifacts = []
        unindexed_path = None

        if arg1 == '.' or os.path.isdir(arg1):
            # A folder: the registered repository that holds it (the deepest one, for nested repositories)
            path = os.path.abspath(os.path.normpath(os.getcwd() if arg1 == '.' else arg1))

            r = self.cm.repos.find_in_index('repo', self.cm.cfg['category_repo_uid'])
            if r['return']>0: return r

            best = None
            best_path = None

            for repo in r['artifacts']:
                repo_path = os.path.abspath(os.path.normpath(repo['path']))

                if utils.files.is_path_within(repo_path, path):
                    if best is None or len(repo_path) > len(best_path):
                        best = repo
                        best_path = repo_path

            if best is None:
                # Registered but not in the index: a repository that was out of reach when the index was last
                # built (it stays registered) and is there again
                unindexed_path = self._registered_path(path, inside=True)

                if unindexed_path is None:
                    return {'return':16, 'error':f'no registered repository holds "{path}" - register it first with "cx repo plug <path>"'}

            else:
                repo_artifacts = [best]

        else:
            p = {'category': ctx['category'],
                 'command': 'find',
                 'arg1': arg1,
                 'sort': False,
                 'base': True,
                 'con': False}

            r = self.cm.access(p)
            if r['return']>0: return r

            repo_artifacts = r['artifacts']

        # Only a registered path can be reindexed, and only one whose folder is there: the incremental
        # index drops a repository whose descriptor it cannot read (unless the repository is kept)
        repos_config_path = self.cm.repos_config_path

        r = utils.files.safe_read_file(repos_config_path, lock=False, fail_on_error=self.fail_on_error, logger=self.logger)
        if r['return']>0: return r

        repos_paths = r['data']

        paths = []

        for repo in repo_artifacts:
            repo_cmeta_ref_parts = repo['cmeta_ref_parts']
            repo_alias = repo_cmeta_ref_parts.get('artifact_alias', repo_cmeta_ref_parts['artifact_uid'])

            path = repo['path']

            if path not in repos_paths:
                caller = ctx.get('origin',{}).get('cli',{}).get('caller','')
                return {'return':1, 'error':f'repository "{repo_alias}" is indexed with the path "{path}" that is not in {repos_config_path} - try "{caller} --reindex"'}

            if not os.path.isdir(path) or not os.path.isfile(os.path.join(path, self.cm.cfg['repo_meta_desc'])):
                return {'return':1, 'error':f'the folder of repository "{repo_alias}" or its {self.cm.cfg["repo_meta_desc"]} is not there: {path} (a detached drive?) - nothing was reindexed'}

            paths.append(path)

        if unindexed_path is not None:
            if not os.path.isdir(unindexed_path) or not os.path.isfile(os.path.join(unindexed_path, self.cm.cfg['repo_meta_desc'])):
                return {'return':1, 'error':f'the folder of the repository registered as "{unindexed_path}" or its {self.cm.cfg["repo_meta_desc"]} is not there (a detached drive?) - nothing was reindexed'}

            paths.append(unindexed_path)

        if con:
            print ('')

        r = self.cm.repos.index(clean=False, con=con, verbose=verbose, add_repo_paths=paths)
        if r['return']>0: return r

        if con:
            for repo, path in zip(repo_artifacts, paths):
                repo_cmeta_ref_parts = repo['cmeta_ref_parts']
                repo_alias = repo_cmeta_ref_parts.get('artifact_alias', '')
                repo_uid = repo_cmeta_ref_parts['artifact_uid']

                print (f'Reindexed repository "{repo_alias}" ({repo_uid}): {path}')

            if unindexed_path is not None:
                print (f'Reindexed the repository in "{unindexed_path}" (it was registered and not in the index)')

        return {'return':0, 'artifacts': repo_artifacts, 'paths': paths}

    ###############################################################################################
    def space(
        self,
        params,  # Input parameters dictionary.
    ):
        """
            Get space of a give repo
            @self.find

            Args:
                params: Input parameters dictionary.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        ctx = params['ctx']
        con = ctx.get('control',{}).get('con', False)

        # Check if some repos exists
        p = self._prepare_input_from_ctx(ctx, base = True)

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
