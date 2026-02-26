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
        ctx,  # Execution context dictionary with category, command, and control data.
        arg1 = None,  # First positional argument from command input.
        flag1 = False,  # Input parameter used by this function.
    ):
        """
            Args:
                ctx: Execution context dictionary with category, command, and control data.
                arg1: First positional argument from command input.
                flag1: Input parameter used by this function.
            Returns:
                dict: Operation result.
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
        params,  # Input parameters dictionary.
    ):
        """
            Args:
                params: Input parameters dictionary.
            Returns:
                dict: Operation result.
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
            Create work artifact

            @base.create_

            Args:
                params: Input parameters dictionary.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """
        self.logger.debug("RUNNING work api v1 create")

        p = self._prepare_input_from_params(params, base = False)

        p['from_category'] = p['category']
        p['category'] = self.cmeta['uses_categories']['utils']
        p['command'] = 'create_artifact_with_date'

        return self.cm.access(p)
