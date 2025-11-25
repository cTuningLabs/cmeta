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


def _get_cmeta(**kwargs):
    """
    Lazy initialization of CMeta per multiprocessing worker.
    Mirrors FastAPI logic where the instance is created once per process.
    """
    global _cmeta_instance, _cmeta_index

    if _cmeta_instance is None:
        # Initialize CMeta normally
        cmeta = CMeta(**kwargs)

        _cmeta_instance = cmeta
        _cmeta_index += 1

        # Log initialization (using worker logging config)
        module_logger.info(
            f"[PID {os.getpid()}] Created CMeta instance #{_cmeta_index}"
        )

    return _cmeta_instance


def _access_worker(params, kwargs):
    """
    Standalone function executed inside the ProcessPool.
    Must NOT reference `self`, or use bound methods → prevents pickling errors.
    """
    cmeta = _get_cmeta(**kwargs)
    return cmeta.access(params)


class CMetaAsync(CMeta):
    """
    Async wrapper around CMeta using multiprocessing to avoid blocking
    event loop in FastAPI or asyncio-based services.

    Inherits all CMeta methods while providing async wrappers for blocking operations.
    """

    def __init__(self, max_workers=None, logger=None, loop=None, **kwargs):
        # Initialize parent CMeta
        super().__init__(**kwargs)

        # Store external logger (use parent's logger if not provided)
        self._logger = logger or self.logger

        # Event loop + executor
        self._loop = loop or asyncio.get_event_loop()
        self._executor = ProcessPoolExecutor(max_workers=max_workers)

        # Store constructor args for CMeta workers
        self._cmeta_kwargs = kwargs

        self._logger.info(
            f"[PID {os.getpid()}] CMetaAsync initialized | max_workers={max_workers}"
        )

    async def access(self, params):
        """
        Asynchronous non-blocking wrapper that runs CMeta.access() in a worker process.
        """
        func = partial(_access_worker, params, self._cmeta_kwargs)

        try:
            return await self._loop.run_in_executor(self._executor, func)

        except Exception as e:
            self._logger.exception("Error executing CMetaAsync access")
            return {"return": 99, "error": f"CMetaAsync internal error: {e}"}

    def access_sync(self, params):
        """
        Synchronous access using the inherited CMeta.access() method.
        Use this when you're already in a worker thread/process.
        """
        return super().access(params)

    def shutdown(self):
        """
        Optional: Clean shutdown of executor (can be tied to FastAPI shutdown event).
        """
        self._logger.info("Shutting down CMetaAsync executor...")
        self._executor.shutdown(wait=True)
