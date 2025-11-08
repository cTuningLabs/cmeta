"""
CMeta category functions

cMeta author and developer: (C) 2025 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
from cmeta.category import InitCategory

from cmeta.utils import names

class Category(InitCategory):
    """
    Various Utils
    """

    def __init__(self, *kwargs):
        self.module_file_path = __file__
        super().__init__(*kwargs)


    def create(self, params):
        """
        Create new category with commands

        @base.create_
        """

        input('xyz2')

        params_copy = params.copy()

        if 'yaml' not in params_copy:
            params_copy['yaml'] = True

        meta = params_copy.setdefault('meta', {})
            
        if 'default_api_version' not in meta: meta['default_api_version']=1

        p = self._prepare_input_from_params(params_copy, base = True)

        print (p)

        r = self.cm.access(p)
        if r['return']>0: return r

        path = r['path']

        print (self.path)
        print (path)

        return r




    def move(self, params):
        """
        Move/rename category

        @base.move_
        """

        input('xyz1')

        p = self._prepare_input_from_params(params, base = True)

        return self.cm.access(p)

