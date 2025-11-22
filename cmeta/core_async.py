"""
CMeta asynchronous wrapper for the core class

cMeta author and developer: (C) 2025 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import asyncio
import logging
from functools import partial
from concurrent.futures import ProcessPoolExecutor

from .core import CMeta

# This logger is ONLY the module-level fallback.
module_logger = logging.getLogger(__name__)

# Per-process persistent CMeta instance
_cmeta_instance = None
_cmeta_index = 0


def _configure_worker_logging(logger_override=None):
    """
    Ensure that worker processes log using the provided external logger.
    On Windows + multiprocessing, logging config does NOT carry over automatically.
    """
    if logger_override is None:
        return  # fallback to default logging behavior

    # Clear default handler to avoid duplicated logs
    logging.root.handlers = []

    # Copy handlers from provided logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logger_override.level)

    for handler in logger_override.handlers:
        root_logger.addHandler(handler)


def _get_cmeta(logger_override=None, **kwargs):
    """
    Lazy initialization of CMeta per multiprocessing worker.
    Mirrors FastAPI logic where the instance is created once per process.
    """
    global _cmeta_instance, _cmeta_index

    if _cmeta_instance is None:
        # Initialize CMeta normally
        cmeta = CMeta(**kwargs)

        # Override logger if external logger was passed
        if logger_override is not None:
            cmeta.logger = logger_override

        _cmeta_instance = cmeta
        _cmeta_index += 1

        # Log initialization (using worker logging config)
        module_logger.info(
            f"[PID {os.getpid()}] Created CMeta instance #{_cmeta_index}"
        )

    return _cmeta_instance


def _access_worker(params, kwargs, logger_override):
    """
    Standalone function executed inside the ProcessPool.
    Must NOT reference `self`, or use bound methods → prevents pickling errors.
    """
    _configure_worker_logging(logger_override)
    cmeta = _get_cmeta(logger_override=logger_override, **kwargs)
    return cmeta.access(params)


class CMetaAsync:
    """
    Async wrapper around CMeta using multiprocessing to avoid blocking
    event loop in FastAPI or asyncio-based services.
    """

    def __init__(self, max_workers=None, logger=None, loop=None, **kwargs):
        # Store external logger
        self._logger = logger or logging.getLogger(__name__)

        # Event loop + executor
        self._loop = loop or asyncio.get_event_loop()
        self._executor = ProcessPoolExecutor(max_workers=max_workers)

        # Store constructor args for CMeta
        self._cmeta_kwargs = kwargs
        self._logger_override = logger

        self._logger.info(
            f"[PID {os.getpid()}] CMetaAsync initialized | max_workers={max_workers}"
        )

    async def access(self, params):
        """
        Asynchronous non-blocking wrapper that runs CMeta.access() in a worker process.
        """
        func = partial(_access_worker, params, self._cmeta_kwargs, self._logger_override)

        try:
            return await self._loop.run_in_executor(self._executor, func)

        except Exception as e:
            self._logger.exception("Error executing CMetaAsync access")
            return {"return": 99, "error": f"CMetaAsync internal error: {e}"}

    def shutdown(self):
        """
        Optional: Clean shutdown of executor (can be tied to FastAPI shutdown event).
        """
        self._logger.info("Shutting down CMetaAsync executor...")
        self._executor.shutdown(wait=True)
