"""
cMeta config functions

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os

from cmeta import utils
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
    def read(self, params):
        """
        Read config with default ['data.json']

        @base.read_
        """

        con = params['state']['control'].get('con', False)

        p = self._prepare_input_from_params(params, base = True)

        if 'load_files' not in p:
            p['load_files'] = ['data.json']

        r = self.cm.access(p)

        r['config_cmeta'] = r.get('loaded_files',{}).get('data.json',{}).get('data', {})

        return r

    ############################################################
    def get(self, params):
        """
        Get config with default ['data.json']

        @base.get_
        """

        con = params['state']['control'].get('con', False)

        p = self._prepare_input_from_params(params, base = True)

        if 'load_files' not in p:
            p['load_files'] = ['data.json']

        r = self.cm.access(p)

        r['config_cmeta'] = r.get('loaded_files',{}).get('data.json',{}).get('data', {})

        return r

    ############################################################
    def show_(self, state, arg1):
        """
        Show configuration

        @base.create_
        """

        con = state['control'].get('con', False)

        p = self._prepare_input_from_state(state)

        p['command'] = 'get'
        p['arg1'] = arg1
        p['con'] = False

        r = self.cm.access(p)
        if r['return']>0: return r

        loaded_files = r['loaded_files']

        config_file_dict = loaded_files.get('data.json',{})
        config_cmeta = config_file_dict.get('data',{})
        r['config_cmeta'] = config_cmeta

        path = config_file_dict['path']

        if con:
            print (f'Configuration "{arg1}" ({path}):')

            print ('')
            flat_cmeta = self.cm.utils.common.flatten_dict(config_cmeta)
            for k in sorted(flat_cmeta):
                v = flat_cmeta[k]
                print (f'--meta.{k}={v}')

        return r

    ############################################################
    def set_(self, 
             state, 
             arg1 = None,
             meta = {},
             load_files = None,
             unset = False,
        ):
        """
        Set keys in configuration artifacts

        @base.get_
        """

        import copy

        con = state['control'].get('con', False)

        p = {
           'category':state['category'],
           'arg1':arg1
        }

        if load_files is not None:
            p['load_files'] = load_files

        if len(meta) == 0:
            p['command'] = 'show'
            p['con'] = con
        else:
            p['command'] = 'get'

        r = self.cm.access(p)
        if r['return']>0: return r

        if len(meta)>0:
            loaded_files = r['loaded_files']

            config_file_dict = loaded_files.get('data.json',{})

            path = config_file_dict['path']

            # Load with lock
            r = utils.files.safe_read_file(path, lock=True, keep_locked=True, fail_on_error=self.fail_on_error, logger=self.logger)
            if r['return']>0: 
                if r['return']!=16: return r

                config_data = {}
                config_file_lock = None
            else:
                config_data = r['data']
                config_file_lock = r['file_lock']
            
            # Update with update_meta
            if unset:
                config_data = self.cm.utils.common.deep_remove(config_data, meta)
            else:
                config_data = self.cm.utils.common.deep_merge(config_data, meta, append_lists=False)

            # Save and release lock
            r = utils.files.safe_write_file(path, config_data, file_lock=config_file_lock, atomic=True, fail_on_error=self.fail_on_error, logger=self.logger, sort_keys=False)
            if r['return']>0: return r

            rx = self.cm.access({'category':state['category'], 'command':'show', 'arg1':arg1, 'con':con})
            if rx['return']>0: return rx

        return r

    ############################################################
    def unset(self, params):
        """
        Unset (delete) keys in configuration artifacts

        @self.set_
        """

        return self.set_(**params, unset=True)
