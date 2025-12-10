"""
cMeta log functions

cMeta author and developer: (C) 2025 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os

from cmeta.category import InitCategory

class Category(InitCategory):
    """
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path = __file__, **kwargs)


    ############################################################
    def test_(
            self,
            state: dict,             # cMeta state
            arg1: str = None,        # Test argument 1
            flag1: bool = False      # Test flag 1
    ):
        """
        Test function.
        
        Args:
            state (dict): cMeta state.
            arg1 (str | None): Test argument 1.
            flag1 (bool): Test flag 1.
            
        Returns:
            dict: Dictionary with 'return': 0.
        """

        self.logger.debug("RUNNING API v1 test_")

        print (f'arg1={arg1}')
        print (f'flag1={flag1}')

        return {'return':0}

    ############################################################
    def test2(
            self,
            params: dict  # cMeta parameters
    ):
        """
        Test function 2.
        
        Args:
            params (dict): cMeta parameters.
            
        Returns:
            dict: Dictionary with 'return': 0.
        """

        self.logger.debug("RUNNING API v1 test2")

        import json
        print (json.dumps(params, indent=2))

        return {'return':0}

    ############################################################
    def record_(
            self,
            state: dict,
            arg1: str,
            paths: list = None,
            data: dict = None,
    ):
        """
        Record log.
        
        Args:
            state (dict): cMeta state.
            arg1 (str): Log name.
            paths (list | None): Additional path segments.
            data (dict | None): Log data to write.
            
        Raises:
            Exception: If artifact access fails or file write fails.
            
        Returns:
            dict: Dictionary with 'return': 0 on success, >0 on error.
        """

        self.logger.debug("RUNNING log v1 record_")

        r = self.cm.access({'category': state['category'], 
                            'command': 'get', 
                            'base': True,
                            'arg1': arg1,
                           })
        if r['return']>0: return r

        path = r['artifact']['path']

        # Prepare extra paths
        if paths is not None and len(paths)>0:
            path = os.path.join(path, *paths)

        # Generate timestamp
        r = self.cm.utils.common.generate_timestamp()
        if r['return']>0: return r

        timestamp = r['timestamp']

        paths2 = [timestamp[:8], timestamp[9:11]]

        path = os.path.join(path, *paths2)

        if not os.path.isdir(path):
            os.makedirs(path)

        filename = timestamp + '.json'

        filename_with_path = os.path.join(path, filename)

        r = self.cm.utils.files.write_file(filename_with_path, data)
        if r['return']>0: return r

        return {'return':0}
