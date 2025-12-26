import os

from cmeta.category import InitCategory

class Category(InitCategory):
    """
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path = __file__, **kwargs)


    ############################################################
    def test_(self, state, arg1=None, flag1=False):
        """
        """

        self.logger.debug("RUNNING API v1 test_")

        print (f'arg1={arg1}')
        print (f'flag1={flag1}')

        return {'return':0}

    ############################################################
    def test2(self, params):
        """
        """

        self.logger.debug("RUNNING API v1 test2")

        import json
        print (json.dumps(params, indent=2))

        return {'return':0}

    ############################################################
    def create(self, params):
        """
        Create work artifact

        @base.create_
        """
        self.logger.debug("RUNNING work api v1 create")

        p = self._prepare_input_from_params(params, base = False)

        p['from_category'] = p['category']
        p['category'] = 'utils,234ce5e3262e4d52'
        p['command'] = 'create_artifact_with_date'

        return self.cm.access(p)
