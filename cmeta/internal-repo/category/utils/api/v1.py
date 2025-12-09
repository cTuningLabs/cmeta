"""
cMeta misc utilities

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
    def uid_(
        self,
        state           # [dict] cMeta state object
    ):
        """
        Generate UID

        Args:
            state (dict): cMeta state object.
        """

        self.logger.debug("running utils.uid")

        con = state['control'].get('con', False)

        uid = names.generate_cmeta_uid()

        if con:
            print (uid)

        return {'return':0, 'uid':uid}

    ############################################################
    def uuid_(
        self,
        state           # [dict] cMeta state object
    ):
        """
        Generate UUID

        Args:
            state (dict): cMeta state object.
        """

        import uuid

        self.logger.debug("running utils.uuid")

        con = state['control'].get('con', False)

        uuid = str(uuid.uuid4())

        if con:
            print (uuid)

        return {'return':0, 'uuid':uuid}

    ############################################################
    def find_by_cid_(
        self,
        state,          # [dict] cMeta state object
        arg1,           # [str] Standard CID
        ask = False     # [bool] If True, ask for CID in console
    ):
        """
        Find artifacts by standard CID

        Args:
            state (dict): cMeta state object.
            arg1 (str): Standard CID.
            ask (bool): If True, ask for CID in console.
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
    def smart_find_by_cid_(
        self,
        state,              # [dict] cMeta state object
        arg1 = None,        # [str] CID that can be wrapped with some text
        far = False,        # [bool] If True, open FAR in found artifact
        web = False,        # [bool] If True, remove cmeta:///? from CID (web request)
        ask = False,        # [bool] If True, ask for CID in console
        cid = None          # [str] Direct CID to use
    ):
        """
        Find artifacts by wrapped CID

        Args:
            state (dict): cMeta state object.
            arg1 (str): CID that can be wrapped with some text.
            far (bool): If True, open FAR in found artifact.
            web (bool): If True, remove cmeta:///? from CID (web request).
            ask (bool): If True, ask for CID in console.
            cid (str): Direct CID to use.
        """
        self.logger.debug("running utils.find_by_cid_smart")

        con = state['control'].get('con', False)

        if ask:
            arg1 = input('Enter complex CID: ')

        if web and arg1.startswith('cmeta:///?'):
            cid = arg1[10:]

            from urllib.parse import unquote
            cid = unquote(cid)
        elif cid is not None:
            cid = _extract_category_artifact(cid) 
        elif arg1 is not None:
            cid = _extract_category_artifact(arg1) 
        else:
            return {'return':1, 'error': 'CID is not specified'}

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
    def copy_text_to_clipboard_(
        self,
        state,                  # [dict] cMeta state object
        arg1 = "",              # [str] Text to copy to clipboard
        add_quotes = False,     # [bool] Add quotes to the text if True
        do_not_fail = True      # [bool] Do not fail on error if True
    ):
        """
        Copy text to clipboard

        Args:
            state (dict): cMeta state object.
            arg1 (str): Text to copy to clipboard.
            add_quotes (bool): Add quotes to the text if True.
            do_not_fail (bool): Do not fail on error if True.
        """

        return self.cm.utils.common.copy_text_to_clipboard(arg1, add_quotes)


    ############################################################
    def json2yaml_(
        self,
        state,                  # [dict] cMeta state object
        arg1,                   # [str] Input JSON file
        arg2 = None,            # [str] Output YAML file (if None, use {input file without ext}.yaml)
        force = False,          # [bool] If True and output file exists, overwrite it
        f = False,              # [bool] If True and output file exists, overwrite it
        sort_keys = False       # [bool] Sort keys in output if True
    ):
        """
        Convert JSON file to YAML file

        Args:
            state (dict): cMeta state object.
            arg1 (str): Input JSON file.
            arg2 (str): Output YAML file (if None, use {input file without ext}.yaml).
            force (bool): If True and output file exists, overwrite it.
            f (bool): If True and output file exists, overwrite it.
            sort_keys (bool): Sort keys in output if True.
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
    def yaml2json_(
        self,
        state,                  # [dict] cMeta state object
        arg1,                   # [str] Input YAML file
        arg2 = None,            # [str] Output JSON file (if None, use {input file without ext}.json)
        force = False,          # [bool] If True and output file exists, overwrite it
        f = False,              # [bool] If True and output file exists, overwrite it
        sort_keys = False       # [bool] Sort keys in output if True
    ):
        """
        Convert YAML file to JSON file

        Args:
            state (dict): cMeta state object.
            arg1 (str): Input YAML file.
            arg2 (str): Output JSON file (if None, use {input file without ext}.json).
            force (bool): If True and output file exists, overwrite it.
            f (bool): If True and output file exists, overwrite it.
            sort_keys (bool): Sort keys in output if True.
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
    def pickle2json_(
        self,
        state,                  # [dict] cMeta state object
        arg1,                   # [str] Pickle file
        arg2 = None,            # [str] JSON file (if not specified, use base of pickle file with .json)
        sort_keys = False       # [bool] Sort keys in output if True
    ):
        """
        Convert pickle file to JSON file

        Args:
            state (dict): cMeta state object.
            arg1 (str): Pickle file.
            arg2 (str): JSON file (if not specified, use base of pickle file with .json).
            sort_keys (bool): Sort keys in output if True.
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
    def json2pickle_(
        self,
        state,              # [dict] cMeta state object
        arg1,               # [str] JSON file
        arg2 = None         # [str] Pickle file (if not specified, use base of json file with .pkl)
    ):
        """
        Convert JSON file to pickle file

        Args:
            state (dict): cMeta state object.
            arg1 (str): JSON file.
            arg2 (str): Pickle file (if not specified, use base of json file with .pkl).
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
    def utf8sig_to_utf8_(
        self,
        state,              # [dict] cMeta state object
        arg1,               # [str] Input file (UTF-8 with BOM)
        arg2 = None         # [str] Output file (if None, overwrites input file and creates .bak backup)
    ):
        """
        Convert UTF-8 with BOM (utf-8-sig) file to standard UTF-8

        Args:
            state (dict): cMeta state object.
            arg1 (str): Input file (UTF-8 with BOM).
            arg2 (str): Output file (if None, overwrites input file and creates .bak backup).
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
