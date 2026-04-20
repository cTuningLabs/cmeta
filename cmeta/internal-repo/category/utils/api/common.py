"""
CMeta common repo functions

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

###################################################################################################
def _extract_category_artifact(
    s: str,  # Value for s.
) -> str:
    """
    _extract_category_artifact function.

    Args:
        s (str): Value for s.

    Returns:
        str: Result value.

    Raises:
        Exception: Propagated runtime errors, if any.
    """
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
def select_artifact_(
    self,
    ctx,  # Input dictionary used by this function.
    select_category,  # Value for select category.
    select_artifact = None,  # Value for select artifact.
    select_tags = None,  # Value for select tags.
    select_text = '',  # Value for select text.
    select_match = None, # Value for select dict.
    select_match_empty_version = None, # Value for match empty version.
    show_tags = False,  # Value for show tags.
    artifacts = None,  # Value for artifacts.
    cmeta_params_keys = None,  # Value for cmeta params keys.
    skip_uids: bool = False,  # Value for skip uids.
    sort_keys: list = None,  # Value for sort keys.
    load_files: list = [],  # Value for load files.
    space: str = '',  # Value for space.
    load_api: bool = False,  # Value for load api.
    load_api_ver: str = None,  # Value for load api ver.
    load_api_class: str = None,  # Value for load api class.
    inside_cli: bool = None, # True if calls were from inside CLI,
                             # in such case, attempt to load the last available version of code
                             # if load_api is True
    print_extra_line: bool = False,  # Value for print extra line.
    allow_skip: bool = False, # If True, add -1 to skip selection
    allow_multiple: bool = False, # If True, allow multiple selections separated by comma
):

    """
    select_artifact_ function.

    Args:
        ctx: Input dictionary used by this function.
        select_category: Value for select category.
        select_artifact: Value for select artifact.
        select_tags: Value for select tags.
        select_text: Value for select text.
        select_match: Value for select dict.
        select_match_empty_version: # Value for match empty version.
        show_tags: Value for show tags.
        artifacts: Value for artifacts.
        cmeta_params_keys: Value for cmeta params keys.
        skip_uids (bool): Value for skip uids.
        sort_keys (list): Value for sort keys.
        load_files (list): Value for load files.
        space (str): Value for space.
        load_api (bool): Value for load api.
        load_api_ver (int): Value for load api ver.
        load_api_class (str): Value for load api class.
        print_extra_line (bool): Value for print extra line.

    Returns:
        dict: Operation result.

    Raises:
        Exception: Propagated runtime errors, if any.
    """
    import os

    if load_api and not load_api_class:
        return self.cm.error(f'load_api == True but load_api_class is not defined in {__name__}')

    con = ctx['control'].get('con', False)
    quiet = ctx['control'].get('quiet', False)
    if inside_cli is None:
        inside_cli = 'cli' in ctx.get('origin',{})

    select_category_name = select_category['artifact_alias'] if type(select_category)==dict else str(select_category)

    if artifacts is None or type(artifacts) != list:
        p = {'category':select_category,
             'command':'find',
             'arg1':select_artifact,
             'tags':select_tags
        }

        if select_match:
            p['match'] = select_match

        if select_match_empty_version is not None:
            p['select_match_empty_version'] = select_match_empty_version

        r = self.cm.access(p)
        if r['return']>0: 
            if r['return'] != 16: return r

            r = self.cm.utils.names.parse_cmeta_name(select_category_name)
            if r['return']>0: return r

            select_category_name = r['name']['alias']

            x = '' 

            if select_artifact:
                x += f' "{select_artifact}"'

            if select_tags is not None and len(select_tags)>0: 
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
            indexes = [0]

        else:
            if con:
                print ('')

                x = ', use -1 to skip selection' if allow_skip else ''
                new_index = input(f'{space}Make your selection{x} or press Enter for 0: ').strip()
            else:
                new_index = ''

            if allow_multiple:
                if new_index == '':
                    indexes = [0]
                else:
                    r = self.cm.utils.common.normalize_tags(new_index)
                    if self.cm.catch_error(r): return r
                    
                    indexes = r['tags']
                    indexes_int = []

                    for new_index in indexes:
                        new_index_int = 0 if new_index == '' else int(new_index)
                        if new_index_int < 0 or new_index_int >= index:
                            return {'return':1, 'error': f'selection "{new_index_int}" out of range'}

                        indexes_int.append(new_index_int)

                    indexes = sorted(indexes_int)
            else:
                new_index_int = 0 if new_index == '' else int(new_index)

                if allow_skip and new_index_int == -1:
                    return {'return':0, 'skipped': True}

                if new_index_int < 0 or new_index_int >= index:
                    return {'return':1, 'error': f'selection "{new_index_int}" out of range'}


    result = {
      'return':0, 
      'artifacts': artifacts, 
    }

    if allow_multiple:
        result['indexes'] = indexes

    else:
        artifact = artifacts[new_index_int]
        result['artifact'] = artifact     
        result['index'] = new_index_int

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

    #    xver = '1'
    #    if load_api_ver is not None and str(load_api_ver) != '0':
    #        xver = load_api_ver
    #    elif inside_cli or str(load_api_ver) == '0':
    #        if cmeta.get('last_api_version') is not None:
    #            xver = str(cmeta['last_api_version'])

        xver = '1'
        if load_api_ver is not None:
            xver = str(load_api_ver)
        elif 'last_api_version' in cmeta:
            xver = cmeta['last_api_version']

        min_cmeta_version = cmeta.get('min_cmeta_version_api')
        if min_cmeta_version is None:
            min_cmeta_version = cmeta.get('min_cmeta_version',{}).get(xver)
       
        if min_cmeta_version is not None:
            cm_version = self.cm.__version__
            r = self.cm.utils.common.compare_versions(min_cmeta_version, cm_version)
            if r['return']>0: return r
            if r['comparison'] == '>':
                err = f'the artifact "{category_au}::{artifact_au}" requires min cMeta version "{min_cmeta_version}" but "{cm_version}" is installed'
                return self.cm.error(err)

        # Check if need to load API
        if load_api:
            # Check version
            artifact_api_path = os.path.join(artifact_path, f'api_v{xver}.py')
            result['api_path'] = artifact_api_path

            if (load_api_ver is not None or xver != '1') and not os.path.isfile(artifact_api_path):
                return self.cm.error(f'customization module not found in "{artifact_api_path}"')

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
                if self.cm.catch_error(r): return r

                artifact_api_code = r['cache']['initialized_class']

                result['load_api_ver_resolved'] = xver

            result['api_code'] = artifact_api_code

    return result
