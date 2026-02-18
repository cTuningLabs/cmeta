"""
CMeta common repo functions

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

###################################################################################################
def _extract_category_artifact(s: str) -> str:
    import re

    # Remove leading/trailing whitespace and parentheses from the entire string
    s = s.strip().strip('()')
    
    # 1) Specific case: ignore preceding words if a 16-hex token directly precedes ':'
    # Example: "(in fursin website) Logos   f7458783a87400f1:79541da5b57f6591"
    #          -> f7458783a87400f1::79541da5b57f6591
    # 2) Already normalized with '::'
    # 3) Single ':' -> normalize to '::'
    patterns = [
        (r'.*?\b([0-9a-fA-F]{16})\s*:\s*(.+)',  # trailing 16-hex before colon
         lambda g1, g2: f"{g1}::{g2.strip()}"),
        (r"([\w.,\-@'!\s\"]+)::([\w.,\-@'!\s\"]+)",  # Added ' and ! to character class, already has ::
         lambda g1, g2: f"{g1.strip()}::{g2.strip()}"),
        (r"([\w.,\-@'!\s\"]+):([\w.,\-@'!\s\"]+)",  # Added ' and ! to character class, single :
         lambda g1, g2: f"{g1.split()[-1]}::{g2.split()[0]}"),
    ]

    for regex, builder in patterns:
        match = re.search(regex, s)
        if match:
            g1 = match.group(1).strip()
            g2 = match.group(2).strip()
            return builder(g1, g2).replace('"', '')

    return None

############################################################
def select_artifact_(self, 
                     state,
                     select_category,
                     select_artifact=None,
                     select_tags=None,
                     select_text='',
                     show_tags=False,
                     artifacts=None,
                     cmeta_params_keys=None,
                     skip_uids: bool = False,
                     sort_keys: list = None,
                     load_files: list = [],         # Attempt to load files in the selected artifact
                     space: str = '',
                     load_api: bool = False,
                     load_api_ver: int = 0,
                     load_api_class: str = None,
                     print_extra_line: bool = False,
    ):

    import os

    if load_api and not load_api_class:
        err = f'load_api == True but load_api_class is not defined in {__name__}'
        return self.cm._error(err, 1, None, self.cm.fail_on_error)

    con = state['control'].get('con', False)
    quiet = state['control'].get('quiet', False)
    inside_cli = 'cli' in state.get('origin',{})

    select_category_name = select_category['artifact_alias'] if type(select_category)==dict else str(select_category)

    if artifacts is None or type(artifacts) != list:
        p = {'category':select_category,
             'command':'find',
             'arg1':select_artifact,
             'tags':select_tags
        }

        r = self.cm.access(p)
        if r['return']>0: 
            if r['return'] != 16: return r

            r = self.cm.utils.names.parse_cmeta_name(select_category_name)
            if r['return']>0: return r

            select_category_name = r['name']['alias']

            x = '' 

            if select_artifact:
                x += f' "{select_artifact}"'

            if select_tags is not None and len(selet_tags)>0: 
                x += f' with tags "{select_tags}"'

            return {'return':16, 'error': f'couldn\'t find "{select_category_name}" artifact(s){x}'}

        artifacts = r['artifacts']

    if len(artifacts) == 1:
        new_index_int = 0

    # Continue processing artifacts
    if len(artifacts) > 1:

        if select_text == '':
            select_text = f'{space}Select {select_category_name}'

        select_text += ':'

        if con:
            if print_extra_line:
                print ('')
            print (select_text)
            print ('')

        index = 0

        xsort_keys = sort_keys.copy() if sort_keys else []

        for k in ["cmeta.sort", "cmeta_ref_parts.artifact_alias", "cmeta_ref_parts.artifact_uid"]:
            if k not in xsort_keys:
                xsort_keys.append(k)

#        sort_keys = [
#            "cmeta.sort",
#            "@cmeta.params.version-",
#            "@cmeta.params.tag-",
#            "cmeta.params.name",
#            "cmeta_ref_parts.artifact_alias",
#            "cmeta_ref_parts.artifact_uid",
#        ]

#        artifacts = sorted(
#            artifacts,
#            key=lambda a: self.cm.utils.common.build_sort_key(a, xsort_keys)
#        )

        artifacts = sorted(
            artifacts,
            key=lambda a: (
                type(self.cm.utils.common.build_sort_key(a, xsort_keys)).__name__,
                self.cm.utils.common.build_sort_key(a, xsort_keys)
            )
        )

        num_artifacts = len(artifacts)
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

                xtags = '' #'[' + ','.join(cmeta['tags']) + '] ' if show_tags else ''

                xuid = f'({uid})' if not skip_uids else ''

                text = f'{space}{index}) {x} {xtags}{xuid}'

#                if cmeta_params_keys:
#                    xparams = {}
#                    for cmeta_params_key in cmeta_params_keys:
#                        if cmeta_params_key in cmeta:
#                            uparams = cmeta[cmeta_params_key]
#                            if type(uparams) == dict:
#                                for p in sorted(uparams):
#                                    xparams[p] = str(uparams[p])
#                            else:
#                                xparams[cmeta_params_key] = str(uparams)
#                    
#                    if len(xparams)>0:
#                        for p in sorted(xparams):
#                            v = xparams[p]
#                            text += f'\n      * {p} = {v}'

                xparams = {}
                for cmeta_params_key in ['params', 'tags', 'path']:
                    if cmeta_params_key in cmeta:
                        uparams = cmeta[cmeta_params_key]
                        if type(uparams) == dict:
                            for p in sorted(uparams):
                                xparams[cmeta_params_key+'.'+p] = str(uparams[p])
                        elif type(uparams) == list:
                            xparams[cmeta_params_key] = ','.join(str(x) for x in uparams)
                        else:
                            xparams[cmeta_params_key] = str(uparams)
                
                if len(xparams)>0:
                    for p in sorted(xparams):
                        v = xparams[p]
                        text += f'\n{space}      * {p} = {v}'

                print (text)

                if cmeta_params_keys and n != num_artifacts-1:
                    print ('')

            index += 1

        if quiet:
            if con:
                print ('')
                print (f'{space}Quietly selected: 0')

            new_index_int = 0

        else:
            print ('')
            new_index = input(f'{space}Make your selection or press Enter for 0: ').strip()

            new_index_int = 0 if new_index == '' else int(new_index)

            if new_index_int < 0 or new_index_int >= index:
                return {'return':1, 'error': 'selection out of range'}

#        if con:
#            print ('')

    artifact = artifacts[new_index_int]

    result = {'return':0, 
              'artifacts': artifacts, 
              'artifact': artifact,
              'index':new_index_int,
    }

    # Check if need to load files
    if len(load_files) > 0:
        r = self.cm.utils.files.load_files(artifact['path'], load_files, self.cm.fail_on_error, logger = self.logger)
        if r['return']>0: return r

        result['loaded_files'] = r['loaded_files']

    # Check if min version
    artifact_path = artifact['path']

    cmeta = artifact['cmeta']

    cmeta_ref_parts = artifact['cmeta_ref_parts']

    artifact_alias = cmeta_ref_parts.get('artifact_alias', '')
    artifact_uid = cmeta_ref_parts['artifact_uid']
    artifact_au = artifact_alias if artifact_alias is not None and artifact_alias != '' else artifact_uid

    category_uid = cmeta_ref_parts['category_uid']
    category_alias = cmeta_ref_parts.get('category_alias', '')
    category_au = category_alias if category_alias is not None and category_alias != '' else category_uid

    result['artifact_alias'] = artifact_au
    result['artifact_uid'] = artifact_uid
    result['artifact_au'] = artifact_au

    result['category_alias'] = category_au
    result['category_uid'] = category_uid
    result['category_au'] = category_au

    # Check min cMeta versions

    xver = '1'
    if load_api_ver is not None and str(load_api_ver) != '0':
        xver = load_api_ver
    elif inside_cli or str(load_api_ver) == '0':
        if cmeta.get('last_api_version') is not None:
            xver = str(cmeta['last_api_version'])

    min_cmeta_version = cmeta.get('min_cmeta_version_api')
    if min_cmeta_version is None:
        min_cmeta_version = cmeta.get('min_cmeta_version',{}).get(xver)
   
    if min_cmeta_version is not None:
        cm_version = self.cm.__version__
        r = self.cm.utils.common.compare_versions(min_cmeta_version, cm_version)
        if r['return']>0: return r
        if r['comparison'] == '>':
            err = f'the artifact "{category_au}::{artifact_au}" requires min cMeta version "{min_cmeta_version}" but "{cm_version}" is installed'
            return self.cm._error(err, 1, None, self.cm.fail_on_error)

    # Check if need to load API
    if load_api:
        # Check version
        artifact_api_path = os.path.join(artifact_path, f'api_v{xver}.py')
        result['api_path'] = artifact_api_path

        if load_api_ver is not None and not os.path.isfile(artifact_api_path):
            err = f'customization module not found in "{artifact_api_path}"'
            return self.cm._error(err, 1, None, self.cm.fail_on_error)

        artifact_api_code = None
        if os.path.isfile(artifact_api_path):
            r = self.cm.utils.sys.load_module(artifact_api_path, 
                                              self.cm.module_cache, 
                                              fail_on_error = self.fail_on_error, 
                                              init_class=load_api_class, 
                                              cmeta=self.cm, 
                                              suffix=category_uid, 
                                              self_meta=cmeta
            )
            if r['return'] >0: 
                return self.cm._error2(r, self)

            artifact_api_code = r['cache']['initialized_class']

        result['api_code'] = artifact_api_code

    return result
