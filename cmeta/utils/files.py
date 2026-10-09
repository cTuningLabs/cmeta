"""
Reusable functions for safe loading, storing and caching of files 

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import time
import json
import pickle
import shutil
import stat
import zipfile
from pathlib import Path
import uuid
import hashlib
import fnmatch
import re
import errno
import logging
import random
import threading

from .common import _error

try:
    import yaml
except ImportError:
    yaml = None  # YAML is optional

try:
    import fcntl  # POSIX: flock and POSIX record locks
except ImportError:
    fcntl = None

try:
    import msvcrt  # Windows: byte-range locks
except ImportError:
    msvcrt = None

LOCK_SUFFIX = ".lock"
LOCK_POLL_START = 0.001          # the first wait when a lock is busy; it doubles up to LOCK_POLL_MAX
LOCK_POLL_MAX = 0.025
LOCK_SOFT_STALE_SECONDS = 600    # a soft lock file older than this, whose holder is on another host, is stale
LOCK_SOFT_EMPTY_STALE_SECONDS = 2.0  # an EMPTY soft lock file older than this is a leftover (a holder writes its content at once)
LOCK_SOFT_DEAD_MIN_AGE_SECONDS = 1.0  # a soft lock file of a dead pid younger than this is a release in flight, not a crash
LOCK_SOFT_CHECK_SECONDS = 0.25   # how often a waiter on a soft lock reads the file to check for a stale holder
LOCK_SOFT_REMOVE_SECONDS = 2.0   # how long a releasing soft lock retries the removal of its file (Windows: a reader may hold it)
LOCK_IDENTITY_RETRIES = 50       # consecutive identity mismatches after which a path is locked with the soft lock
LOCK_NOTE_MAX = 512              # bytes of the note a holder may leave in its lock file for the message of a waiter
ERROR_CODE_FILE_NOT_FOUND = 16
RETRY_DELAY = 0.1
RETRY_NOT_FOUND_FILE = 10
RETRY_NOT_FOUND_INDEX_FILE = 2
RETRY_REPLACE_FILE = 10
RETRY_TIMESTAMP_FILE = 10
RETRY_DELETE_ATTEMPTS = 5

##########################################################################################
def _get_lockfile_path(
    filepath: str,  # Path to the file that needs locking.
):
    """
        Get the lock file path for a given file path.

        Args:
            filepath (str): Path to the file that needs locking.

        Returns:
            str: Path to the corresponding lock file (filepath + .lock suffix).

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    return f"{filepath}{LOCK_SUFFIX}"

##########################################################################################
def is_dir_within_path(
    base: str,  # Value for base.
    directory: str,  # Directory path.
):
    """
        Check whether a child directory name resolves under a base path.

        Args:
            base: Value for base.
            directory: Directory path.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """
    target = os.path.join(base, directory)
    return is_path_within(base, target)

def is_path_within(
    base: str,  # Base path to check.
    target: str,  # Target path to check against.
):
    """
        Check if base path is within target path.

        Determines if the base path is a subdirectory or file within the target path.

        Args:
            base (str): Base path to check.
            target (str): Target path to check against.

        Returns:
            bool: True if base is within target, False otherwise.

        Raises:
            Exception: Propagated runtime errors, if any.
    """

    base = os.path.abspath(base)
    target = os.path.abspath(target)

    try:
        common = os.path.commonpath([base, target])
    except ValueError:
        # Different drives or mixed absolute/relative paths
        return False

    return common == base

##########################################################################################
# The path lock
#
# One exclusive lock per path for processes and threads alike, through the sidecar file `<path>.lock`:
# the lock file is created for the operation and removed by the process that releases it, so a repository
# never keeps lock files (a crash leaves at most the one of the operation in flight, which the next holder
# reuses and removes - every lock dies with its process).
#
# Why not a library: a lock file that is removed after release is only correct when the holder removes
# it BEFORE releasing and every newcomer checks, after acquiring, that the file it holds is still the
# file at the path (otherwise a waiter blocked on the removed file and a newcomer that created a new
# one both hold "the lock" - the lost updates seen on Linux with the previous library + removal). That
# needs the lock's own descriptor, which libraries do not expose.
#
# The ladder, per platform:
#   Windows:  msvcrt.locking (a byte-range lock, per handle, mandatory) on the lock file; an open file
#             cannot be removed there, so the identity check is not needed - a newcomer that finds the
#             file "being deleted" (PermissionError) simply tries again.
#   POSIX:    fcntl.flock (per open file description, so threads of one process exclude each other too),
#             then fcntl.lockf (POSIX record locks: NFS and some network mounts refuse flock), each with
#             the identity check (fstat of the descriptor vs stat of the path, inode and device);
#   anywhere: the soft lock (the file created with O_EXCL, holding "pid host time") where the file
#             system refuses both OS locks (some FUSE, 9p and SMB mounts) or the identity check keeps
#             failing - a stale soft lock (its pid dead on this host, or older than LOCK_SOFT_STALE_SECONDS
#             when left by another host) is renamed away and removed by the waiter that finds it.
# In every mode the threads of one process are serialized on the path first (a threading.Lock per path),
# which POSIX record locks and soft locks need (they are per process), and the busy wait polls with a
# delay that doubles from LOCK_POLL_START to LOCK_POLL_MAX until the timeout.

_LOCK_BUSY_ERRNOS = tuple(e for e in (getattr(errno, name, None) for name in ('EWOULDBLOCK', 'EAGAIN', 'EACCES', 'EDEADLK', 'EDEADLOCK')) if e is not None)
_LOCK_UNSUPPORTED_ERRNOS = tuple(e for e in (getattr(errno, name, None) for name in ('ENOLCK', 'ENOSYS', 'EOPNOTSUPP', 'ENOTSUP', 'EINVAL', 'ENOTTY', 'EPERM', 'EBADF')) if e is not None)

_lock_registry = {}               # normalized lock file path -> threading.Lock (the threads of this process)
_lock_registry_guard = threading.Lock()
_lock_soft_paths = set()          # lock files locked with the soft lock from now on (the OS lock was refused)
_lock_no_flock_dirs = set()       # folders where flock was refused (POSIX record locks are tried first there)
_lock_host = None


def _lock_thread_lock(lock_file):
    key = os.path.normcase(os.path.abspath(lock_file))
    with _lock_registry_guard:
        lock = _lock_registry.get(key)
        if lock is None:
            lock = threading.Lock()
            _lock_registry[key] = lock
        return lock


def _lock_host_name():
    global _lock_host
    if _lock_host is None:
        try:
            import platform
            _lock_host = platform.node() or 'unknown-host'
        except Exception:
            _lock_host = 'unknown-host'
    return _lock_host


def _lock_pid_alive(pid):
    try:
        import psutil
        return psutil.pid_exists(pid)
    except Exception:
        return True   # unknown: never treat it as dead


class _LockUnsupported(Exception):
    pass


class PathLock:
    """
        An exclusive lock on a path for processes and threads, through the sidecar file `<path>.lock`
        (see the notes above). Use `acquire(timeout)` / `release()` or the context manager; `is_locked`
        says whether this object holds the lock; `mode` is how it was taken ('windows', 'flock', 'lockf'
        or 'soft'); `identity_retries` counts the times a replaced lock file was detected and retried.
    """

    def __init__(
        self,
        lock_file: str,  # The lock file (normally `<path>.lock`, see _get_lockfile_path).
        logger = None,  # Optional logger for debug and warning messages.
    ):
        self.lock_file = lock_file
        self.logger = logger if logger is not None else logging.getLogger('cmeta.utils.files')
        self.is_locked = False
        self.mode = None
        self.identity_retries = 0
        self._fd = None
        self._ident = None
        self._thread_lock = None
        self._mismatches = 0
        self._last_error = None
        self._next_stale_check = 0.0

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()

    def __del__(self):
        try:
            if self.is_locked:
                self.release()
        except Exception:
            pass

    def acquire(
        self,
        timeout: float = 3,  # Seconds to wait for the lock (0: one try).
        note: str = None,  # A short note left in the lock file for the message of a waiter (see read_note).
    ):
        """Take the lock or raise TimeoutError; returns self."""
        timeout = max(float(timeout), 0.0)
        thread_lock = _lock_thread_lock(self.lock_file)
        if not thread_lock.acquire(timeout=timeout):
            raise TimeoutError(f"the lock {self.lock_file} is held by another thread of this process (waited {timeout} s)")

        try:
            deadline = time.monotonic() + timeout
            delay = LOCK_POLL_START
            while True:
                if self._try():
                    self._thread_lock = thread_lock
                    self.is_locked = True
                    self.logger.debug(f"utils.files.PathLock - acquired {self.lock_file} ({self.mode})")
                    if note is not None:
                        self.write_note(note)
                    return self

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    why = f" ({self._last_error})" if self._last_error is not None else ""
                    raise TimeoutError(f"the lock {self.lock_file} is held by another process (waited {timeout} s){why}")

                time.sleep(min(delay, remaining))
                delay = min(delay * 2, LOCK_POLL_MAX)

        except BaseException:
            thread_lock.release()
            raise

    def release(self):
        """Release the lock and remove its file (when the file at the path is still the one this lock holds)."""
        if not self.is_locked:
            return

        try:
            if self.mode == 'windows':
                try:
                    msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
                os.close(self._fd)
                self._unlink_own_file()

            elif self.mode in ('flock', 'lockf'):
                self._unlink_own_file()
                try:
                    self._posix_unlock(self._fd, self.mode)
                except OSError:
                    pass
                os.close(self._fd)

            elif self.mode == 'soft':
                self._remove_soft_file()

        finally:
            self._fd = None
            self._ident = None
            self.is_locked = False
            self.mode = None
            thread_lock = self._thread_lock
            self._thread_lock = None
            if thread_lock is not None:
                thread_lock.release()

    def write_note(self, note):
        """Leave a short note in the held lock file - who holds it and why - for the message of a waiter
        (`read_note`). Best effort: nothing happens when it cannot be written. The note starts after a first
        byte that stays free: on Windows that byte is the locked one, which another process cannot read. Not
        in soft mode, where the file already holds `pid host time`."""
        if not self.is_locked or self._fd is None or self.mode == 'soft':
            return
        data = b'\n' + str(note).encode('utf-8', 'replace')[:LOCK_NOTE_MAX] + b'\n'
        try:
            os.ftruncate(self._fd, 0)
            os.lseek(self._fd, 0, os.SEEK_SET)
            os.write(self._fd, data)
        except OSError:
            pass
        finally:
            try:
                os.lseek(self._fd, 0, os.SEEK_SET)   # the Windows byte lock is addressed by the file position
            except OSError:
                pass

    @staticmethod
    def read_note(lock_file):
        """The note the holder of `lock_file` left (`write_note`), or the `pid host time` of a soft lock,
        or '' when there is none or the file cannot be read."""
        try:
            fd = os.open(lock_file, os.O_RDONLY | getattr(os, 'O_BINARY', 0))
        except OSError:
            return ''
        try:
            try:
                data = os.read(fd, LOCK_NOTE_MAX + 8)
            except OSError:
                # Windows: the first byte is locked by the holder - read from the second one
                os.lseek(fd, 1, os.SEEK_SET)
                data = os.read(fd, LOCK_NOTE_MAX + 8)
        except OSError:
            return ''
        finally:
            os.close(fd)
        text = data.decode('utf-8', 'replace').strip()
        return text.splitlines()[0].strip() if text else ''

    # ---- one attempt ----------------------------------------------------------------------

    def _try(self):
        if self.lock_file in _lock_soft_paths:
            return self._try_soft()
        if msvcrt is not None:
            return self._try_windows()
        if fcntl is not None:
            return self._try_posix()
        return self._try_soft()

    def _folder_is_there(self):
        return os.path.isdir(os.path.dirname(self.lock_file) or '.')

    def _open_failed_for_the_moment(self, e):
        """An open of the lock file that failed for a moment: the file being removed by the process that
        just released it (Windows: PermissionError; 9p and other network mounts: ENOENT with the folder
        there) or held by a scanner. A missing folder is a real error."""
        if isinstance(e, PermissionError):
            self._last_error = e
            return True
        if isinstance(e, FileNotFoundError) and self._folder_is_there():
            self._last_error = e
            return True
        return False

    def _try_windows(self):
        try:
            fd = os.open(self.lock_file, os.O_RDWR | os.O_CREAT, 0o644)
        except OSError as e:
            if self._open_failed_for_the_moment(e):
                return False
            raise

        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as e:
            os.close(fd)
            if e.errno in _LOCK_BUSY_ERRNOS:
                self._last_error = e
                return False
            self._fall_back_to_soft(e)
            return self._try_soft()

        try:
            self._ident = self._identity(os.fstat(fd))
        except OSError:
            self._ident = None
        self._fd = fd
        self.mode = 'windows'
        return True

    def _try_posix(self):
        try:
            fd = os.open(self.lock_file, os.O_RDWR | os.O_CREAT | getattr(os, 'O_CLOEXEC', 0), 0o644)
        except OSError as e:
            if self._open_failed_for_the_moment(e):
                return False
            raise

        try:
            kind = self._posix_lock(fd)
        except _LockUnsupported as e:
            os.close(fd)
            self._fall_back_to_soft(e)
            return self._try_soft()
        except BaseException:
            os.close(fd)
            raise

        if kind is None:
            os.close(fd)
            return False

        # The file this descriptor holds must still be the file at the path: a holder that removed
        # the file and released it leaves a waiter with a lock on a file that is not there any more
        try:
            path_ident = self._identity(os.stat(self.lock_file))
        except OSError:
            path_ident = None
        fd_ident = self._identity(os.fstat(fd))

        if fd_ident is not None and (path_ident is None or path_ident != fd_ident):
            try:
                self._posix_unlock(fd, kind)
            except OSError:
                pass
            os.close(fd)
            self.identity_retries += 1
            self._mismatches += 1
            if self._mismatches >= LOCK_IDENTITY_RETRIES:
                self._fall_back_to_soft(f"the identity of the lock file could not be confirmed {self._mismatches} times")
                return self._try_soft()
            return False

        self._mismatches = 0
        self._fd = fd
        self._ident = fd_ident
        self.mode = kind
        return True

    def _posix_lock(self, fd):
        """flock, else POSIX record lock; 'flock' | 'lockf' when taken, None when busy, _LockUnsupported when refused."""
        folder = os.path.dirname(self.lock_file)

        if folder not in _lock_no_flock_dirs:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return 'flock'
            except OSError as e:
                if e.errno in _LOCK_BUSY_ERRNOS or e.errno == errno.EINTR:
                    self._last_error = e
                    return None
                if e.errno not in _LOCK_UNSUPPORTED_ERRNOS:
                    raise
                _lock_no_flock_dirs.add(folder)
                self.logger.info(f"utils.files.PathLock - flock is not supported for {self.lock_file} ({e}): POSIX record locks are used in that folder")

        try:
            fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return 'lockf'
        except OSError as e:
            if e.errno in _LOCK_BUSY_ERRNOS or e.errno == errno.EINTR:
                self._last_error = e
                return None
            if e.errno in _LOCK_UNSUPPORTED_ERRNOS:
                raise _LockUnsupported(str(e))
            raise

    @staticmethod
    def _posix_unlock(fd, kind):
        if kind == 'flock':
            fcntl.flock(fd, fcntl.LOCK_UN)
        else:
            fcntl.lockf(fd, fcntl.LOCK_UN)

    def _try_soft(self):
        try:
            fd = os.open(self.lock_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0), 0o644)
        except FileExistsError as e:
            self._last_error = e
            now = time.monotonic()
            if now >= self._next_stale_check:
                self._next_stale_check = now + LOCK_SOFT_CHECK_SECONDS
                self._clear_stale_soft_lock()
            return False
        except OSError as e:
            if self._open_failed_for_the_moment(e):
                return False
            raise

        try:
            os.write(fd, (f"{os.getpid()} {_lock_host_name()} {time.time():.3f}\n").encode('utf-8', 'replace'))
        finally:
            os.close(fd)

        try:
            self._ident = self._identity(os.stat(self.lock_file))
        except OSError:
            self._ident = None
        self.mode = 'soft'
        return True

    def _clear_stale_soft_lock(self):
        """A soft lock file whose holder is dead (this host; the file at least LOCK_SOFT_DEAD_MIN_AGE_SECONDS
        old, so that a holder that just released and exited is not mistaken for a crash), that was marked
        released by a holder that could not remove it, that is empty and old (a leftover) or too old (another
        host) is renamed away and removed - by one waiter only (the rename is atomic), and only when the file
        at the path is still the file that was judged (a fresh lock file of a live holder moved by mistake in
        the instant between the check and the rename is put back)."""
        try:
            fd = os.open(self.lock_file, os.O_RDONLY | getattr(os, 'O_BINARY', 0))
        except OSError:
            return
        try:
            st = os.fstat(fd)
            words = os.read(fd, 256).decode('utf-8', 'replace').split() if st.st_size > 0 else []
        except OSError:
            return
        finally:
            os.close(fd)

        ident = self._identity(st)
        age = time.time() - st.st_mtime
        pid = int(words[0]) if len(words) > 0 and words[0].isdigit() else None
        host = words[1] if len(words) > 1 else None

        if not words:
            stale = age > LOCK_SOFT_EMPTY_STALE_SECONDS
        elif words[0] == 'released':
            stale = True
        elif pid is not None and host == _lock_host_name():
            stale = age > LOCK_SOFT_DEAD_MIN_AGE_SECONDS and not _lock_pid_alive(pid)
        else:
            stale = age > LOCK_SOFT_STALE_SECONDS

        if not stale:
            return

        try:
            if ident is not None and self._identity(os.stat(self.lock_file)) != ident:
                return                      # the file changed under us: judge it again next time
        except OSError:
            return

        moved = f"{self.lock_file}.stale-{os.getpid()}-{random.getrandbits(32):08x}"
        try:
            os.rename(self.lock_file, moved)   # atomic: only one waiter gets to remove it
        except OSError:
            return

        if ident is not None:
            try:
                moved_ident = self._identity(os.stat(moved))
            except OSError:
                return
            if moved_ident != ident:
                # Not the file judged stale but a fresh one made in between: back where it was, without
                # clobbering (a hard link fails where a file exists already), then the extra name goes
                try:
                    os.link(moved, self.lock_file)
                except OSError:
                    try:
                        if not os.path.exists(self.lock_file):
                            os.rename(moved, self.lock_file)
                    except OSError:
                        pass
                    return
                try:
                    os.unlink(moved)
                except OSError:
                    pass
                return

        try:
            os.unlink(moved)
        except OSError:
            pass
        self.logger.warning(f"utils.files.PathLock - removed the stale lock file {self.lock_file} (left by pid {pid} on {host})")

    def _fall_back_to_soft(self, why):
        if self.lock_file not in _lock_soft_paths:
            _lock_soft_paths.add(self.lock_file)
            self.logger.warning(f"utils.files.PathLock - the file system refuses OS locks for {self.lock_file} ({why}): a soft lock file is used instead (best effort between hosts)")
        # The empty file the OS-lock attempt created or found is not a soft lock (a soft holder writes its
        # content at once): out of the way, or the soft lock could never be taken
        try:
            if os.path.getsize(self.lock_file) == 0:
                os.unlink(self.lock_file)
        except OSError:
            pass

    def _remove_soft_file(self):
        """Remove the soft lock file; on Windows a waiter reading it holds it open for a moment, so the removal
        is retried, and a file that cannot be removed in time is marked released for the waiters to clear."""
        deadline = time.monotonic() + LOCK_SOFT_REMOVE_SECONDS
        while True:
            if self._ident is not None:
                try:
                    if self._identity(os.stat(self.lock_file)) != self._ident:
                        return     # not ours any more
                except OSError:
                    return
            try:
                os.unlink(self.lock_file)
                return
            except FileNotFoundError:
                return
            except PermissionError:
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.002)
            except OSError:
                break

        try:
            with open(self.lock_file, 'w') as f:
                f.write(f"released {os.getpid()}\n")
        except OSError:
            pass
        self.logger.warning(f"utils.files.PathLock - the soft lock file {self.lock_file} could not be removed and was marked released")

    @staticmethod
    def _identity(st):
        """The (inode, device) of a stat result; None where the file system reports no inode (some FAT drivers)."""
        if not st.st_ino:
            return None
        return (st.st_ino, st.st_dev)

    def _unlink_own_file(self):
        """Remove the lock file, unless the file at the path is no longer the one this lock took (someone
        removed it under us and another process created a new one: that one is theirs)."""
        if self._ident is not None:
            try:
                if self._identity(os.stat(self.lock_file)) != self._ident:
                    return
            except OSError:
                return
        try:
            os.unlink(self.lock_file)
        except OSError:
            pass


##########################################################################################
def _acquire_lock(
    filepath: str,  # Path to the file to lock.
    timeout: int = 3,  # Maximum seconds to wait for lock acquisition. Default is 3.
    logger = None,  # Optional logger for debug messages.
):
    """
        Acquire the lock of a path (`<filepath>.lock`, see PathLock) for process- and thread-safe
        file operations. Blocks until the lock is acquired or the timeout expires.

        Args:
            filepath (str): Path to the file to lock.
            timeout (int): Maximum seconds to wait for lock acquisition. Default is 3.
            logger: Optional logger for debug messages.

        Returns:
            PathLock: Acquired lock object that must be released later (`_release_lock`).

        Raises:
            TimeoutError: If lock cannot be acquired within timeout period.
    """
    lockfile = _get_lockfile_path(filepath)
    if logger is not None:
        logger.debug(f"utils.files._acquire_lock - attempting to create {lockfile} ...")

    file_lock = PathLock(lockfile, logger=logger)
    try:
        file_lock.acquire(timeout=timeout)
        if logger is not None:
            logger.debug(f"utils.files._acquire_lock - lock {lockfile} acquired!")
        return file_lock
    except Exception as e:
        if logger is not None:
            logger.debug(f"utils.files._acquire_lock - failed to create {lockfile} ...")
        raise TimeoutError(f"Could not acquire lock on '{filepath}' within {timeout} seconds: {str(e)}")

##########################################################################################
def _check_lock(
    filepath: str,  # Path to the locked file.
    file_lock,  # PathLock object to check.
    logger = None,  # Optional logger for debug messages.
):
    """
        Verify that a file lock is still valid.

        Args:
            filepath (str): Path to the locked file.
            file_lock: PathLock object to check.
            logger: Optional logger for debug messages.

        Raises:
            TimeoutError: If lock has expired or is no longer valid.

        Returns:
            dict: Operation result.
    """
    if not file_lock.is_locked:
        if logger is not None:
            logger.debug(f"utils.files._check_lock - detected expired lock for {filepath} ...")
        raise TimeoutError(f"Detected expired lock for '{filepath}'")
    if logger is not None:
        logger.debug(f"utils.files._check_lock - lock file checked for {filepath} ...")

##########################################################################################
def _release_lock(
    filepath: str,  # Path to the locked file.
    file_lock,  # PathLock object to release.
    logger = None,  # Optional logger for debug messages.
):
    """
        Release a previously acquired file lock; the lock file is removed by the lock itself.

        Args:
            filepath (str): Path to the locked file.
            file_lock: PathLock object to release.
            logger: Optional logger for debug messages.

        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """
    lockfile = _get_lockfile_path(filepath)

    try:
        if file_lock.is_locked:
            file_lock.release()
            if logger is not None:
                logger.debug(f"utils.files._release_lock - lock released {lockfile} ...")
        else:
            if logger is not None:
                logger.debug(f"utils.files._release_lock - lock {lockfile} doesn't exist - weird but keep running ...")

    except Exception as e:
        if logger is not None:
            logger.debug(f"utils.files._release_lock - error releasing lock {lockfile} ({str(e)})")
        raise e

##########################################################################################
def _detect_file_format(
    filepath: str,  # Path to the file.
):
    """
        Detect file format based on file extension.

        Args:
            filepath (str): Path to the file.

        Returns:
            str: File format ('json', 'yaml', 'pickle', or 'text').

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    suffix = Path(filepath).suffix.lower()
    if suffix == ".json":
        return "json"
    elif suffix in [".yaml", ".yml"]:
        return "yaml"
    elif suffix in [".pkl", ".pickle"]:
        return "pickle"
    else:
        return "text"

##########################################################################################
def _read_file_data(
    filepath: str,  # Path to the file to read.
    encoding: str = None,  # Character encoding for text files. If None, uses binary mode for pickle.
):
    """
        Read file data with format-specific parsing.

        Automatically detects file format and uses appropriate parser
        (JSON, YAML, pickle, or plain text).

        Args:
            filepath (str): Path to the file to read.
            encoding (str | None): Character encoding for text files. If None, uses binary mode for pickle.

        Returns:
            Parsed file content (dict for JSON/YAML, bytes/str for text/pickle).

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    file_format = _detect_file_format(filepath)

    encoding = _get_encoding(encoding, file_format)

    mode = "rb" if encoding is None else "r"

    with open(filepath, mode, encoding=encoding) as f:
        if file_format == "json":
            return json.load(f)
        elif file_format == "yaml":
            return yaml.safe_load(f)
        elif file_format == "pickle":
            return pickle.load(f)
        else:
            return f.read()


##########################################################################################
def read_file(
    filepath: str,  # Path to the file to read.
    fail_on_error: bool = False,  # If True, raises exception on error instead of returning error dict.
    logger = None,  # Optional logger for debug messages.
    encoding: str = None,  # Character encoding for text files.
    remove_after_read: bool = False,
):
    """
        Read file without locking (convenience wrapper for safe_read_file).

        Args:
            filepath (str): Path to the file to read.
            fail_on_error (bool): If True, raises exception on error instead of returning error dict.
            logger: Optional logger for debug messages.
            encoding (str | None): Character encoding for text files.
            remove_after_read (bool): If True, attempt to remove the file after reading it.

        Returns:
            dict: Dictionary with 'return': 0 and 'data', or 'return' > 0 and 'error'.

        Raises:
            Exception: Propagated runtime errors, if any.
    """

    r = safe_read_file(filepath, encoding=encoding, timeout=0, retry_if_not_found=1, fail_on_error=fail_on_error, logger=logger)

    if remove_after_read and os.path.isfile(filepath):
        try:
            os.remove(filepath)
        except Exception as e:
            pass

    return r

##########################################################################################
def safe_read_file(
    filepath: str,  # Path to the file to read.
    encoding: str = None,  # Character encoding for text files. If None, auto-detected.
    lock: bool = False,  # If True, acquires file lock before reading.
    keep_locked: bool = False,  # If True with lock=True, keeps lock after read (returns in result).
    timeout: int = 3,  # Seconds to wait for lock acquisition. Default is 3.
    retry_if_not_found: int = 0,  # Number of retry attempts if file not found.
    fail_on_error: bool = False,  # If True, raises exception on error instead of returning error dict.
    logger = None,  # Optional logger for debug messages.
    get_last_modified: bool = False,  # If True, include file modification timestamp in the result.
):
    """
        Safely read file with optional locking and retry logic.

        Provides thread/process-safe file reading with file locking support.
        Cleans up lock on error. If keep_locked=True and lock=True, maintains
        the lock after successful read (caller must release).

        WARNING: This function uses blocking I/O operations. Not suitable for
        async contexts - use aiofiles and async locking instead.

        Args:
            filepath: Path to the file to read.
            encoding: Character encoding for text files. If None, auto-detected.
            lock: If True, acquires file lock before reading.
            keep_locked: If True with lock=True, keeps lock after read (returns in result).
            timeout: Seconds to wait for lock acquisition. Default is 3.
            retry_if_not_found: Number of retry attempts if file not found.
            fail_on_error: If True, raises exception on error instead of returning error dict.
            logger: Optional logger for debug messages.

            get_last_modified (bool): If True, include file modification timestamp in the result.
        Returns:
            dict: Dictionary with 'return': 0, 'data', 'filepath', and optionally 'last_modified'
                  and 'file_lock' (if keep_locked=True). Returns 'return' > 0 and 'error' on failure.

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    if logger is not None:
        logger.debug(f"utils.files.safe_read_file - preparing to read {filepath} ...")

    path = Path(filepath)

    if path.is_dir():
        return _error(f"'{filepath}' is a directory; safe_read only supports files.", 1, None, fail_on_error)

    # We need to acquire lock first and then check if file exists
    # to avoid cases, when file was deleted before writing
    if lock:
        try:
            file_lock = _acquire_lock(filepath, timeout, logger)
        except Exception as e:
            return _error(None, 1, e, fail_on_error)

    # Check if file exists with retry logic when no lock
    last_modified = None

    # Retry file existence check RETRY_NOT_FOUND_FILE+1 times with small delay
    retry_not_found_file = RETRY_NOT_FOUND_FILE + 1 if retry_if_not_found == 0 else retry_if_not_found
    for attempt in range(retry_not_found_file):
        if path.exists():
            if get_last_modified:
                try:
                    last_modified = path.stat().st_mtime
                except Exception:
                    last_modified = None
            break

        if attempt < retry_not_found_file:  # Don't delay after last attempt
            if logger is not None:
                logger.debug(f"utils.files.safe_read_file - retrying existence check for '{filepath}' (attempt {attempt + 1}) ...")
            time.sleep(RETRY_DELAY)

    if not path.exists():
        if lock:
            try:
                _release_lock(filepath, file_lock, logger)
            except Exception as e:
                return _error(None, 1, e, fail_on_error)

        return _error(f"'{filepath}' does not exist", ERROR_CODE_FILE_NOT_FOUND, None, fail_on_error)

    data = None

    if not lock:
        if timeout == 0:
            try:
                data = _read_file_data(filepath, encoding=encoding)
            except Exception as e:
                return _error(str(e), 1, None, fail_on_error)

        else:
            # Retry reading with timeout when no lock
            start_time = time.time()
            last_error = None
            
            while time.time() - start_time < timeout:
                try:
                    data = _read_file_data(filepath, encoding=encoding)
                    break  # Success, exit retry loop
                    
                except Exception as e:
                    last_error = e
                    if time.time() - start_time < timeout:
                        if logger is not None:
                            logger.debug(f"utils.files.safe_read_file - retrying read file '{filepath}' due to error: {str(e)} ...")
                        time.sleep(RETRY_DELAY)  # Small delay before retry
                        
            if data is None and last_error:
                return _error(str(last_error), 1, None, fail_on_error)
    else:
        try:
            data = _read_file_data(filepath)
            
        except Exception as e:
            try:
                _release_lock(filepath, file_lock)
            except Exception as e:
                return _error(None, 1, e, fail_on_error)
        
            return _error(None, 1, e, fail_on_error)

    r = {'return': 0, 'data': data, 'filepath': filepath}

    if last_modified is not None:
        r['last_modified'] = last_modified

    if lock:
        if keep_locked:
            r['file_lock'] = file_lock
        else:
            try:
                _release_lock(filepath, file_lock, logger)
            except Exception as e:
                return _error(None, 1, e, fail_on_error)

    return r

##########################################################################################
def write_file(
    filepath: str,  # Path where file should be written.
    data,  # Data to write (dict/list for JSON/YAML, any object for pickle/text).
    encoding: str = None,  # Character encoding for text files. If None, auto-detected.
    fail_on_error: bool = False,  # If True, raises exception on error instead of returning error dict.
    logger = None,  # Optional logger for debug messages.
    sort_keys: bool = True,  # If True, sorts dictionary keys in JSON/YAML output.
    file_format: str = None,  # Force specific format ('json', 'yaml', 'pickle', 'text'). If None, auto-detected.
    newline: str = '\n',  # Newline character for text files. Default is '
    safe_dump: bool = False, # If True, write non-serializable vars as "#NON-SERIALIZABLE#"
    keep: bool = False,  # If True, YAML is written in the keep style: the key order of YAML_META_KEY_ORDER, nothing folded, lists indented (yaml_dump_keep). Other formats are not affected.
):
    """
        Write data to file with format-specific serialization.

            Automatically serializes data based on file format (JSON, YAML, pickle, or text).

            Args:
                filepath (str): Path where file should be written.
                data: Data to write (dict/list for JSON/YAML, any object for pickle/text).
                encoding (str | None): Character encoding for text files. If None, auto-detected.
                fail_on_error (bool): If True, raises exception on error instead of returning error dict.
                logger: Optional logger for debug messages.
                sort_keys (bool): If True, sorts dictionary keys in JSON/YAML output.
                file_format (str | None): Force specific format ('json', 'yaml', 'pickle', 'text'). If None, auto-detected.
                newline (str): Newline character for text files. Default is '
        '.
                safe_dump (bool): Replace non-serializable JSON values with a marker string.
                keep (bool): Write YAML in the keep style (the style of a new _cmeta.yaml): the keys of
                             YAML_META_KEY_ORDER first, then the rest in the order given; long strings on
                             one line, multi-line strings as literal blocks, list items indented under
                             their key. JSON, pickle and text are written as without it.

            Returns:
                dict: Dictionary with 'return': 0 on success, or 'return' > 0 and 'error' on failure.

        Raises:
            Exception: Propagated runtime errors, if any.
    """

    if file_format is None:
        file_format = _detect_file_format(filepath)

    encoding = _get_encoding(encoding, file_format)

    mode = "wb" if encoding is None else "w"
    set_newline = None if encoding is None else newline

    try:
        with open(filepath, mode, encoding=encoding, newline=set_newline) as f:
            if file_format == "json":
                if safe_dump:
#                    sdata = make_json_serializable(data)
##                    f.write(safe_print_json_to_str(data, indent=2, sort=sort_keys))
##                    f.write("\n")
#                    json.dump(sdata, f, indent=2, sort_keys=sort_keys)
                    f.write(safe_json_dumps(data, indent=2, sort_keys=sort_keys))
                else:
                    json.dump(data, f, indent=2, sort_keys=sort_keys)
                f.write("\n")
            elif file_format == "yaml":
                if keep:
                    f.write(yaml_dump_keep(order_meta_keys(data), indent_lists=True))
                else:
                    yaml.safe_dump(data, f, sort_keys=sort_keys)
            elif file_format == "pickle":
                pickle.dump(data, f)
            else:
                f.write(str(data))

    except Exception as e:
        return _error(None, 1, e, fail_on_error)

    return {'return':0, 'encoding':encoding, 'mode':mode}


##########################################################################################
def safe_json_dumps(obj, sobj = "#NON-SERIALIZABLE#", **kwargs):
    """Serialize an object to JSON while replacing unsupported values.

    Args:
        obj: Object to serialize.
        sobj (str): Replacement value for objects that JSON cannot serialize.
        **kwargs: Additional keyword arguments forwarded to ``json.dumps``.

    Returns:
        str: Serialized JSON text.
    """
    def default(o):
        return sobj
    return json.dumps(obj, default=default, **kwargs)

##########################################################################################
# The "keep" style for YAML that is written over an existing file: the order of the keys is kept, a long
# string stays on one line (nothing is rewrapped), a multi-line string is a literal block. Comments can
# only be kept by editing the text (edit_yaml_text); this is the style of every rewritten or appended part.
YAML_DUMP_KEEP = {'sort_keys': False, 'allow_unicode': True, 'width': 1000000, 'default_flow_style': False}

if yaml is not None:
    class _YamlKeepDumper(yaml.SafeDumper):
        pass

    def _represent_str_keep(dumper, value):
        return dumper.represent_scalar('tag:yaml.org,2002:str', value, style = '|' if '\n' in value else None)

    _YamlKeepDumper.add_representer(str, _represent_str_keep)

    class _YamlKeepIndentDumper(_YamlKeepDumper):
        """The same, with the items of a list indented under their key (the style of most hand-written files)."""
        def increase_indent(self, flow=False, indentless=False):
            return super().increase_indent(flow, False)

##########################################################################################
def yaml_dump_keep(
    data,  # Data to dump (a dict or a list).
    indent_lists: bool = False,  # If True, the items of a list are indented under their key.
):
    """
        Dump YAML in the "keep" style: the order of the keys as given, long strings on one line, multi-line
        strings as literal blocks (YAML_DUMP_KEEP). Used for the parts of an existing file that are rewritten.

        Args:
            data: Data to dump.
            indent_lists (bool): If True, the items of a list are indented under their key ("  - a");
                                 PyYAML's default puts them at the key's column ("- a").

        Returns:
            str: The YAML text, ending with a line break.
    """
    dumper = _YamlKeepIndentDumper if indent_lists else _YamlKeepDumper
    return yaml.dump(data, Dumper=dumper, **YAML_DUMP_KEEP)

##########################################################################################
def _yaml_lists_are_indented(text):
    """True when the text indents the items of its lists under their keys ("  - a")."""
    return re.search(r'^[ \t]+- ', text, re.M) is not None

##########################################################################################
# The order of the top-level keys of a NEW YAML meta (the _cmeta.yaml that `cx <category> add --yaml`,
# a migrate stub or any other command creates): the identity, what it is, the attribution, the
# bookkeeping, what the engine needs; every other key follows in the order given. Only new files are
# ordered this way - an existing file keeps its own order (edit_yaml_text and the fallback dump of
# _write_yaml_keeping_text never reorder) - and JSON metas stay sorted as before.
YAML_META_KEY_ORDER = (
    'artifact', 'alias', 'category', 'name',                                       # identity
    'tags', 'desc', 'note',                                                        # what it is
    'authors', 'copyright', 'license',                                             # attribution
    'creation_timestamp', 'last_update_timestamp', 'generator', 'last_generator',
    'migrated_to', 'migrated_when',                                                # bookkeeping
    'min_cmeta_version', 'min_cmeta_version_api', 'last_api_version',
    'uses_categories', 'uses_artifacts',                                           # what the engine needs
)

##########################################################################################
def order_meta_keys(
    data,  # A mapping; anything else is returned as it is.
):
    """
        A copy of a meta mapping with the keys of YAML_META_KEY_ORDER first, in that order, and every
        other key after them in the order given (the order of a new _cmeta.yaml).

        Args:
            data: A mapping; anything else is returned unchanged.

        Returns:
            dict: The reordered (shallow) copy.
    """
    if not isinstance(data, dict):
        return data
    ordered = {k: data[k] for k in YAML_META_KEY_ORDER if k in data}
    for k, v in data.items():
        if k not in ordered:
            ordered[k] = v
    return ordered

##########################################################################################
def _yaml_last_index(node):
    """The character index right after the last content of a node (a block collection's own end mark
    points at the next key, past the comments and blank lines in between)."""
    if isinstance(node, yaml.CollectionNode) and not node.flow_style and node.value:
        last = node.value[-1]
        if isinstance(node, yaml.MappingNode):
            last = last[1]
        return _yaml_last_index(last)
    return node.end_mark.index

##########################################################################################
def edit_yaml_text(
    text: str,  # The YAML text of a file: a block mapping at the top level.
    data: dict,  # The mapping the text must load as afterwards.
):
    """
        Edit the text of a YAML mapping so that it loads as `data`, touching only the top-level keys whose
        values changed: the lines of such a key are replaced by a fresh dump of that key (yaml_dump_keep),
        removed keys are deleted, new keys are appended at the end. Comments, blank lines, quoting, the
        order of the keys and the line endings everywhere else stay byte-identical. A comment inside or at
        the end of a value that changed goes with the value.

        Args:
            text (str): The YAML text of a file.
            data (dict): The mapping the text must load as afterwards (string keys).

        Returns:
            str or None: The new text, or None when the text cannot be edited this way: not a block mapping
            at the top level, several documents, anchors or aliases, duplicate or non-string keys, a parse
            error. The caller then dumps the whole file.
    """
    if yaml is None or not isinstance(data, dict) or not all(isinstance(k, str) for k in data):
        return None

    try:
        for token in yaml.scan(text):
            if isinstance(token, (yaml.AnchorToken, yaml.AliasToken)):
                return None

        loader = yaml.SafeLoader(text)
        try:
            node = loader.get_single_node()
            if node is None or not isinstance(node, yaml.MappingNode) or node.flow_style:
                return None
            pairs = list(node.value)
            old = loader.construct_document(node)
        finally:
            loader.dispose()
    except yaml.YAMLError:
        return None

    if not isinstance(old, dict) or len(old) != len(pairs) or not all(isinstance(k, str) for k in old):
        return None

    bom = text.startswith('\ufeff')
    newline = '\r\n' if '\r\n' in text else '\n'
    indent = ' ' * pairs[0][0].start_mark.column if pairs else ''
    indent_lists = _yaml_lists_are_indented(text)

    def chunk(key):
        lines = yaml_dump_keep({key: data[key]}, indent_lists=indent_lists).split('\n')
        return newline.join(indent + line if line != '' else line for line in lines)

    # The lines of every key: from the start of the key's line to the end of the last line of its value
    edits = []
    previous_end = 1 if bom else 0
    for (key_node, value_node), key in zip(pairs, old):
        start = text.rfind('\n', 0, key_node.start_mark.index) + 1
        if bom and start == 0:
            start = 1

        end = max(_yaml_last_index(value_node), key_node.end_mark.index)
        while end > start and text[end - 1] in ' \t\r\n':
            end -= 1
        nl = text.find('\n', end)
        end = len(text) if nl < 0 else nl + 1

        if start < previous_end or end < start:
            return None
        previous_end = end

        if key not in data:
            edits.append((start, end, ''))
        elif old[key] != data[key]:
            edits.append((start, end, chunk(key)))

    for start, end, replacement in reversed(edits):
        text = text[:start] + replacement + text[end:]

    new_keys = [k for k in data if k not in old]
    if new_keys:
        if text != '' and not text.endswith(('\n', '\r')):
            text += newline
        text += ''.join(chunk(k) for k in new_keys)

    return text

##########################################################################################
def _replace_file(
    temp_path: str,  # The file just written.
    filepath: str,  # The file it replaces.
    logger = None,  # Optional logger for debug messages.
):
    """Replace a file atomically, with the retries that Windows needs after a lock."""
    for attempt in range(RETRY_REPLACE_FILE + 1):
        try:
            os.replace(temp_path, filepath)
            return
        except Exception as e:
            if attempt < RETRY_REPLACE_FILE:
                if logger is not None:
                    logger.debug(f"utils.files._replace_file - retrying replace for '{temp_path}' -> '{filepath}' (attempt {attempt + 1}) due to error: {str(e)}")
                time.sleep(RETRY_DELAY)
            else:
                raise

##########################################################################################
def _write_yaml_keeping_text(
    filepath: str,  # An existing YAML file.
    data: dict,  # The mapping the file must load as afterwards.
    encoding: str = 'utf-8',  # Encoding of the file.
    logger = None,  # Optional logger for debug messages.
):
    """
        Rewrite an existing YAML file so that it loads as `data`: a textual edit of the keys that changed
        (edit_yaml_text) when possible, else a full dump in the keep style (yaml_dump_keep). Either text is
        written next to the file, read back with the engine's own loader and compared with `data`; only a
        text that loads as `data` replaces the file (atomically). A full dump that loads but differs (a tuple
        becomes a list) is written too, as before. The file is never left broken or half-written.

        Returns:
            dict: {'return': 0, 'method': 'edit' | 'dump', 'validated': bool}, or 'return' > 0 and 'error'.
    """
    with open(filepath, 'r', encoding=encoding, newline='') as f:
        text = f.read()

    candidates = []

    edited = edit_yaml_text(text, data)
    if edited is not None:
        candidates.append(('edit', edited))

    dumped = yaml_dump_keep(data, indent_lists=_yaml_lists_are_indented(text))
    if '\r\n' in text:
        dumped = dumped.replace('\n', '\r\n')
    if text.startswith('\ufeff'):
        dumped = '\ufeff' + dumped
    candidates.append(('dump', dumped))

    temp_path = f"{filepath}.tmp"

    try:
        for method, new_text in candidates:
            with open(temp_path, 'w', encoding=encoding, newline='') as f:
                f.write(new_text)

            # Read back what is on disk with the engine's YAML loader (the .tmp name hides the format)
            try:
                with open(temp_path, 'r', encoding=encoding) as f:
                    loaded = yaml.safe_load(f)
                parsed = True
            except Exception as e:
                loaded = e
                parsed = False

            if logger is not None and not (parsed and loaded == data):
                logger.debug(f"utils.files._write_yaml_keeping_text - the {method} of '{filepath}' does not load as expected: {loaded if not parsed else 'different data'}")

            if (parsed and loaded == data) or (method == 'dump' and parsed):
                _replace_file(temp_path, filepath, logger)
                return {'return': 0, 'method': method, 'validated': parsed and loaded == data}

    finally:
        if os.path.isfile(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

    return {'return': 1, 'error': f"'{filepath}' could not be written as valid YAML; the file was left unchanged"}

##########################################################################################
def safe_write_file(
    filepath: str,  # Path where file should be written.
    data,  # Data to write (dict/list for JSON/YAML, any object for pickle/text).
    timeout: int = 3,  # Seconds to wait for lock acquisition. Default is 3.
    file_lock = None,  # Existing lock to use. If None, acquires new lock.
    atomic: bool = False,  # If True, writes to temp file then renames for atomicity.
    encoding: str = None,  # Character encoding for text files. If None, auto-detected.
    fail_on_error: bool = False,  # If True, raises exception on error instead of returning error dict.
    logger = None,  # Optional logger for debug messages.
    sort_keys: bool = True,  # If True, sorts dictionary keys in JSON/YAML output.
    preserve: bool = False,  # If True, an existing YAML file is edited in place: only the keys that changed are rewritten (see _write_yaml_keeping_text); a YAML file that does not exist yet is written in the keep style.
    keep: bool = False,  # If True, a YAML file is written in the keep style of a new _cmeta.yaml (write_file keep=True). Other formats are not affected.
):
    """
        Safely write data to file with locking and optional atomic write.

        Provides thread/process-safe file writing with file locking support.
        Supports atomic writes via temp file + rename for data integrity.

        With `preserve`, an existing YAML file keeps its text: only the top-level keys whose values
        changed are rewritten, new keys are appended, and the result is read back and compared with
        `data` before it replaces the file (a full dump that keeps the order of the keys and does not
        rewrap long strings is the fallback). A YAML file that does not exist yet is written in the
        keep style of a new meta (`keep`: the key order of YAML_META_KEY_ORDER, nothing folded, lists
        indented). Other formats are written as without `preserve` or `keep`.

        WARNING: This function uses blocking I/O operations. Not suitable for
        async contexts - use aiofiles and async locking instead.

        Args:
            filepath (str): Path where file should be written.
            data: Data to write (dict/list for JSON/YAML, any object for pickle/text).
            timeout (int): Seconds to wait for lock acquisition. Default is 3.
            file_lock: Existing lock to use. If None, acquires new lock.
            atomic (bool): If True, writes to temp file then renames for atomicity.
            encoding (str | None): Character encoding for text files. If None, auto-detected.
            fail_on_error (bool): If True, raises exception on error instead of returning error dict.
            logger: Optional logger for debug messages.
            sort_keys (bool): If True, sorts dictionary keys in JSON/YAML output.
            preserve (bool): If True, an existing YAML file is edited in place and validated; a new one is
                             written in the keep style.
            keep (bool): If True, a YAML file is written in the keep style of a new _cmeta.yaml.

        Returns:
            dict: Dictionary with 'return': 0 on success, or 'return' > 0 and 'error' on failure.
                  With `preserve` on an existing YAML file also 'method' ('edit' or 'dump') and 'validated'.

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    if logger is not None:
        logger.debug(f"utils.files.safe_write_file - preparing to write {filepath} ...")

    if Path(filepath).is_dir():
        return _error(f"'{filepath}' is a directory; safe_write only supports files.", 1, None, fail_on_error)

    if file_lock is None:
        try:
            file_lock = _acquire_lock(filepath, timeout, logger)
        except Exception as e:
            return _error(None, 1, e, fail_on_error)

    file_format = _detect_file_format(filepath)

    result = {'return': 0}
    release_error = None

    try:
        if preserve and file_format == 'yaml' and yaml is not None and Path(filepath).is_file():
            try:
                _check_lock(filepath, file_lock, logger)
            except Exception as e:
                return _error(None, 1, e, fail_on_error)

            try:
                r = _write_yaml_keeping_text(filepath, data, encoding=_get_encoding(encoding, file_format), logger=logger)
            except Exception as e:
                return _error(None, 1, e, fail_on_error)

            if r['return'] > 0:
                return _error(r['error'], r['return'], None, fail_on_error)

            result = r

        else:
            temp_path = f"{filepath}.tmp" if atomic else filepath

            # A new YAML meta gets the keep style whether asked for it or for `preserve`
            keep_style = keep or (preserve and file_format == 'yaml')

            r = write_file(temp_path, data, encoding=encoding, fail_on_error=fail_on_error, logger=logger, sort_keys=sort_keys, file_format=file_format, keep=keep_style)
            if r['return']>0: return r

            if atomic:
                try:
                    _check_lock(filepath, file_lock, logger)
                except Exception as e:
                    return _error(None, 1, e, fail_on_error)

                try:
                    _replace_file(temp_path, filepath, logger)
                except Exception as e:
                    return _error(None, 1, e, fail_on_error)

    finally:
        # Always release the lock: either if it was locked externally for writing
        # within the same process or if we acquired a lock inside this function
        try:
            _release_lock(filepath, file_lock, logger)
        except Exception as e:
            release_error = e

    if release_error:
        return _error(None, 1, release_error, fail_on_error)

    return result

##########################################################################################
def safe_delete_directory(
    dirpath: str,  # Full path to directory to delete.
    timeout: int = 3,  # Lock timeout in seconds.
    fail_on_error: bool = False,  # Whether to raise exceptions or return error dict.
    logger = None,  # Logger instance for debug messages.
):
    """
        Safely and recursively deletes a directory with all its contents.
        Works cross-platform (Windows, Linux, MacOS) and handles special cases like
        .git directories with read-only attributes.

        If lock acquisition fails but directory doesn't exist, returns success.

        Args:
            dirpath (str): Full path to directory to delete.
            timeout (int): Lock timeout in seconds.
            fail_on_error (bool): Whether to raise exceptions or return error dict.
            logger: Logger instance for debug messages.

        Returns:
            Dict with 'return' (0=success, non-zero=error) and optional 'error'.

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    if logger is not None:
        logger.debug(f"utils.files.self_delete_directory - preparing to delete {dirpath} ...")
    
    path = Path(dirpath)
    
    # Check if it's actually a directory
    if path.exists() and not path.is_dir():
        return _error(f"'{dirpath}' is not a directory", 1, None, fail_on_error)
    
    file_lock = None
    lock_acquired = False
    
    # Try to acquire lock
    try:
        file_lock = _acquire_lock(dirpath, timeout, logger)
        lock_acquired = True
        if logger is not None:
            logger.debug(f"utils.files.self_delete_directory - lock acquired for {dirpath}")
    except Exception as e:
        if logger is not None:
            logger.debug(f"utils.files.self_delete_directory - failed to acquire lock for {dirpath}: {str(e)}")
        
        # If lock failed, check if directory still exists
        if not path.exists():
            if logger is not None:
                logger.debug(f"utils.files.self_delete_directory - directory {dirpath} doesn't exist, returning success")
            return {'return': 0}
        
        # Directory exists but we couldn't lock it
        return _error(f"Could not acquire lock and directory still exists: {str(e)}", 1, e, fail_on_error)
    
    try:
        # Double-check directory still exists after acquiring lock
        if not path.exists():
            if logger is not None:
                logger.debug(f"utils.files.self_delete_directory - directory {dirpath} disappeared after lock, returning success")
            return {'return': 0}
        
        def handle_remove_readonly(
            func,  # Function that failed (e.g., os.remove, os.rmdir).
            path,  # Path to the file/directory that couldn't be removed.
            exc,  # Exception information.
        ):
            """
                Error handler for shutil.rmtree to handle read-only files.

                Clears readonly bit and retries deletion. Important for .git
                directories on Windows.

                Args:
                    func: Function that failed (e.g., os.remove, os.rmdir).
                    path: Path to the file/directory that couldn't be removed.
                    exc: Exception information.

                Returns:
                    dict: Operation result.
                Raises:
                    Exception: Propagated runtime errors, if any.
            """
            if logger is not None:
                logger.debug(f"utils.files.self_delete_directory - handling read-only file: {path}")
            
            # Clear the readonly bit and retry
            try:
                os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
                func(path)
            except Exception as e:
                if logger is not None:
                    logger.debug(f"utils.files.self_delete_directory - failed to remove {path}: {str(e)}")
                raise
        
        # Retry deletion with exponential backoff
        last_error = None
        for attempt in range(RETRY_DELETE_ATTEMPTS):
            try:
                if logger is not None:
                    logger.debug(f"utils.files.self_delete_directory - attempt {attempt + 1} to delete {dirpath}")
                
                shutil.rmtree(dirpath, onerror=handle_remove_readonly)
                
                if logger is not None:
                    logger.debug(f"utils.files.self_delete_directory - successfully deleted {dirpath}")
                break
                
            except Exception as e:
                last_error = e
                
                # Check if directory was deleted by another process
                if not path.exists():
                    if logger is not None:
                        logger.debug(f"utils.files.self_delete_directory - directory {dirpath} was deleted externally")
                    break
                
                if attempt < RETRY_DELETE_ATTEMPTS - 1:
                    delay = RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                    if logger is not None:
                        logger.debug(f"utils.files.self_delete_directory - retrying delete after {delay}s due to: {str(e)}")
                    time.sleep(delay)
                else:
                    return _error(f"Failed to delete directory after {RETRY_DELETE_ATTEMPTS} attempts: {str(e)}", 1, e, fail_on_error)
        
        # Final verification
        if path.exists():
            if last_error:
                return _error(f"Directory still exists after deletion attempts: {str(last_error)}", 1, last_error, fail_on_error)
        
        return {'return': 0}
        
    finally:
        # Always release lock if it was acquired
        if lock_acquired and file_lock is not None:
            try:
                _release_lock(dirpath, file_lock, logger)
                if logger is not None:
                    logger.debug(f"utils.files.self_delete_directory - lock released for {dirpath}")
            except Exception as e:
                if logger is not None:
                    logger.debug(f"utils.files.self_delete_directory - error releasing lock: {str(e)}")
                # Don't fail on lock release error if deletion succeeded
                if not fail_on_error:
                    pass
                else:
                    raise

##########################################################################################
def safe_delete_directory_if_empty(
    dirpath: str,  # Path to the directory to potentially delete.
):
    """
        Delete directory only if it's empty (no files or subdirectories).

        Quickly checks if directory is empty and removes it. Ignores all errors
        (permissions, race conditions, etc.) for safe cleanup operations.

        Args:
            dirpath (str): Path to the directory to potentially delete.

        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """
    try:
        if os.path.isdir(dirpath):
            with os.scandir(dirpath) as it:
                if not any(it):  # stops immediately if one entry exists
                    os.rmdir(dirpath)
    except OSError:
        pass  # ignore permission/race/other errors safely

    return {'return':0}

##########################################################################################
def lock_path(
    path: str,  # Path to lock (file or directory).
    timeout: int = 3,  # Seconds to wait for lock acquisition. Default is 3.
    fail_on_error: bool = False,  # If True, raises exception on error instead of returning error dict.
    logger = None,  # Optional logger for debug messages.
):
    """
        Acquire a lock on a file or directory path.

        Args:
            path (str): Path to lock (file or directory).
            timeout (int): Seconds to wait for lock acquisition. Default is 3.
            fail_on_error (bool): If True, raises exception on error instead of returning error dict.
            logger: Optional logger for debug messages.

        Returns:
            dict: Dictionary with 'return': 0 and 'file_lock' on success,
                  or 'return' > 0 and 'error' on failure.

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    if logger is not None:
        logger.debug(f"utils.files.lock_path - preparing to lock path {path} ...")

    try:
        file_lock = _acquire_lock(path, timeout, logger)
        return {'return': 0, 'file_lock': file_lock}
    except Exception as e:
        return _error(None, 1, e, fail_on_error)

##########################################################################################
def unlock_path(
    path: str,  # Path to unlock (file or directory).
    file_lock,  # FileLock object from lock_path().
    fail_on_error: bool = False,  # If True, raises exception on error instead of returning error dict.
    logger = None,  # Optional logger for debug messages.
):
    """
        Release a lock on a file or directory path.

        Args:
            path (str): Path to unlock (file or directory).
            file_lock: FileLock object from lock_path().
            fail_on_error (bool): If True, raises exception on error instead of returning error dict.
            logger: Optional logger for debug messages.

        Returns:
            dict: Error dict with 'return' > 0 and 'error' on failure, None on success.

        Raises:
            Exception: Propagated runtime errors, if any.
    """

    if logger is not None:
        logger.debug(f"utils.files.unlock_path - preparing to unlock path {path} ...")

    try:
        _release_lock(path, file_lock, logger)
    except Exception as e:
        return _error(None, 1, e, fail_on_error)

    return {'return':0}

##########################################################################################
def safe_read_file_via_cache(
    filepath: str,  # Path to the file to read.
    cache: dict,  # Dictionary to store cached data (modified in-place).
    timeout: int = 10,  # Lock timeout for file operations.
    fail_on_error: bool = False,  # Whether to raise exceptions or return error dict.
    logger = None,  # Optional logger for debug messages
):
    """
        Reads a file with caching based on file modification timestamp.
        Automatically reloads if file has been modified since last cache.

        WARNING: This function is NOT thread-safe for async usage. The cache dictionary
        can be corrupted by concurrent access, and it uses blocking I/O operations.

        Args:
            filepath (str): Path to the file to read.
            cache (dict): Dictionary to store cached data (modified in-place).
            timeout (int): Lock timeout for file operations.
            fail_on_error (bool): Whether to raise exceptions or return error dict.
            logger: Optional logger for debug messages

        Returns:
            Dict with 'return' (0=success, non-zero=error) and 'data' or 'error'.

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    path = Path(filepath)
    
    if path.is_dir():
        return _error(f"'{filepath}' is a directory; safe_read_file_via_cache only supports files.", 1, None, fail_on_error)
    
    for attempt in range(RETRY_NOT_FOUND_INDEX_FILE + 1):
        if path.exists():
            break

        return _error(f"'{filepath}' does not exist", ERROR_CODE_FILE_NOT_FOUND, None, fail_on_error)
    
    try:
        # Retry getting file timestamp RETRY_TIMESTAMP_FILE+1 times with small delay
        for attempt in range(RETRY_TIMESTAMP_FILE + 1):
            try:
                current_timestamp = path.stat().st_mtime
                break  # Success, exit retry loop
            except Exception as e:
                if attempt < RETRY_TIMESTAMP_FILE:  # Don't delay after last attempt
                    if logger is not None:
                        logger.debug(f"utils.files.safe_read_file_via_cache - retrying getmtime for '{filepath}' (attempt {attempt + 1}) due to error: {str(e)}")
                    time.sleep(RETRY_DELAY)
                else:
                    return _error(None, 1, e, fail_on_error)

    except Exception as e:
        return _error(f"Could not get file timestamp: {str(e)}", 1, e, fail_on_error)
    
    # Check if file is in cache and timestamp matches
    if filepath in cache:
        cached_entry = cache[filepath]
        if cached_entry.get('timestamp') == current_timestamp:
            return {'return': 0, 'data': cached_entry['data']}

        if logger is not None:
            logger.debug(f"utils.files.safe_read_file_via_cache - recaching changed index file {filepath} ...")
    
    # Cache miss or file changed - read the file
    if logger is not None:
        logger.debug(f"utils.files.safe_read_file_via_cache - reading index file {filepath} ...")

    result = safe_read_file(filepath, timeout=timeout, fail_on_error=fail_on_error, logger=logger)
    
    if result['return'] == 0:
        # Update cache with new data and timestamp
        cache[filepath] = {
            'data': result['data'],
            'timestamp': current_timestamp
        }
    
    return result

##########################################################################################
def safe_read_yaml_or_json(
    filepath: str,  # Path to file (extension will be ignored/removed).
    lock: bool = False,  # Whether to use file locking.
    keep_locked: bool = False,  # Whether to keep lock after successful read.
    timeout: int = 3,  # Lock timeout.
    fail_on_error: bool = False,  # Whether to raise exceptions or return error dict.
    retry_if_not_found: int = 0,  # Number of retries if file not found.
    logger = None,  # Logger instance for debug messages.
):
    """
        Safely reads a YAML or JSON file by trying YAML first, then JSON.
        Removes any existing extension from filepath and tries .yaml, then .json.

        Args:
            filepath (str): Path to file (extension will be ignored/removed).
            lock (bool): Whether to use file locking.
            keep_locked (bool): Whether to keep lock after successful read.
            timeout (int): Lock timeout.
            fail_on_error (bool): Whether to raise exceptions or return error dict.
            retry_if_not_found (int): Number of retries if file not found.
            logger: Logger instance for debug messages.

        Returns:
            Dict with 'return' (0=success, non-zero=error) and 'data' or 'error'.
            If keep_locked=True and lock=True, also returns 'file_lock'.

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    if yaml is None:
        return _error("YAML library not available. Install with: pip install pyyaml", 1, None, fail_on_error)
    
    # Remove extension from filepath
    path = Path(filepath)
    base_path = path.parent / path.stem
    
    if logger is not None:
        logger.debug(f"utils.files.safe_read_yaml_or_json - trying to read {base_path} as YAML or JSON...")
    
    # Try YAML first
    yaml_path = f"{base_path}.yaml"
    if Path(yaml_path).exists():
        if logger is not None:
            logger.debug(f"utils.files.safe_read_yaml_or_json - found YAML file: {yaml_path}")
        return safe_read_file(yaml_path, lock=lock, keep_locked=keep_locked, timeout=timeout, 
                            fail_on_error=fail_on_error, retry_if_not_found=retry_if_not_found, logger=logger)
    
    # Try JSON if YAML doesn't exist
    json_path = f"{base_path}.json"
    if Path(json_path).exists():
        if logger is not None:
            logger.debug(f"utils.files.safe_read_yaml_or_json - found JSON file: {json_path}")
        return safe_read_file(json_path, lock=lock, keep_locked=keep_locked, timeout=timeout, 
                            fail_on_error=fail_on_error, retry_if_not_found=retry_if_not_found, logger=logger)
    
    # Neither file exists
    return _error(f"'{base_path}(.yaml or .json)' do not exist", ERROR_CODE_FILE_NOT_FOUND, None, fail_on_error)

##########################################################################################
def _get_encoding(
    encoding: str = None,  # User-provided encoding (None, '', or specific encoding string).
    file_format: str = None,  # File format (e.g., 'json', 'yaml', 'pickle', 'binary').
):
    """
        Determine the appropriate encoding for file operations.

        Args:
            encoding (str | None): User-provided encoding (None, '', or specific encoding string).
            file_format (str | None): File format (e.g., 'json', 'yaml', 'pickle', 'binary').

        Returns:
            str or None: Encoding to use ('utf-8' for text formats, None for binary).

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    if encoding == '': 
        encoding = None
    
    elif encoding is None:
        if file_format in ['json', 'yaml', 'txt', 'text', 'md', 'html', 'htm']:
            encoding = 'utf-8'
    
    return encoding

##########################################################################################
def unzip(
    filename: str,  # Path to ZIP file to extract.
    path: str = None,  # Destination directory (defaults to current directory).
    remove_directories: int = 0,  # Number of leading directory levels to strip from paths.
    skip_directories: list = None,  # List of directory names to skip during extraction.
    overwrite: bool = True,  # If True, overwrite existing files.
    clean: bool = False,  # If True, delete ZIP file after successful extraction.
    fail_on_error: bool = False,  # If True, raises exception on error instead of returning error dict.
):
    """
        Extract a ZIP archive to a directory.

        Args:
            filename (str): Path to ZIP file to extract.
            path (str | None): Destination directory (defaults to current directory).
            remove_directories (int): Number of leading directory levels to strip from paths.
            skip_directories (list | None): List of directory names to skip during extraction.
            overwrite (bool): If True, overwrite existing files.
            clean (bool): If True, delete ZIP file after successful extraction.
            fail_on_error (bool): If True, raises exception on error instead of returning error dict.

        Returns:
            dict: Dictionary with 'return': 0 on success, or 'return' > 0 and 'error' on failure.

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    
    if skip_directories is None:
        skip_directories = []

    if not path:
        path = os.getcwd()

    if not os.path.exists(path):
        os.makedirs(path)

    try:
        with zipfile.ZipFile(filename, 'r') as zip_ref:
            for member in zip_ref.infolist():
                # Get original path
                orig_path = member.filename

                # Split path
                parts = orig_path.split('/')
                # Remove empty parts
                parts = [p for p in parts if p]
                
                if not parts:
                    continue

                # Check if we need to skip directories
                skip = False
                for s in skip_directories:
                    if s in parts:
                        skip = True
                        break
                if skip:
                    continue

                # Check if we need to remove starting directories
                if len(parts) <= remove_directories:
                    continue
                
                new_parts = parts[remove_directories:]
                
                target_path = os.path.join(path, *new_parts)
                
                # Check if directory
                if member.is_dir() or orig_path.endswith('/'):
                    if not os.path.exists(target_path):
                        os.makedirs(target_path)
                    continue

                # It's a file
                target_dir = os.path.dirname(target_path)
                if not os.path.exists(target_dir):
                    os.makedirs(target_dir)

                if os.path.exists(target_path) and not overwrite:
                    continue

                with zip_ref.open(member) as source, open(target_path, "wb") as target:
                    shutil.copyfileobj(source, target)

    except Exception as e:
        return _error(f"Failed to unzip {filename}: {e}", 1, e, fail_on_error)

    if clean:
        try:
            os.remove(filename)
        except Exception as e:
            return _error(f"Failed to remove zip file {filename}: {e}", 1, e, fail_on_error)

    return {'return': 0}

##########################################################################################
def zip_directory(
    source_dir: str,  # Path to the directory to zip.
    output_path: str,  # Path where the zip file will be created.
    skip_directories: list = None,  # List of directory names/patterns to skip (e.g., ['.git', '__pycache__', 'tmp*']).
    fail_on_error: bool = True,  # Whether to raise exceptions or return error dict.
    logger = None,  # Logger instance for debug messages
    skip_files: list = None,  # List of file names or glob patterns to exclude from the archive.
):
    """
        Creates a zip archive from a directory.

        Args:
            source_dir (str): Path to the directory to zip.
            output_path (str): Path where the zip file will be created.
            skip_directories (list | None): List of directory names or glob patterns to skip (e.g., ['.git', '__pycache__', 'tmp*']).
            fail_on_error (bool): Whether to raise exceptions or return error dict.
            logger: Logger instance for debug messages

            skip_files (list): List of file names or glob patterns to exclude from the archive.
        Returns:
            Dict with 'return' (0=success, non-zero=error) and optional 'error'.

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    if skip_directories is None:
        skip_directories = []
    
    source_path = Path(source_dir)
    
    if not source_path.exists():
        return _error(f"Source directory '{source_dir}' does not exist", 1, None, fail_on_error)
    
    if not source_path.is_dir():
        return _error(f"'{source_dir}' is not a directory", 1, None, fail_on_error)
    
    if logger is not None:
        logger.debug(f"utils.files.zip_directory - creating zip archive from {source_dir} to {output_path}")
    
    try:
        # Ensure output directory exists
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
            for file_path in source_path.rglob('*'):
                # Check if any parent directory should be skipped
                skip = False
                for parent in file_path.relative_to(source_path).parts:
                    if skip_directories and any(fnmatch.fnmatch(parent, pattern) for pattern in skip_directories):
                        skip = True
                        break

                if skip:
                    if logger is not None:
                        logger.debug(f"utils.files.zip_directory - skipping {file_path}")
                    continue
                
                # Add file or directory to zip
                if file_path.is_file():
                    arcname = file_path.relative_to(source_path)

                    if skip_files and str(arcname) in skip_files:
                        if logger is not None:
                            logger.debug(f"utils.files.zip_directory - skipping {file_path}")
                        continue

                    zip_ref.write(file_path, arcname)
                    if logger is not None:
                        logger.debug(f"utils.files.zip_directory - added {arcname}")
        
        if logger is not None:
            logger.debug(f"utils.files.zip_directory - successfully created {output_path}")
       
    except Exception as e:
        return _error(f"Failed to create zip archive: {str(e)}", 1, e, fail_on_error)

    return {'return': 0, 'output_path': output_path}

##########################################################################################
def shard_name(
    name: str,  # Name to shard (file or directory name).
    slices = None,  # List of integers specifying shard lengths (e.g., [2, 2] creates 2-char shards).
):
    """
        Apply sharding to a single path component.

        Generates shard directory names from a name string based on specified slice lengths.
        If the name is shorter than required, uses underscore-filled placeholders to ensure
        predictable directory structure.

        Args:
            name: Name to shard (file or directory name).
            slices: List of integers specifying shard lengths (e.g., [2, 2] creates 2-char shards).
                    None means no sharding.

        Returns:
            list: List containing shard directory names followed by the original name.
                  Example: shard_name('example', [2, 2]) -> ['ex', 'am', 'example']

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    if not slices:
        parts = [name]
    else:
        parts = []
        start = 0
        for length in slices:
            end = start + length
            
            # Extract shard from name, padding with underscores if needed
            if start < len(name):
                shard = name[start:end].lower() # important to enable faster search ...
                # Fill remainder with underscores if shard is shorter than expected
                if len(shard) < length:
                    shard = shard + '_' * (length - len(shard))
            else:
                # If we've exhausted the name, use underscores
                shard = '_' * length
            
            shard = shard.replace(' ', '_')

            # Avoiding glitches on Windows
            if shard.endswith('.'): shard = shard[:-1] + '_'
            
            parts.append(shard)
            start = end
        
        # Final element is the actual original name (always)
        parts.append(name)
    
    return {'return':0, 'parts': parts}


##########################################################################################
def apply_sharding_to_path(
    path: str,  # Base directory path to prepend to sharded path.
    name: str,  # Name to shard.
    slices: list,  # List of integers specifying shard lengths (e.g., [2, 2]).
):
    """
        Apply sharding to construct a full sharded directory path.

        Combines a base path with sharded directory components generated from a name.

        Args:
            path: Base directory path to prepend to sharded path.
            name: Name to shard.
            slices: List of integers specifying shard lengths (e.g., [2, 2]).

        Returns:
            dict: Dictionary with 'return': 0, 'sharded_parts': list of path components,
                  and 'sharded_path': full sharded path string. On error, 'return' > 0.

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    r = shard_name(name, slices)
    if r['return']>0: return r

    sharded_parts = r['parts']

    # Compose final result:
    # path / (sharded path parts)

    sharded_path = os.path.join(*sharded_parts)

    if path is not None:
       full_path = os.path.join(path, sharded_path)
    else:
       full_path = sharded_path

    return {'return':0, 'sharded_parts': sharded_parts, 'sharded_path': full_path}

##########################################################################################
def safe_delete_directory_if_empty_with_sharding(
    artifact_path: str,  # Path to the artifact directory.
    sharding_slices: list = None,  # Sharding configuration from category meta.
):
    """
        Safely delete empty directories up the hierarchy based on sharding configuration.

        Args:
            artifact_path (str): Path to the artifact directory.
            sharding_slices (list | None): Sharding configuration from category meta.

        Returns:
            dict: A cMeta dictionary with the following keys
                - **return** (int): 0 if success, >0 if error.
                - **error** (str): Error message if `return > 0`.

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    current_path = os.path.dirname(artifact_path)
    extra_levels = 1 if sharding_slices is None else len(sharding_slices) + 1

    for _i in range(extra_levels):
        r = safe_delete_directory_if_empty(current_path)
        if r['return'] > 0: return r

        if os.path.isdir(current_path): break

        current_path = os.path.dirname(current_path)

    return {'return': 0}

##########################################################################################
def get_latest_tree_modification_time(
    path,  # Filesystem path.
):
    """
        Return the maximum modification time (mtime) of the directory
        or any file/directory inside it (recursively).
        Works on Linux, macOS, and Windows.

        Args:
            path: Filesystem path.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """
    latest = os.path.getmtime(path)

    # Stack for our own DFS (faster than recursion)
    stack = [path]

    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        m = entry.stat().st_mtime
                        if m > latest:
                            latest = m

                        # Recurse into subdirectories
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)

                    except FileNotFoundError:
                        # Entry disappeared during scan — skip
                        pass
        except (NotADirectoryError, PermissionError):
            # Not a directory or forbidden — ignore
            pass

    return {'return':0, 'latest': latest}

##########################################################################################
def get_latest_modification_time(
    path,  # Filesystem path.
):
    """
        Return last modification timestamp for a path as a datetime object.

        Args:
            path: Filesystem path.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """

    from datetime import datetime

    mtime = os.path.getmtime(path)
    modified_dt = datetime.fromtimestamp(mtime)

    return {'return':0, 'last': modified_dt}



##########################################################################################
def get_creation_time(
    path,  # Filesystem path.
):
    """
        Return creation (or closest available) timestamp for a path.

        Args:
            path: Filesystem path.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """

    import sys
    from datetime import datetime

    stat = os.stat(path)

    # Windows: true creation time
    if sys.platform.startswith("win"):
        return datetime.fromtimestamp(stat.st_ctime)

    # macOS / BSD: true birth time
    if hasattr(stat, "st_birthtime"):
        return datetime.fromtimestamp(stat.st_birthtime)

    # Linux fallback: last content modification time
    return datetime.fromtimestamp(stat.st_mtime)

##########################################################################################
def quote_path(
    path,  # Filesystem path.
):
    """
        Add double quotes around a path when it contains spaces.

        Args:
            path: Filesystem path.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """

    if not path.startswith('"') and (' ' in path or ',' in path or '+' in path):
        path = '"' + path + '"'

    return path

##########################################################################################
def quote_path2(
    path,  # Filesystem path.
):
    """
        Add double quotes with \\ around a path when it contains spaces.
        Useful for sub-tools such as adb or rcp

        Args:
            path: Filesystem path.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """

    if not path.startswith('"') and (' ' in path or ',' in path or '+' in path):
        path = '\\"' + path + '\\"'

    return path

##########################################################################################
def files_encode(
    files,  # Value for files.
):
    """
        files: list of file paths
        returns: dict {filename: base64_string}

        Args:
            files: Value for files.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """
    import base64

    try:
        files_base64 = {}

        for path in files:
            if os.path.isfile(path):
                filename = os.path.basename(path)
                with open(path, "rb") as f:
                    data = f.read()
                    files_base64[filename] = base64.b64encode(data).decode("utf-8")
    except Exception as e:
        return {'return':1, 'error': str(e)}

    return {'return':0, 'files_base64': files_base64}

##########################################################################################
def files_decode(
    files_base64,  # Value for files base64.
):
    """
        files_base64: dict {filename: base64_string}
        returns: dict {filename: binary_bytes}

        Args:
            files_base64: Value for files base64.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """
    import base64

    try:
        files = {}

        for filename, b64_data in files_base64.items():
            files[filename] = base64.b64decode(b64_data)

    except Exception as e:
        return {'return':1, 'error': str(e)}

    return {'return':0, 'files': files}

##########################################################################################
def gen_temp_filepath(
    template = None,  # Value for template.
):
    """
        Generate a temporary file path using an optional template.

        Args:
            template: Value for template.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """

    import tempfile
    import uuid
    import os

    tmp_dir = tempfile.gettempdir()

    if template is None or template == '':
        template = 'cmeta-{uid}.tmp'

    template = template.replace('{uid}', str(uuid.uuid4()))

    temp_filepath = os.path.join(tmp_dir, template)

    return {'return':0, 'filepath': temp_filepath}

##########################################################################################
def _to_extended_path(
    path,  # Filesystem path.
):
    """
        Convert a path to a Windows extended-length path (\\\\?\\...) to avoid
        MAX_PATH (260 char) limitations for deeply nested build trees.
        No-op on non-Windows platforms.

        Args:
            path: Filesystem path.
        Returns:
            str: Possibly-prefixed path.
    """
    p = os.fspath(path)

    if os.name != 'nt':
        return p

    p = os.path.abspath(p)

    if p.startswith('\\\\?\\'):
        return p

    if p.startswith('\\\\'):
        return '\\\\?\\UNC\\' + p[2:]

    return '\\\\?\\' + p

##########################################################################################
def _force_remove(
    path,  # Filesystem path.
):
    """
        Best-effort removal of a single file or (empty) directory entry.

        Clears the read-only attribute before removing, uses extended-length
        paths on Windows to cope with deep/long build paths, and retries a
        few times with short delays to ride out transient locks held by
        antivirus, search indexing or cloud-sync agents.

        Args:
            path: Filesystem path.
        Returns:
            None
        Raises:
            Exception: Propagated if the entry could not be removed after retries.
    """
    p = _to_extended_path(path)

    last_exc = None

    for attempt in range(5):
        try:
            try:
                os.chmod(p, stat.S_IWRITE)
            except OSError:
                pass

            if os.path.isdir(p) and not os.path.islink(p):
                os.rmdir(p)
            else:
                os.unlink(p)

            return
        except FileNotFoundError:
            return
        except (PermissionError, OSError) as e:
            last_exc = e
            time.sleep(0.1 * (attempt + 1))

    raise last_exc

##########################################################################################
def _handle_remove_readonly(
    func,  # Value for func.
    path,  # Filesystem path.
    exc_info,  # Value for exc info.
):
    """
        Error handler for shutil.rmtree that removes read-only attributes
        and retries removal (see `_force_remove`).

        Args:
            func: Value for func.
            path: Filesystem path.
            exc_info: Value for exc info.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """
    _force_remove(path)

##########################################################################################
def remove_files_and_dirs_in_path(
    path,  # Filesystem path.
    pattern = '*',  # Value for pattern.
    ignore = None,  # Value for ignore.
):
    """
        Recursively remove files and directories in `path` matching `pattern`,
        while ignoring any names matching items in `ignore`.

        Parameters
        ----------
        path : str or Path
            Root directory to operate on.
        pattern : str
            Wildcard pattern (fnmatch-style) to match files/directories.
        ignore : list[str], optional
            List of wildcard patterns for files/directories to ignore.
            Matching is done against the basename.

        Examples
        --------
        remove_files_and_dirs_in_path(
            path=".",
            pattern="*.log",
            ignore=["keep.log", "important_*"]
        )

        Args:
            path: Filesystem path.
            pattern: Value for pattern.
            ignore: Value for ignore.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """
    root = Path(path)
    ignore = ignore or []

    def is_ignored(
        p: Path,  # Value for p.
    ) -> bool:
        """
            Return True when a path basename matches any ignore pattern.

            Args:
                p: Value for p.
            Returns:
                bool: Result value.
            Raises:
                Exception: Propagated runtime errors, if any.
        """
        return any(fnmatch.fnmatch(p.name, ig) for ig in ignore)

    for item in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if is_ignored(item):
            continue

        if fnmatch.fnmatch(item.name, pattern):
            try:
                if item.is_dir():
                    shutil.rmtree(
                        item,
                        onerror=_handle_remove_readonly,
                    )
                else:
                    _force_remove(item)
            except FileNotFoundError:
                pass

    return {'return':0}

##########################################################################################
def ask_to_delete(
    con,  # If True, print output to console.
    force,  # If True, force operation.
    path,  # Filesystem path.
    name = None,  # Object or artifact name.
    text = None,  # Value for text.
    space = False,  # Indentation prefix for console output.
):
    """
        Prompt for deletion confirmation in console mode.

        Args:
            con: If True, print output to console.
            force: If True, force operation.
            path: Filesystem path.
            name: Object or artifact name.
            text: Value for text.
            space: Indentation prefix for console output.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """

    confirmed = True
    if con:
        xname = name if name is not None else "artifact"
        xtext = text if text is not None else f'Deleting {xname} located at "{path}" ...'
        
        if space:
            print ('')

        print (xtext)

        if not force:
            x = input('  Proceed (y/N)? ')
            x = x.strip().lower()

            if x not in ['y', 'yes']:
                print ('    Skipped!')
                confirmed = False

    return {'return':0, 'confirmed': confirmed}

##########################################################################################
def is_dir_empty(
    path,  # Filesystem path.
    clean = False,  # Value for clean.
):
    """
        Check if a directory is empty and optionally remove it.

        Args:
            path: Filesystem path.
            clean (bool): If True, remove the directory when it is found to be empty.
        Returns:
            bool: True if the path is an existing, empty directory, else False.
        Raises:
            Exception: Propagated runtime errors, if any.
    """
    if not os.path.isdir(path):
        return False

    try:
        empty = not any(os.scandir(path))
        if empty and clean:
            os.rmdir(path)  # only removes empty directories
        return empty
    except PermissionError:
        return False

############################################################
def load_files(
    path,  # Filesystem path.
    load_files,  # Value for load files.
    fail_on_error = False,  # Value for fail on error.
    logger = None,  # Value for logger.
    timeout = 1,  # Timeout value in seconds.
):
    """
        Load selected files from a directory using safe readers.

        Args:
            path: Filesystem path.
            load_files: Value for load files.
            fail_on_error: Value for fail on error.
            logger: Value for logger.
            timeout: Timeout value in seconds.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """

    loaded_files = {}

    for filename in load_files:

        file_path = os.path.join(path, filename)

        # If filename has no extension, try .json then .yaml if those files exist
        if os.path.splitext(filename)[1] == '':
            json_path = os.path.join(path, filename + '.json')
            yaml_path = os.path.join(path, filename + '.yaml')
            if os.path.isfile(json_path):
                file_path = json_path
            elif os.path.isfile(yaml_path):
                file_path = yaml_path
        
        loaded_files[filename] = {'path': file_path}
        
        if os.path.isfile(file_path):
            r = safe_read_file(file_path, fail_on_error = fail_on_error, logger = logger, timeout = timeout)
            if r['return']>0: return r

            loaded_files[filename]['data'] = r['data']

    return {'return':0, 'loaded_files': loaded_files}

############################################################
def md5sum(
    path,  # Filesystem path.
    chunk_size = 100000,  # Number of bytes to read per iteration when hashing file content.
):
    """
        Calculate md5sum

        Args:

            path: Filesystem path.
            chunk_size: Number of bytes to read per iteration when hashing file content.
        Returns:
           (CM return dict):

           * return (int): return code == 0 if no error and >0 if error
           * (error) (str): error string if return>0

           * md5sum (str): md5sum of the give file

        Raises:
            Exception: Propagated runtime errors, if any.
    """

    import sys
    import hashlib

    try:
        with open(path, "rb") as f:
            file_hash = hashlib.md5()
            while chunk := f.read(chunk_size):
                file_hash.update(chunk)

        md5sum = file_hash.hexdigest()
    
    except Exception as e:
        err = f'problem calculating md5sum for "{path}" ({e})'
        return {'return':1, 'error': err}

    return {'return':0, 'md5sum': md5sum}

############################################################
def cpath(
    path,  # Filesystem path.
):
    """
        Normalize and quote a path string for shell usage.

        Args:
            path: Filesystem path.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """

    if path:
        path = path.strip()
        if ' ' in path:
            if not path.startswith('"') and not path.endswith('"'):
                path = f'"{path}"'

    return path

############################################################
def parse_env_dump(
    data: str,  # Input data object.
) -> dict[str, str]:
    """
        Parse KEY=VALUE lines into an environment dictionary.

        Args:
            data: Input data object.
        Returns:
            dict[str, str]: Result value.
        Raises:
            Exception: Propagated runtime errors, if any.
    """
    env = {}

    for line in data.splitlines():
        line = line.strip()

        # skip empty lines
        if not line:
            continue

        # skip invalid lines (rare but safe)
        if "=" not in line:
            continue

        key, value = line.split("=", 1)  # IMPORTANT: split once
        env[key] = value

    return {'return':0, 'env': env}

############################################################
def diff_env(
    old: dict[str, str],  # Old environment dictionary.
    new: dict[str, str],  # New environment dictionary.
):
    """
        Diff two environment dicts and return added/removed variables.

        Args:
            old (dict[str, str]): Old environment dictionary.
            new (dict[str, str]): New environment dictionary.

        Returns:
            dict: Dictionary with 'env_added' and 'env_removed' keys containing
                  usable environment dictionaries with fuzzy PATH expansion.

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    env_added = {}
    env_removed = {}

    all_keys = set(old) | set(new)

    for key in all_keys:
        old_val = old.get(key)
        new_val = new.get(key)

        # Variable was added
        if old_val is None:
            env_added[key] = new_val
            continue

        # Variable was removed
        if new_val is None:
            env_removed[key] = old_val
            continue

        # unchanged
        if old_val == new_val:
            continue

        # --- fuzzy PATH-like diff ---
        if os.pathsep in old_val or os.pathsep in new_val:
            old_parts = set(filter(None, old_val.split(os.pathsep)))
            new_parts = set(filter(None, new_val.split(os.pathsep)))

            added = sorted(new_parts - old_parts)
            removed = sorted(old_parts - new_parts)

            if added:
                env_added[key] = os.pathsep.join(added)
            if removed:
                env_removed[key] = os.pathsep.join(removed)

        else:
            # normal value changed - store new as added, old as removed
            env_added[key] = new_val
            env_removed[key] = old_val

    return {
        'return': 0,
        'env_added': env_added,
        'env_removed': env_removed
    }

############################################################
def remove_dirs_from_path(
    path: str,
    num: int = 0,
):
    """Remove trailing directory levels from a path.

    Args:
        path (str): Starting filesystem path.
        num (int): Number of parent directory levels to remove.

    Returns:
        dict: A successful cMeta return dictionary containing the resulting ``path``.
    """

    for _ in range(0, num):
        path = os.path.dirname(path)

    return {'return':0, 'path': path}
