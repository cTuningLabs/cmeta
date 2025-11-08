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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path = __file__, **kwargs)

    def create(self, params):
        """
        Create new category with commands

        @base.create_
        """

        params_copy = params.copy()

        if 'yaml' not in params_copy:
            params_copy['yaml'] = True

        con = params.get('state',{}).get('control',{}).get('con', False)

        meta = params_copy.setdefault('meta', {})
            
        if 'default_api_version' not in meta: meta['default_api_version']=1

        p = self._prepare_input_from_params(params_copy, base = True)

        result = self.cm.access(p)
        if result['return']>0: return result

        path = result['path']

        api_path = os.path.join(path, 'api')
        if not os.path.isdir(api_path):
            os.makedirs(api_path)

        api_filepath = os.path.join(api_path, 'v1.py')
        if os.path.exists(api_filepath):
            return {'return':1, 'error':f'API file "{api_filepath}" already exists'}

        api_template_filepath=os.path.join(self.path, 'v1-template.py')

        import shutil

        shutil.copyfile(api_template_filepath, api_filepath)

        print (f'API code was created in "{api_filepath}"')

        return result




    def move(self, params):
        """
        Move/rename category

        @base.move_
        """

        input('xyz1')

        p = self._prepare_input_from_params(params, base = True)

        return self.cm.access(p)

