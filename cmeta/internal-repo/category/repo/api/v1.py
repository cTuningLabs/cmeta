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

    def __init__(self, *kwargs):
        self.module_file_path = __file__
        super().__init__(*kwargs)


    def find_(self, state, arg1=None):
        """
        Find cMeta repositories

        @base.find_
        """


        input('xyz')


        r = {'return':0}

        return r

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
