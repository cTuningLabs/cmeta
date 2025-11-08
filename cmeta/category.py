"""
Managing Category class

cMeta author and developer: (C) 2025 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import logging
import os
from pathlib import Path

from . import utils
from .utils.common import _error

class InitCategory:
    """
    Initialize Category without artifact management functions
    """

    def __init__(self,
                 cm = None,
                 module_file_path = None,
                 logger: logging.Logger = None):
        """
        """

        if cm is None:
            from .core import CMeta
            cm = CMeta()

        self.cm = cm
        self._error = cm._error
        self.fail_on_error = cm.fail_on_error

        if module_file_path is None:
            # If base init
            module_file_path = __file__
            module_name = 'category'
            category_module_name = module_name

            module_path = os.path.dirname(module_file_path)
            path = module_path

            extra_text = 'GLOBAL '

        else:
            file_path = Path(module_file_path)

            module_name = file_path.stem

            path_parts = file_path.parts
        
            category_module_name = '#' + path_parts[-3] + '#' + path_parts[-2] + '.' + module_name

            module_path = os.path.dirname(module_file_path)
            path = os.path.dirname(module_path)

            extra_text = ''

        self.module_file_path = module_file_path
        self.module_path = module_path
        self.module_name = module_name
        self.path = path
        self.category_module_name = category_module_name
        self.exclude_base_functions = False

        # Create a child logger that inherits CMeta's configuration
        self.logger = logger if logger is not None else self.cm.logger.getChild(self.category_module_name)

        if self.cm.debug:
            import inspect

            stack = inspect.stack()

            caller_frame = stack[1]

            self.logger.debug(f"Initializing {extra_text}category class from: {caller_frame.filename}:{caller_frame.lineno}")

    def _prepare_input_from_params(self, params, base=False):
        """
        """

        state = params['state']

        p = params.copy()

        p['category'] = state['category']
        p['command'] = state['command']
        p['con'] = state['control']['con']

        if base:
            p['base'] = True

        return p

    def _prepare_input_from_state(self, state, base=False):
        """
        """

        p = {}

        p['category'] = state['category']
        p['command'] = state['command']
        p['con'] = state['control']['con']

        if base:
            p['base'] = True

        return p
