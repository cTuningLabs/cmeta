"""
cMeta app functions

cMeta author and developer: (C) 2025 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os

from cmeta.category import InitCategory

class Category(InitCategory):
    """
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path = __file__, **kwargs)


    ############################################################
    def test_(
            self,
            state: dict,             # cMeta state
            arg1: str = None,        # Test argument 1
            flag1: bool = False      # Test flag 1
    ):
        """
        Test function.
        
        Args:
            state (dict): cMeta state.
            arg1 (str | None): Test argument 1.
            flag1 (bool): Test flag 1.
            
        Returns:
            dict: Dictionary with 'return': 0.
        """

        self.logger.debug("RUNNING API v1 test_")

        print (f'arg1={arg1}')
        print (f'flag1={flag1}')

        return {'return':0}

    ############################################################
    def test2(
            self,
            params: dict  # cMeta parameters
    ):
        """
        Test function 2.
        
        Args:
            params (dict): cMeta parameters.
            
        Returns:
            dict: Dictionary with 'return': 0.
        """

        self.logger.debug("RUNNING API v1 test2")

        import json
        print (json.dumps(params, indent=2))

        return {'return':0}

    ############################################################
    def run_(
            self,
            state,
            arg1,
            run_script = None,
            env = {},
            param = {},
    ):
        """
        Simple app run.
        
        Args:
            
        Returns:
            dict: Dictionary with 'return': 0.
        """

        con = state.get('control',{}).get('con', False)

        
        # Call base find function to find an artifact
        p = {'category':state['category'], 
             'command':'find',
             'arg1':arg1,
             'base':True}

        r = self.cm.access(p)
        if r['return']>0: return r

        artifacts = r.get('artifacts',[])

        if len(artifacts)>1:
            return {'return':1, 'error':f'more than 1 artifact selected in {__name__}'}

        artifact = artifacts[0]

        path = artifact['path']
        cmeta = artifact['cmeta']

        default_env = cmeta.get('default_env', {})

        if run_script is None or run_script == '':
            run_script = cmeta.get('run_script')
        if run_script is None or run_script == '':
            run_script = '_run'

        skip_chdir = cmeta.get('skip_chdir', False)

        if skip_chdir:
            path_to_run_script = os.path.join(path, run_script)
        else:
            cur_dir = os.getcwd()

            if con:
                print (f'$ cd {path}')

            os.chdir(path)

            path_to_run_script = run_script

        if os.name == 'nt':
            path_to_run_script += '.bat'
        else:
            path_to_run_script = './' + path_to_run_script + '.sh'

        path_to_run_script2 = self.cm.utils.files.quote_path(path_to_run_script)

        if os.name == 'nt':
            cmd = f'call {path_to_run_script2}' 
        else:
            cmd = f'. {path_to_run_script2}' 


        envs = default_env.copy()
        if len(param)>0:
            param_env_prefix = cmeta.get('param_env_prefix', '')
            for p in param:
                pp = param_env_prefix + p.upper()
                envs[pp] = param[p]

        r = self.cm.utils.sys.run(cmd, env=env, envs=envs, con=con, verbose=True)
        if r['return']>0: return r

        rc = r['returncode']
            
        if not skip_chdir:
            os.chdir(cur_dir)

        return {'return':0, 'return_code':rc}
