"""
CMeta asynchronous wrapper for the core class

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import sys
import time
import asyncio
import logging
import threading
import traceback
import multiprocessing
from functools import partial
from concurrent.futures import ProcessPoolExecutor

from .core import CMeta
from .utils import sys as sys_utils

# This logger is ONLY the module-level fallback.
module_logger = logging.getLogger(__name__)

# How the worker processes are started (2026-11-05). Python's default on Linux up to 3.13 is "fork": every worker is
# then a copy of the server process at the instant of the first call - its memory, every open descriptor (the
# listening socket, the client connections open right then) and the state of every lock its threads held. The copies
# of a client connection keep it open after the server closes its end (no FIN reaches the client, so a proxy reuses
# the dead connection and its next request hangs), the copy of the listening socket keeps the port taken after the
# server dies, and a lock copied while held can stop the worker for good. So the pool never forks a server: the
# platform's own method where that is not fork (spawn on Windows and macOS), forkserver elsewhere (the workers are
# forked from a small clean process that holds nothing of the server), spawn where forkserver does not exist. The
# environment variable, or the constructor, may name another method - "fork" included, with a warning.
START_METHOD_ENV = 'CMETA_ASYNC_START_METHOD'

# Every worker watches its parent and exits when the parent is gone (the server stopped, crashed or was killed):
# without it the workers of a dead server stayed for days, holding memory - and the port, when forked. "0", "no",
# "false" or "off" in this variable keeps the old behaviour (diagnostics, tests).
PARENT_WATCH_ENV = 'CMETA_ASYNC_PARENT_WATCH'

# Per-process persistent CMeta instance
_cmeta_instance = None
_cmeta_index = 0


def default_start_method():
    """
        The start method of the worker processes when nothing asks for another one: never "fork".

        Args:
            None.
        Returns:
            str: "spawn" on Windows (the only method there) and on macOS (the platform's own choice since Python
                 3.8); "forkserver" on the other POSIX platforms, "spawn" where it is not available.
    """
    if sys.platform in ('win32', 'darwin'):
        return 'spawn'
    return 'forkserver' if 'forkserver' in multiprocessing.get_all_start_methods() else 'spawn'


def start_method_context(
    start_method = None,  # The method asked for, or None: the environment variable CMETA_ASYNC_START_METHOD, else the default.
    logger = None,  # Where a warning goes (the module logger when None).
):
    """
        The multiprocessing context the pool starts its workers with.

        Args:
            start_method: "spawn", "forkserver" or "fork" (the last one with a warning: see the note at the top of
                          this module), or None for the environment variable, else `default_start_method()`.
            logger: The logger of the warning.
        Returns:
            multiprocessing.context.BaseContext: The context of that method.

        Raises:
            ValueError: The method is not one this platform has.
    """
    method = (start_method or os.environ.get(START_METHOD_ENV, '') or '').strip().lower() or default_start_method()
    methods = multiprocessing.get_all_start_methods()
    if method not in methods:
        raise ValueError(f'start method "{method}" is not one of this platform: {", ".join(methods)} '
                         f'(CMetaAsync(start_method=...) or {START_METHOD_ENV})')
    if method == 'fork':
        (logger or module_logger).warning(
            'CMetaAsync starts its workers with "fork": copies of this process, with its open connections and '
            'locks - a server should use forkserver or spawn (see cmeta.core_async)')
    return multiprocessing.get_context(method)


def _watch_parent():
    """
        A daemon thread of a worker process that ends the process when its parent is gone.

        Args:
            None.
        Returns:
            None.
    """
    parent = multiprocessing.parent_process()
    if parent is None:
        return

    def wait_for_the_parent():
        try:
            parent.join()
        except Exception:
            return
        os._exit(0)

    threading.Thread(target=wait_for_the_parent, name='cmeta-parent-watch', daemon=True).start()


def _worker_init(
    watch_parent,  # True: the worker ends itself when its parent is gone.
):
    """
        Runs once in every worker process, before its first call.

        Args:
            watch_parent: True to start the watch of the parent process (see `_watch_parent`).
        Returns:
            None.
    """
    if watch_parent:
        _watch_parent()


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
        # A worker answers requests: at full speed when it has one, whatever Windows takes a process that waits
        # between them for (utils.sys.prefer_speed, 2026-11-04)
        sys_utils.prefer_speed()

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


def _warm_worker(
    kwargs,  # Keyword arguments for CMeta initialization.
    hold,  # Seconds the worker keeps this call, so that the others of a warm() each reach a worker of their own.
):
    """
        A call of `warm()`, in a worker: its CMeta is made, the call is held, the pid comes back.

        Args:
            kwargs: Keyword arguments for CMeta initialization.
            hold: Seconds to hold the call.
        Returns:
            int: The pid of this worker.
    """
    _get_cmeta(**kwargs)
    if hold > 0:
        time.sleep(hold)
    return os.getpid()


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
        start_method = None,  # How the workers are started: "spawn", "forkserver" or "fork"; None: CMETA_ASYNC_START_METHOD, else never fork (see the note at the top of this module).
        **kwargs,  # Additional keyword arguments passed to CMeta constructor.
    ):
        """
            Initialize CMetaAsync with process pool executor.

            Args:
                max_workers: Maximum number of worker processes in the pool.
                logger: Custom logger instance. If None, uses parent CMeta's logger.
                loop: Event loop to use. If None, gets the current event loop.
                start_method: How the workers are started (see `start_method_context`).
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

        # The workers: started by the context of `start_method_context` (never a fork of this process unless asked
        # for), each watching this process so that none outlives it
        context = start_method_context(start_method, logger=self._logger)
        self.start_method = context.get_start_method()
        self.watch_parent = os.environ.get(PARENT_WATCH_ENV, '').strip().lower() not in ('0', 'no', 'false', 'off')
        self._executor = ProcessPoolExecutor(max_workers=max_workers, mp_context=context,
                                             initializer=_worker_init, initargs=(self.watch_parent,))
        self.max_workers = max_workers or getattr(self._executor, '_max_workers', None) or os.cpu_count() or 1

        # The process that runs the event loop too: it reads every request and writes every answer
        sys_utils.prefer_speed()

        # Store constructor args for CMeta workers
        self._cmeta_kwargs = kwargs

        # The plain CMeta of this process for access_sync(), made at its first call (KI-001)
        self._sync_cmeta = None

        self._logger.info(
            f"[PID {os.getpid()}] CMetaAsync initialized | max_workers={self.max_workers} start_method={self.start_method}"
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
            Synchronous access: the command runs in this process, blocking, on a plain
            CMeta of this process - made at the first call with the constructor arguments
            of this object, as a worker process makes its own - so a command that calls
            cm.access() itself (most of them) gets a result dict, as it does in a worker.

            Use this method when already executing in a worker thread or process
            where blocking is acceptable, or before an event loop runs (at import).
            It never runs the command on this async object: until KI-001 was fixed it
            did, and a nested cm.access() landed on the async access() and handed back
            an un-awaited coroutine in place of the result.

            Args:
                params: Dictionary of parameters to pass to CMeta.access().
            Returns:
                dict: Result dictionary from CMeta.access().

            Raises:
                Exception: Propagated runtime errors, if any.
        """
        if self._sync_cmeta is None:
            self._sync_cmeta = CMeta(**self._cmeta_kwargs)

        return self._sync_cmeta.access(params)

    def _warm_futures(
        self,
        count,  # How many workers to start: None = all of them (max_workers).
        hold,  # Seconds each call is held, so that the calls reach distinct workers.
    ):
        """
            The calls of a warm-up, submitted: one per worker to start.

            Args:
                count: The number of calls (workers), None for max_workers.
                hold: Seconds each call is held.
            Returns:
                list: The concurrent.futures.Future of each call (its result is the worker's pid).
        """
        n = int(count or self.max_workers or 1)
        return [self._executor.submit(_warm_worker, self._cmeta_kwargs, hold) for _ in range(n)]

    def warm(
        self,
        count = None,  # How many workers to start: None = all of them (max_workers).
        hold = 0.5,  # Seconds each call is held, so that the calls reach distinct workers (0: the processes start, their CMeta is made on the first real call of some of them).
    ):
        """
            Start the worker processes now, each with its CMeta made - before the first request, so that no visitor
            meets a cold worker and no client connection is open when the processes start (a server calls it in its
            startup, before it accepts anyone). Blocking; `warm_async` is the same for a coroutine.

            Args:
                count: The number of workers to start (None: every one of the pool).
                hold: Seconds each warm-up call is held in its worker - long enough for the other workers to start
                      and take theirs; with 0 a fast worker may take several calls, and only the processes are
                      guaranteed to exist.
            Returns:
                list: The pids of the workers that answered, sorted (distinct).

            Raises:
                Exception: Propagated runtime errors, if any.
        """
        return sorted({f.result() for f in self._warm_futures(count, hold)})

    async def warm_async(
        self,
        count = None,  # How many workers to start: None = all of them (max_workers).
        hold = 0.5,  # Seconds each call is held, so that the calls reach distinct workers.
    ):
        """
            `warm()` for a coroutine: the event loop stays free while the workers start.

            Args:
                count: The number of workers to start (None: every one of the pool).
                hold: Seconds each warm-up call is held in its worker.
            Returns:
                list: The pids of the workers that answered, sorted (distinct).

            Raises:
                Exception: Propagated runtime errors, if any.
        """
        futures = [asyncio.wrap_future(f, loop=self._loop or asyncio.get_running_loop())
                   for f in self._warm_futures(count, hold)]
        return sorted(set(await asyncio.gather(*futures)))

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
