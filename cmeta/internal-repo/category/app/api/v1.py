"""
cMeta app functions

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import sys
import copy

from cmeta.category import InitCategory

class Category(InitCategory):
    """
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


    ############################################################
    def test_(
        self,
        ctx: dict,  # cMeta context.
        arg1: str = None,  # Test argument 1.
        flag1: bool = False,  # Test flag 1.
    ):
        """
            Test function.

            Args:
                ctx (dict): cMeta context.
                arg1 (str | None): Test argument 1.
                flag1 (bool): Test flag 1.

            Returns:
                dict: Dictionary with 'return': 0.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        self.logger.debug("RUNNING API v1 test_")

        print (f'arg1={arg1}')
        print (f'flag1={flag1}')

        return {'return':0}

    ############################################################
    def test2(
        self,
        params: dict,  # cMeta parameters.
    ):
        """
            Test function 2.

            Args:
                params (dict): cMeta parameters.

            Returns:
                dict: Dictionary with 'return': 0.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        self.logger.debug("RUNNING API v1 test2")

        import json
        print (json.dumps(params, indent=2))

        return {'return':0}

    ############################################################
    def run_(
        self,
        ctx,  # cMeta context.
        arg1,  # Artifact alias or UID.
        run_script = None,  # Script name to execute from artifact path.
        env = {},  # Extra environment variables merged before execution.
        param = {},  # Additional execution parameters merged with defaults.
    ):
        """
            Simple app run.

            Args:
                ctx (dict): cMeta context.
                arg1 (str): Artifact alias or UID.
                run_script (str): Script name to execute from artifact path.
                env (dict): Extra environment variables merged before execution.
                param (dict): Additional execution parameters merged with defaults.

            Returns:
                dict: Dictionary with 'return': 0.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        con = ctx.get('control', {}).get('con', False)
        verbose = ctx.get('control', {}).get('verbose', False)

        env1 = env.copy()

        # Call base find function to find an artifact
        p = {'category':ctx['category'], 
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
        cmeta_orig = artifact['cmeta']

        cmeta = copy.deepcopy(cmeta_orig)

        # Check cfg
        config_name = cmeta.get('config_name', '')
        config_cmeta = {}
        if config_name != '':
            r = self.cm.access({'category': self.cmeta['uses_categories']['config'],
                                'command': 'get',
                                'arg1': config_name})
            if r['return']>0: return r

            config_cmeta = r['config_cmeta']

            config_cmeta_vars = config_cmeta.get('vars', {})
            cmeta = self.cm.utils.common.deep_merge(cmeta, config_cmeta, append_lists=True)

            config_cmeta_env = config_cmeta.get('env', {})
            if len(config_cmeta_env) >0:
                env2 = env1.copy()
                env1 = config_cmeta_env
                env1 = self.cm.utils.common.deep_merge(env1, env2, append_lists=True)

            config_cmeta_param = config_cmeta.get('param', {})
            if len(config_cmeta_param) >0:
                param1 = param
                param = config_cmeta_param.copy()
                param = self.cm.utils.common.deep_merge(param, param1, append_lists=True)

            
        # The interpreter cMeta itself is running under, exported for every app's
        # run script.
        #
        # A run script cannot assume "python" is on PATH. A `uv tool` install
        # (the route the installer page recommends) keeps its interpreter out of
        # PATH on purpose - only the cx/cmeta/cserver shims go there - so a bare
        # `python` in a run script fails with "python: not found" even though cx
        # works perfectly. Modern Linux is the same story with python3 and no
        # python alias. sys.executable is also the ONLY interpreter guaranteed
        # to have cmeta itself importable, which is what an app like cserver
        # needs.
        #
        # Not overwritten if the caller or a config already set it.
        if not env1.get('CMETA_PYTHON'):
            env1['CMETA_PYTHON'] = sys.executable

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


        if len(param)>0:
            param_env_prefix = cmeta.get('param_env_prefix', '')
            for p in param:
                pp = param_env_prefix + p.upper()
                env1[pp] = param[p]

        r = self.cm.utils.sys.run(cmd, env=env1, envs=default_env, con=con, verbose=verbose)
        if r['return']>0: return r

        rc = r['returncode']
            
        if not skip_chdir:
            os.chdir(cur_dir)

        return {'return':0, 'return_code':rc}
