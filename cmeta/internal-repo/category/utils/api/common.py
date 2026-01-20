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
    ):

    con = state['control'].get('con', False)
    quiet = state['control'].get('quiet', False)

    p = {'category':select_category,
         'command':'find',
         'arg1':select_artifact,
         'tags':select_tags
    }

    select_category_name = select_category['artifact_alias']

    r = self.cm.access(p)
    if r['return']>0: 
        if r['return'] != 16: return r

        xtags = '' if (select_tags == None or len(select_tags)==0) else f' with tags "{select_tags}"'

        return {'return':16, 'error': f'couldn\'t find "{select_category_name}" artifacts{xtags}'}

    artifacts = r['artifacts']

    if len(artifacts) == 1:
        new_index_int = 0

    # Continue processing artifacts
    if len(artifacts) > 1:

        if select_text == '':
            select_text = f'Select {select_category_name}'

        select_text += ':'

        if con:
            print (select_text)
            print ('')

        index = 0

        artifacts = sorted(artifacts, key = lambda artifact: (artifact['cmeta'].get('sort', 0),
                                                              artifact['cmeta'].get('name', ''),
                                                              artifact['cmeta_ref_parts']['artifact_alias'],
                                                              artifact['cmeta_ref_parts']['artifact_uid']))

        for a in artifacts:
            cmeta_ref_parts = a['cmeta_ref_parts']
            cmeta = a['cmeta']
            path = a['path']

            name = cmeta.get('name', '')
            alias = cmeta_ref_parts['artifact_alias']
            uid = cmeta_ref_parts['artifact_uid']

            x = name if name != '' else alias

            xtags = '[' + ','.join(cmeta['tags']) + '] ' if show_tags else ''

            text = f'{index}) {x} {xtags}({uid})'

            if con:
                print (text)

            index += 1

        if quiet:
            if con:
                print ('')
                print ('Quietly selected 0')

            new_index_int = 0

        else:
            print ('')

            new_index = input('Make your selection or press Enter for 0: ').strip()

            new_index_int = 0 if new_index == '' else int(new_index)

            if new_index_int < 0 or new_index_int >= index:
                return {'return':1, 'error': 'selection out of range'}

    artifact = artifacts[new_index_int]

    return {'return':0, 
            'artifacts': artifacts, 
            'artifact': artifact,
            'index':new_index_int}
