"""
cMeta cache functions

cMeta author and developer: (C) 2025-2026 Grigori Fursin

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
    def show_(
            self,
            state: dict,
            arg1: str = None,              # Artifact alias or UID
            tags: str = None,              # Comma-separated string or iterable of tags to match
            sort: bool = None,             # Sort by path
            match: dict = None,            # Filter artifacts by this match dict (if key ends with -, do not include value)
            sort_keys: list = None,
            show_tags: bool = False,
            skip_uids: bool = False,
    ):
        """
        Show cache
        
        Args:
            params (dict): cMeta parameters.
            
        Returns:
            dict: Dictionary with 'return': 0.
        """

        self.logger.debug("RUNNING cache show API v1")

        con = state['control'].get('con', False)

        # Call base find function to find an artifact with a website
        p = {'category':state['category'],
             'command':'find',
             'arg1':arg1,
             'tags':tags,
             'sort':sort,
             'match':match}

        r = self.cm.access(p)
        if r['return']>0 and r['return'] != 16: 
            return self.cm._error2(r, self.cm.fail_on_error)

        artifacts = r.get('artifacts', [])

        xsort_keys = sort_keys if sort_keys else ["@cmeta.params.name", "@cmeta.params.version-", "@cmeta.params.tag-"]

        artifacts = sorted(
            artifacts,
            key=lambda a: self.cm.utils.common.build_sort_key(a, xsort_keys)
        )

        num_artifacts = len(artifacts)
        index = 1
        for n in range(num_artifacts):
            a = artifacts[n]
            if con:
                cmeta_ref_parts = a['cmeta_ref_parts']
                cmeta = a['cmeta']
                path = a['path']

                name = cmeta.get('name', '')
                alias = cmeta_ref_parts['artifact_alias']
                uid = cmeta_ref_parts['artifact_uid']

                x = name if name != '' else alias

                xtags = '[' + ','.join(cmeta['tags']) + '] ' if show_tags else ''

                xuid = f'({uid})' if not skip_uids else ''

                text = f'{index}) {x} {xtags}{xuid}'

                xparams = {}
                for cmeta_params_key in ['params', 'tags', 'path']:
                    if cmeta_params_key in cmeta:
                        uparams = cmeta[cmeta_params_key]
                        if type(uparams) == dict:
                            for p in sorted(uparams):
                                xparams[cmeta_params_key+'.'+p] = str(uparams[p])
                        elif type(uparams) == list:
                            xparams[cmeta_params_key] = ','.join(uparams)
                        else:
                            xparams[cmeta_params_key] = str(uparams)
                
                if len(xparams)>0:
                    for p in sorted(xparams):
                        v = xparams[p]
                        text += f'\n      * {p} = {v}'

                print (text)

                if cmeta_params_key and n != num_artifacts-1:
                    print ('')

            index += 1

        return {'return':0}

