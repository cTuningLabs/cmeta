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

    ):

    con = state['control'].get('con', False)
    quiet = state['control'].get('quiet', False)

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

        artifacts = sorted(
            artifacts,
            key=lambda a: self.cm.utils.common.build_sort_key(a, xsort_keys)
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
                            xparams[cmeta_params_key] = ','.join(uparams)
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

    if len(load_files) > 0:
        r = self.cm.utils.files.load_files(artifact['path'], load_files, self.cm.fail_on_error)
        if r['return']>0: return r

        result['loaded_files'] = r['loaded_files']

    return result
