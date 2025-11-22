"""
CMeta asynchronous wrapper for the core class

cMeta author and developer: (C) 2025 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

# core_async.py

import os
import asyncio
import logging
from functools import partial
from concurrent.futures import ProcessPoolExecutor

from .core import CMeta

logger = logging.getLogger(__name__)

_cmeta_instance = None
_cmeta_index = 0

def _get_cmeta(logger_override=None, **kwargs):
    """
    Lazy initialization of CMeta instances per process, similar to FastAPI initialization.
    """
    global _cmeta_instance, _cmeta_index

    if _cmeta_instance is None:
        # If an external logger is provided, override logging config BEFORE init logic
        if logger_override is not None:
            kwargs["logger"] = logger_override   # injected into CMeta init params

        _cmeta_instance = CMeta(**kwargs)
        _cmeta_index += 1
        logger.info(f"Initializing CMeta instance #{_cmeta_index} in process {os.getpid()}")

    return _cmeta_instance


class CMetaAsync:
    def __init__(self, max_workers=None, logger=None, loop=None, **kwargs):
        """
        Async wrapper around CMeta that supports external logging and multiprocessing.
        
        Args:
            logger: (optional) external logger to reuse (e.g. FastAPI app logger)
            max_workers: size of ProcessPool
            **kwargs: params passed directly to CMeta
        """

        self._loop = loop or asyncio.get_event_loop()
        self._executor = ProcessPoolExecutor(max_workers=max_workers)
        self._cmeta_kwargs = kwargs

        # Store external logger for later use
        self._logger_override = logger

        logger_name = logger.name if logger else "internal"
        logging.getLogger(__name__).info(
            f"CMetaAsync initialized in PID {os.getpid()} | max_workers={max_workers} | logger={logger_name}"
        )

    async def access(self, params):
        func = partial(self._call_sync, params)

        try:
            return await self._loop.run_in_executor(self._executor, func)
        except Exception as e:
            logging.getLogger(__name__).exception("Error executing CMetaAsync access")
            return {"return": 99, "error": f"CMetaAsync internal error: {e}"}

    def _call_sync(self, params):
        # Here we lazily initialize CMeta inside the worker process
        cmeta = _get_cmeta(logger_override=self._logger_override, **self._cmeta_kwargs)
        return cmeta.access(params)
