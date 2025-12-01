"""
cMeta utilities.

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

    ############################################################
    def uid_(self, state):
        """
        Generate UID

        Args: None
        """

        self.logger.debug("running utils.uid")

        con = state['control'].get('con', False)

        uid = names.generate_cmeta_uid()

        if con:
            print (uid)

        return {'return':0, 'uid':uid}

    ############################################################
    def uuid_(self, state):
        """
        Generate UUID

        Args: None
        """

        import uuid

        self.logger.debug("running utils.uuid")

        con = state['control'].get('con', False)

        uuid = str(uuid.uuid4())

        if con:
            print (uuid)

        return {'return':0, 'uuid':uuid}

    ############################################################
    def find_by_cid_(self, state, arg1, ask=False):
        """
        Find artifacts by standard CID

        Args:
           arg1 (str): standard CID
           ask (bool): if True, ask for CID in a console
        """
        self.logger.debug("running utils.find_by_cid")

        con = state['control'].get('con', False)

        if ask:
            arg1 = input('Enter CID: ')

        r = names.parse_cmeta_ref(arg1, fail_on_error = self.fail_on_error)
        if r['return']>0: return r

        artifact_ref_parts = r['ref_parts']

        if self.cm.debug:
            self.logger.debug(f"artifact_ref_parts={artifact_ref_parts}")

        r = self.cm.repos.find(artifact_ref_parts)
        if r['return']>0: return r

        artifacts = r['artifacts']

        # if no artifact found, "find" function will return error
        # we need to check >1 for ambiguity
        if con:
            for artifact in artifacts:
                print (artifact['path'])

        return r

    ############################################################
    def smart_find_by_cid_(self, state, arg1, far=False, web=False, ask=False):
        """
        Find artifacts by wrapped CID

        Args:
           arg1 (str): CID that can be wrapped with some text
           ask (bool): if True, ask for CID in a console
           web (bool): if True, remove cmeta:///? from CID (web request)
           far (bool): if true, open FAR in found artifact
       
        """
        self.logger.debug("running utils.find_by_cid_smart")

        con = state['control'].get('con', False)

        if ask:
            arg1 = input('Enter complex CID: ')

        if web and arg1.startswith('cmeta:///?'):
            cid = arg1[10:]

            from urllib.parse import unquote
            cid = unquote(cid)
        else:
            cid = _extract_category_artifact(arg1) 

        if self.cm.debug:
            self.logger.debug(f"extracted_cid={cid}")

        if cid is None:
            return {'return':1, 'error':f'Could not extract CID from the input string (arg1)'}

        r = self.find_by_cid_(state, cid)
        if r['return']>0: return r

        artifacts = r['artifacts']

        path = artifacts[0]['path']

        if far:
            os.system(f'start far {path}')

        return r

    ############################################################
    def copy_text_to_clipboard_(self, state, arg1 = "", add_quotes = False, do_not_fail = True):
        """
        Copy text to clipboard

        Args:
           arg1 (str): text to copy to clipboard
           add_quotes (bool): add quotes to the text if True
        """

        return self.cm.utils.common.copy_text_to_clipboard(arg1, add_quotes)


    ############################################################
    def json2yaml_(self, state, arg1, arg2=None, force=False, f=False, sort_keys=False):
        """
        Copy text to clipboard and add quotes if needed
        Args:
           arg1 (str): input JSON file
           arg2 (str, optional): output YAML file (if None, use {input file without ext}.yaml
           force (bool, optional): if True and output file exists, overwrite it
           f (bool, optional): if True and output file exists, overwrite it
        """

        self.logger.debug("running utils json2yaml")

        con = state['control'].get('con', False)

        r = self.cm.utils.files.safe_read_file(arg1)
        if r['return'] > 0: return r

        data = r['data']

        if arg2 is None:
            arg2 = f"{os.path.splitext(arg1)[0]}.yaml"

        if os.path.isfile(arg2) and not (force or f):
            return {'return':1, 'error':f'Output file already exists (use --force or --f option to overwrite): {arg2}'} 

        r = self.cm.utils.files.safe_write_file(arg2, data, sort_keys=sort_keys)
        if r['return'] > 0: return r

        return {'return':0}


    ############################################################
    def yaml2json_(self, state, arg1, arg2=None, force=False, f=False, sort_keys=False):
        """
        Convert YAML file to JSON file
        Args:
           arg1 (str): input YAML file
           arg2 (str, optional): output JSON file (if None, use {input file without ext}.json
           force (bool, optional): if True and output file exists, overwrite it
           f (bool, optional): if True and output file exists, overwrite it
        """

        self.logger.debug("running utils yaml2json")

        con = state['control'].get('con', False)

        r = self.cm.utils.files.safe_read_file(arg1)
        if r['return'] > 0: return r

        data = r['data']

        if arg2 is None:
            arg2 = f"{os.path.splitext(arg1)[0]}.json"

        if os.path.isfile(arg2) and not (force or f):
            return {'return':1, 'error':f'Output file already exists (use --force or --f option to overwrite): {arg2}'} 

        r = self.cm.utils.files.safe_write_file(arg2, data, sort_keys=sort_keys)
        if r['return'] > 0: return r

        return {'return':0}


    ############################################################
    def pkl2json(self, params):
        """
        @self.pickle2json_
        """

        return self.pickle2json_(**params)


    ############################################################
    def pickle2json_(self, state, arg1, arg2=None, sort_keys=False):
        """
        Change date and time in files
        Args:
           arg1 (str): pickle file
           arg2 (str, optional): json file. If not specified, use base of pickle file with .json
        """

        import os
        import pickle
        import json

        con = state['control'].get('con', False)

        # Check if pickle file exists
        if not os.path.isfile(arg1):
            return {'return':1, 'error':f'Pickle file not found: {arg1}'}

        # Set default json filename if not provided
        if arg2 is None:
            base = os.path.splitext(arg1)[0]
            arg2 = f"{base}.json"

        # Load pickle file
        try:
            with open(arg1, 'rb') as f:
                data = pickle.load(f)
        except Exception as e:
            return {'return':1, 'error':f'Failed to load pickle file: {e}'}

        # Save to json file
        try:
            with open(arg2, 'w') as f:
                json.dump(data, f, sort_keys=sort_keys, indent=2)
                f.write('\n')
        except Exception as e:
            return {'return':1, 'error':f'Failed to save JSON file: {e}'}

        if con:
            print (f'Successfully converted {arg1} to {arg2}')

        return {'return':0, 'json_file': arg2}

    ############################################################
    def json2pickle_(self, state, arg1, arg2=None):
        """
        Convert JSON file to pickle file
        Args:
           arg1 (str): json file
           arg2 (str, optional): pickle file. If not specified, use base of json file with .pkl
        """

        import os
        import pickle
        import json

        con = state['control'].get('con', False)

        # Check if json file exists
        if not os.path.isfile(arg1):
            return {'return':1, 'error':f'JSON file not found: {arg1}'}

        # Set default pickle filename if not provided
        if arg2 is None:
            base = os.path.splitext(arg1)[0]
            arg2 = f"{base}.pkl"

        # Load json file
        try:
            with open(arg1, 'r') as f:
                data = json.load(f)
        except Exception as e:
            return {'return':1, 'error':f'Failed to load JSON file: {e}'}

        # Save to pickle file
        try:
            with open(arg2, 'wb') as f:
                pickle.dump(data, f)
        except Exception as e:
            return {'return':1, 'error':f'Failed to save pickle file: {e}'}

        if con:
            print (f'Successfully converted {arg1} to {arg2}')

        return {'return':0, 'pickle_file': arg2}

    ############################################################
    def utf8sig_to_utf8_(self, state, arg1, arg2=None):
        """
        Convert UTF-8 with BOM (utf-8-sig) file to standard UTF-8
        Args:
           arg1 (str): input file (UTF-8 with BOM)
           arg2 (str, optional): output file. If None, overwrites input file and creates .bak backup
        """

        import os
        import shutil

        con = state['control'].get('con', False)

        # Check if input file exists
        if not os.path.isfile(arg1):
            return {'return':1, 'error':f'Input file not found: {arg1}'}

        # Read file with utf-8-sig encoding (strips BOM automatically)
        try:
            with open(arg1, 'r', encoding='utf-8-sig') as f:
                content = f.read()
        except Exception as e:
            return {'return':1, 'error':f'Failed to read file: {e}'}

        # Determine output file
        if arg2 is None:
            # Create backup of original file
            backup_file = f"{arg1}.bak"
            try:
                shutil.copy2(arg1, backup_file)
                if con:
                    print(f'Created backup: {backup_file}')
            except Exception as e:
                return {'return':1, 'error':f'Failed to create backup: {e}'}
            arg2 = arg1

        # Write file with standard utf-8 encoding (without BOM)
        try:
            with open(arg2, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception as e:
            return {'return':1, 'error':f'Failed to write file: {e}'}

        if con:
            print(f'Successfully converted {arg1} to UTF-8 (without BOM)')
            if arg2 != arg1:
                print(f'Output saved to: {arg2}')

        return {'return':0, 'output_file': arg2}


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
        (r'([\w.,\-\s"]+)::([\w.,\-\s"]+)',
         lambda g1, g2: f"{g1}::{g2}"),
        (r'([\w.,\-\s"]+):([\w.,\-\s"]+)',
         lambda g1, g2: f"{g1.split()[-1]}::{g2.split()[0]}"),
    ]

    for regex, builder in patterns:
        match = re.search(regex, s)
        if match:
            g1 = match.group(1).strip()
            g2 = match.group(2).strip()
            return builder(g1, g2).replace('"', '')

    return None
