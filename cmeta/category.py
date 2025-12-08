"""
Category Manager class

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
        """Initialize the category base class without artifact management functions.
        
        Args:
            cm: CMeta instance. If None, creates a new one.
            module_file_path: Path to the category module file. If None, uses base category.
            logger: Logger instance. If None, uses CMeta's logger.
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

    def _prepare_input_from_params(self, params, extra={}, base=False):
        """Prepare input dictionary from params for category command execution.
        
        Extracts relevant information from params and state, adds extra parameters,
        and prepares a clean input dictionary for command execution.
        
        Args:
            params: Dictionary containing parameters and state.
            extra: Additional parameters to merge into the result.
            base: If True, adds 'base': True flag to call base category commands.
            
        Returns:
            dict: Prepared input dictionary with category, command, and control flags.
        """

        import copy

        state = params['state']

        p = copy.deepcopy(params)

        p.update(extra)

        p['category'] = state['category']
        p['command'] = state['command']
        p['con'] = state['control']['con']

        if base:
            p['base'] = True

        return p

    def _prepare_input_from_state(self, state, base=False):
        """Prepare input dictionary from state for category command execution.
        
        Extracts category, command, and control information from state to create
        a minimal input dictionary for command execution.
        
        Args:
            state: State dictionary containing category, command, and control info.
            base: If True, adds 'base': True flag to call base category commands.
            
        Returns:
            dict: Prepared input dictionary with category, command, and control flags.
        """

        p = {}

        p['category'] = state['category']
        p['command'] = state['command']
        p['con'] = state['control']['con']

        if base:
            p['base'] = True

        return p
