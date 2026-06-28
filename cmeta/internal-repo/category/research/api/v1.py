"""
cMeta research functions

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os

from cmeta.category import InitCategory

class Category(InitCategory):
    """
    """

    def __init__(
        self,
        *args,  # Positional argument value.
        **kwargs,  # Value for kwargs.
    ):
        """
        __init__ function.

        Args:
            *args: Positional argument value.
            **kwargs: Value for kwargs.

        Returns:
            dict: Operation result.

        Raises:
            Exception: Propagated runtime errors, if any.
        """
        super().__init__(*args, module_file_path = __file__, **kwargs)


    ############################################################
    def test_(
        self,
        ctx: dict,  # cMeta context.
        arg1: str = None,  # Test argument 1.
        flag1: bool = False,  # Test flag 1.
    ):
        """
            Test function.

            Args:
                ctx (dict): cMeta context.
                arg1 (str | None): Test argument 1.
                flag1 (bool): Test flag 1.

            Returns:
                dict: Dictionary with 'return': 0.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        self.logger.debug("RUNNING API v1 test_")

        print (f'arg1={arg1}')
        print (f'flag1={flag1}')

        return {'return':0}

    ############################################################
    def test2(
        self,
        params: dict,  # cMeta parameters.
    ):
        """
            Test function 2.

            Args:
                params (dict): cMeta parameters.

            Returns:
                dict: Dictionary with 'return': 0.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        self.logger.debug("RUNNING API v1 test2")

        import json
        print (json.dumps(params, indent=2))

        return {'return':0}

    ############################################################
    def create(
        self,
        params,  # Input parameters dictionary.
    ):
        """
            Create research artifact

            @base.create_

            Args:
                params: Input parameters dictionary.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """
        self.logger.debug("RUNNING research api v1 create")

        p = self._prepare_input_from_params(params, base = False)

        p['from_category'] = p['category']
        p['category'] = self.cmeta['uses_categories']['utils']
        p['command'] = 'create_artifact_with_date'

        return self.cm.access(p)
