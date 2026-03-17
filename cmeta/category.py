"""
Category Manager class

cMeta author and developer: (C) 2025-2026 Grigori Fursin

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

    def __init__(
        self,
        cm = None,  # CMeta instance. If None, creates a new one.
        module_file_path = None,  # Path to the category module file. If None, uses base category.
        logger: logging.Logger = None,  # Logger instance. If None, uses CMeta's logger.
    ):
        """
            Initialize the category base class without artifact management functions.

            Args:
                cm: CMeta instance. If None, creates a new one.
                module_file_path: Path to the category module file. If None, uses base category.
                logger: Logger instance. If None, uses CMeta's logger.

            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
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

            if module_name.startswith('category_api_v'):
                # Internal name
                x = ''
            else:
                path_parts = file_path.parts
                x = '___' + path_parts[-3] + '___.' + path_parts[-2] + '.'

            category_module_name = x + module_name

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

    def _prepare_input_from_params(
        self,
        params,  # Dictionary containing parameters and ctx.
        extra = {},  # Additional parameters to merge into the result.
        base = False,  # If True, adds 'base': True flag to call base category commands.
    ):
        """
            Prepare input dictionary from params for category command execution.

            Extracts relevant information from params and ctx, adds extra parameters,
            and prepares a clean input dictionary for command execution.

            Args:
                params: Dictionary containing parameters and ctx.
                extra: Additional parameters to merge into the result.
                base: If True, adds 'base': True flag to call base category commands.

            Returns:
                dict: Prepared input dictionary with category, command, and control flags.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        import copy

        ctx = params['ctx']

        p = copy.deepcopy(params)

        p.update(extra)

        p['category'] = ctx['category']
        p['command'] = ctx['command']

        for k in ['con', 'verbose', 'quiet']:
            if k in ctx['control']: 
                p[k] = ctx['control'][k]

        if base:
            p['base'] = True

        return p

    def _prepare_input_from_ctx(
        self,
        ctx,  # Context dictionary containing category, command, and control info.
        base = False,  # If True, adds 'base': True flag to call base category commands.
    ):
        """
            Prepare input dictionary from ctx for category command execution.

            Extracts category, command, and control information from ctx to create
            a minimal input dictionary for command execution.

            Args:
                ctx: Context dictionary containing category, command, and control info.
                base: If True, adds 'base': True flag to call base category commands.

            Returns:
                dict: Prepared input dictionary with category, command, and control flags.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        p = {}

        p['category'] = ctx['category']
        p['command'] = ctx['command']

        for k in ['con', 'verbose', 'quiet']:
            if k in ctx['control']: 
                p[k] = ctx['control'][k]

        if base:
            p['base'] = True

        return p
