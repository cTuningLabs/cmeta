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

        con = params.get('state',{}).get('control',{}).get('con', False)

        # Will create deep copy of params
        p = self._prepare_input_from_params(params, base = True)

        meta = p.setdefault('meta', {})
        if 'default_api_version' not in meta: meta['default_api_version']=1

        if 'yaml' not in p:
            p['yaml'] = True

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

        con = params.get('state',{}).get('control',{}).get('con', False)

        # Check that move and not rename!
        arg1 = params.get('arg1', None)
        arg2 = params.get('arg2', None)

        arg1_obj_parts = {}
        if arg1 is not None:
            r = names.parse_cmeta_obj(arg1, fail_on_error = self.fail_on_error)
            if r['return'] >0: return r
            arg1_obj_parts = r['obj_parts']

        arg2_obj_parts = {}
        if arg2 is not None:
            r = names.parse_cmeta_obj(arg2, fail_on_error = self.fail_on_error)
            if r['return'] >0: return r
            arg2_obj_parts = r['obj_parts']

        arg1_alias = arg1_obj_parts.get('alias')
        arg2_alias = arg2_obj_parts.get('alias')

        if arg1_alias is not None and arg2_alias is not None and arg1_alias != arg2_alias:
            return {'return':1, 'error':'renaming a category is not allowed for backward compatibility reasons. Please create a new category instead.'}

        # p will be deep copied from params
        p = self._prepare_input_from_params(params, base = True)

        result = self.cm.access(p)

        return result
