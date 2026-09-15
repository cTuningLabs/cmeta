"""
CMeta asynchronous wrapper for the core class

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import asyncio
import logging
import traceback
from functools import partial
from concurrent.futures import ProcessPoolExecutor

from .core import CMeta

# This logger is ONLY the module-level fallback.
module_logger = logging.getLogger(__name__)

# Per-process persistent CMeta instance
_cmeta_instance = None
_cmeta_index = 0


def _get_cmeta(
    **kwargs,  # Keyword arguments to pass to CMeta constructor.
):
    """
        Lazy initialization of CMeta per multiprocessing worker.

        Creates a single CMeta instance per process worker. This function is called
        by worker processes to initialize their own CMeta instance, mirroring the
        pattern used in FastAPI where instances are created once per process.

        Args:
            **kwargs: Keyword arguments to pass to CMeta constructor.
        Returns:
            CMeta: The initialized CMeta instance for this worker process.

        Raises:
            Exception: Propagated runtime errors, if any.
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


def _access_worker(
    params,  # Dictionary of parameters to pass to cmeta.access().
    kwargs,  # Keyword arguments for CMeta initialization.
):
    """
        Standalone function executed inside the ProcessPool worker.

        This function must be a standalone function (not a bound method) to avoid
        pickling errors when being passed to worker processes. It initializes or
        retrieves the worker's CMeta instance and executes the access request.

        Args:
            params: Dictionary of parameters to pass to cmeta.access().
            kwargs: Keyword arguments for CMeta initialization.
        Returns:
            dict: Result dictionary from cmeta.access().

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    cmeta = _get_cmeta(**kwargs)
    return cmeta.access(params)


class CMetaAsync(CMeta):
    """Async wrapper around CMeta using multiprocessing for non-blocking operations.
    
    This class extends CMeta to provide asynchronous wrappers around blocking
    operations using a ProcessPoolExecutor. It prevents blocking the event loop
    in FastAPI or other asyncio-based services by executing CMeta operations in
    separate worker processes.
    
    Inherits all CMeta methods while providing async wrappers for blocking operations.
    """

    def __init__(
        self,
        max_workers = None,  # Maximum number of worker processes in the pool.
        logger = None,  # Custom logger instance. If None, uses parent CMeta's logger.
        loop = None,  # Event loop to use. If None, gets the current event loop.
        **kwargs,  # Additional keyword arguments passed to CMeta constructor.
    ):
        """
            Initialize CMetaAsync with process pool executor.

            Args:
                max_workers: Maximum number of worker processes in the pool.
                logger: Custom logger instance. If None, uses parent CMeta's logger.
                loop: Event loop to use. If None, gets the current event loop.
                **kwargs: Additional keyword arguments passed to CMeta constructor.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """
        # Initialize parent CMeta
        super().__init__(**kwargs)

        # Store external logger (use parent's logger if not provided)
        self._logger = logger or self.logger

        # Event loop + executor.
        #
        # The loop is NOT resolved here. It used to be
        # `loop or asyncio.get_event_loop()`, which is wrong in two ways when
        # CMetaAsync is constructed at import time - as the cserver app and the
        # cTuning platform both do, at module level, before any loop runs:
        #
        #   * On Python 3.14.3 `get_event_loop()` raises
        #     "RuntimeError: There is no current event loop in thread
        #     'MainThread'" when none is current, so the import fails outright.
        #     (3.14.0 still auto-created one, which is why the same code can
        #     work on one patch release and not the next.)
        #   * Where it did auto-create one, that loop was NOT the loop the
        #     server later runs on, so the first await failed with
        #     "Future attached to a different loop".
        #
        # `self._loop` is only ever needed inside a coroutine (see
        # `access()`), and inside a coroutine the running loop is always
        # available - so it is looked up there instead. An explicitly passed
        # `loop` is still honoured.
        self._loop = loop
        self._executor = ProcessPoolExecutor(max_workers=max_workers)

        # Store constructor args for CMeta workers
        self._cmeta_kwargs = kwargs

        self._logger.info(
            f"[PID {os.getpid()}] CMetaAsync initialized | max_workers={max_workers}"
        )

    async def access(
        self,
        params,  # Dictionary of parameters to pass to CMeta.access().
    ):
        """
            Asynchronous non-blocking wrapper for CMeta.access().

            Runs CMeta.access() in a worker process to avoid blocking the event loop.

            Args:
                params: Dictionary of parameters to pass to CMeta.access().
            Returns:
                dict: Result dictionary from CMeta.access() with 'return' and other keys.

            Raises:
                Exception: Propagated runtime errors, if any.
        """
        func = partial(_access_worker, params, self._cmeta_kwargs)

        try:
            # Resolved here rather than in __init__: this is a coroutine, so
            # the loop actually running it is knowable and correct. See the
            # note in __init__ for why capturing one there was a bug.
            loop = self._loop or asyncio.get_running_loop()

            return await loop.run_in_executor(self._executor, func)

        except Exception as e:
            tb = traceback.format_exc()
            self._logger.exception("Error executing CMetaAsync access")
            return {"return": 99, "error": f"CMetaAsync internal error: {e}\n{tb}"}

    def access_sync(
        self,
        params,  # Dictionary of parameters to pass to CMeta.access().
    ):
        """
            Synchronous access using the inherited CMeta.access() method.

            Use this method when already executing in a worker thread or process
            where blocking is acceptable.

            Args:
                params: Dictionary of parameters to pass to CMeta.access().
            Returns:
                dict: Result dictionary from CMeta.access().

            Raises:
                Exception: Propagated runtime errors, if any.
        """
        return super().access(params)

    def shutdown(self):
        """
            Gracefully shutdown the process pool executor.

            Waits for all pending tasks to complete before shutting down the executor.
            This method can be tied to FastAPI or other framework shutdown events.

            Args:
                None.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """
        self._logger.info("Shutting down CMetaAsync executor...")
        self._executor.shutdown(wait=True)
