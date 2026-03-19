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
    def show_(
        self,
        ctx: dict,  # cMeta context.
        arg1: str = None,  # Artifact alias or UID filter.
        tags: str = None,  # Comma-separated tags to match.
        sort: bool = None,  # If True, request sorted lookup from find.
        match: dict = None,  # Additional key-value match filter.
        sort_keys: list = None,  # Keys used to sort displayed artifacts.
        show_tags: bool = False,  # If True, print artifact tags in output.
        skip_uids: bool = False,  # If True, omit UIDs from printed entries.
    ):
        """
            Show cache

            Args:
                ctx (dict): cMeta context.
                arg1 (str): Artifact alias or UID filter.
                tags (str): Comma-separated tags to match.
                sort (bool): If True, request sorted lookup from find.
                match (dict): Additional key-value match filter.
                sort_keys (list): Keys used to sort displayed artifacts.
                show_tags (bool): If True, print artifact tags in output.
                skip_uids (bool): If True, omit UIDs from printed entries.

            Returns:
                dict: Dictionary with 'return': 0.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        self.logger.debug("RUNNING cache show API v1")

        con = ctx['control'].get('con', False)

        # Call base find function to find an artifact with a website
        p = {'category':ctx['category'],
             'command':'find',
             'arg1':arg1,
             'tags':tags,
             'sort':sort,
             'match':match}

        r = self.cm.access(p)
        if self.cm.catch_error(r): return r

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

    ############################################################
    def clean(
        self,
        params: dict,  # cMeta parameters.
    ):
        """
            Args:
                params (dict): cMeta parameters.

            Returns:
                dict: Dictionary with 'return': 0.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        # p will be deep copied from params
        p = self._prepare_input_from_params(params, base = True)

        p['command'] = 'rm'
        p['tags'] = 'tmp'
        p['force'] = True

        return self.cm.access(p)

    ############################################################
    def delete(
        self,
        params: dict,  # cMeta parameters.
    ):
        """
            Args:
                params (dict): cMeta parameters.

            Returns:
                dict: Dictionary with 'return': 0.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        # p will be deep copied from params
        p = self._prepare_input_from_params(params, base = True)

        arg1 = p.get('arg1', '')
        if arg1 is None: arg1 = ''

        if ':' not in arg1:
            arg1 = 'local:' + arg1

        p['arg1'] = arg1

        return self.cm.access(p)
