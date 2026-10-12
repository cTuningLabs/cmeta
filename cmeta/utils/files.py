"""
Reusable functions for safe loading, storing and caching of files 

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import sys
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
import binascii

from .common import _error, ask as _ask

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

# The age of a soft lock is counted from the time its holder WROTE INTO IT, read on this machine's clock, and an
# empty file by how long the waiter itself has seen it - never by the time the file system gave the file: a drive
# can keep another clock (a network share, a Windows drive inside WSL2) or keep times to the whole second.
LOCK_SOFT_STALE_SECONDS = 600    # a soft lock taken longer ago than this by a holder on another host is stale
LOCK_SOFT_EMPTY_STALE_SECONDS = 2.0  # an EMPTY soft lock file that a waiter has seen empty for this long is a leftover (a holder writes its content at once)
LOCK_SOFT_DEAD_MIN_AGE_SECONDS = 1.0  # a soft lock of a dead pid taken less than this ago is a release in flight, not a crash
LOCK_SOFT_CHECK_SECONDS = 0.25   # how often a waiter on a soft lock reads the file to check for a stale holder
LOCK_SOFT_REMOVE_SECONDS = 2.0   # how long a releasing soft lock retries the removal of its file (Windows: a reader may hold it)
LOCK_SOFT_TAKE_TRIES = 25        # tries of the rename that takes a stale soft lock over (Windows: a reader may hold a file for an instant)
LOCK_SOFT_TAKE_REMOVE_SECONDS = 0.2  # how long a waiter retries the removal of the take file it did not use
LOCK_SOFT_READ_MAX = 1024        # bytes read from a soft lock file (its one line: pid host time system)
LOCK_SOFT_HEARTBEAT_SECONDS = 2.0    # a soft holder rewrites the time in its line this often (the heartbeat; soft mode only)
LOCK_SOFT_SILENT_SECONDS = 20.0  # a soft lock whose line a waiter has seen unchanged for this long is the leftover of a holder that is gone
LOCK_SOFT_PATHS_ENV = 'CMETA_SOFT_LOCK_PATHS'  # folders whose lock files use the soft lock (a home or repository written by several systems at once)
LOCK_IDENTITY_RETRIES = 50       # consecutive identity mismatches after which a path is locked with the soft lock
LOCK_NOTE_MAX = 512              # bytes of the note a holder may leave in its lock file for the message of a waiter
LOCK_TIMEOUT_ENV = 'CMETA_LOCK_TIMEOUT'
LOCK_TIMEOUT = 30                # seconds a writer waits for the lock of a file (the environment variable changes it)
LOCK_NOTICE_SECONDS = 3          # a waiter says so on stderr after this long
READ_RETRY_SECONDS = 3           # how long a read without a lock is retried when the file cannot be read (a write in progress)
PICKLE_PROTOCOL = 4              # readable by every Python the engine supports, whatever the default of the Python that writes
ERROR_CODE_FILE_NOT_FOUND = 16
RETRY_DELAY = 0.1                # between the retries of a read; the longest delay between the retries of a replace
RETRY_NOT_FOUND_FILE = 10
RETRY_NOT_FOUND_INDEX_FILE = 3   # short retries of a cached file that is missing for a moment (a replace, the swap of a reindex)
RETRY_NOT_FOUND_DELAY = 0.025
RETRY_TIMESTAMP_FILE = 10
RETRY_DELETE_ATTEMPTS = 5

_REPLACE_BUSY_ERRNOS = tuple(e for e in (getattr(errno, name, None) for name in ('EACCES', 'EPERM', 'EBUSY', 'ETXTBSY')) if e is not None)

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
#   anywhere: the soft lock (the file created with O_EXCL, holding "pid host time system") where the
#             file system refuses both OS locks (some FUSE, 9p and SMB mounts), where the identity check
#             keeps failing, or where it is ASKED FOR - a home or repository that several systems write at
#             once through a shared drive (a Windows tree plugged from WSL2 or a container, a network
#             share), whose OS locks do not see each other: CMETA_SOFT_LOCK_PATHS names such folders,
#             `lock: soft` in a repository's _cmr.yaml names the repository (use_soft_lock_under). The
#             holder keeps its file open and rewrites the time in its line every LOCK_SOFT_HEARTBEAT_SECONDS;
#             a stale soft lock (its pid dead on this system, or its line unchanged for
#             LOCK_SOFT_SILENT_SECONDS on the waiter's own clock - the holder is on another system or host)
#             is taken over by ONE of the waiters that find it: it replaces the file by its own in one
#             rename (PathLock._take_stale_soft_lock). A lock file of cMeta before 0.35.0 (no system, no
#             heartbeat) is judged as before: the pid when the host name is this one, else its age against
#             LOCK_SOFT_STALE_SECONDS.
# In every mode the threads of one process are serialized on the path first (a threading.Lock per path),
# which POSIX record locks and soft locks need (they are per process), and the busy wait polls with a
# delay that doubles from LOCK_POLL_START to LOCK_POLL_MAX until the timeout. The engine's own writers
# (_acquire_lock) wait LOCK_TIMEOUT seconds (CMETA_LOCK_TIMEOUT) and say so on stderr after
# LOCK_NOTICE_SECONDS, naming the holder when it left a note in the lock file (_acquire_with_notice).

_LOCK_BUSY_ERRNOS = tuple(e for e in (getattr(errno, name, None) for name in ('EWOULDBLOCK', 'EAGAIN', 'EACCES', 'EDEADLK', 'EDEADLOCK')) if e is not None)
_LOCK_UNSUPPORTED_ERRNOS = tuple(e for e in (getattr(errno, name, None) for name in ('ENOLCK', 'ENOSYS', 'EOPNOTSUPP', 'ENOTSUP', 'EINVAL', 'ENOTTY', 'EPERM', 'EBADF')) if e is not None)

_lock_registry = {}               # normalized lock file path -> threading.Lock (the threads of this process)
_lock_registry_guard = threading.Lock()
_lock_soft_paths = set()          # lock files locked with the soft lock from now on (the OS lock was refused)
_lock_soft_dirs = []              # folders whose lock files use the soft lock because it was asked for (use_soft_lock_under)
_lock_no_flock_dirs = set()       # folders where flock was refused (POSIX record locks are tried first there)
_lock_host = None
_lock_system = None
_beat_lock = threading.Lock()     # guards _beat_held, and every write of a beat
_beat_held = {}                   # id(lock) -> the soft locks this process holds and beats (PathLock._start_heartbeat)
_beat_thread = None               # the one heartbeat thread of the process, started with the first soft lock held
_beat_wake = threading.Event()    # the thread sleeps on it (never set: a plain sleep that reads the interval each time)


def _after_fork_in_child():
    """A forked child starts with locks of its own: the thread locks of the parent (the registry of the paths,
    the guard of the registry, the lock of the heartbeat) may have been held by a thread that does not exist in
    the child - the parent's heartbeat thread, another thread of the parent - and would be held for ever; the
    soft locks the parent beats are not the child's to beat (its copy of a lock never releases it either:
    PathLock.release)."""
    global _lock_registry_guard, _beat_lock, _beat_thread
    _lock_registry_guard = threading.Lock()
    _lock_registry.clear()
    _beat_lock = threading.Lock()
    _beat_held.clear()
    _beat_thread = None


if hasattr(os, 'register_at_fork'):
    os.register_at_fork(after_in_child=_after_fork_in_child)


def _beat_forever():
    """The heartbeat thread: every LOCK_SOFT_HEARTBEAT_SECONDS, the line of every soft lock this process holds
    is rewritten (PathLock._write_beat). The locks a forked child inherited are its parent's: dropped."""
    while True:
        _beat_wake.wait(LOCK_SOFT_HEARTBEAT_SECONDS)
        try:
            with _beat_lock:
                for key, lock in list(_beat_held.items()):
                    if lock._owner_pid != os.getpid():
                        _beat_held.pop(key, None)
                        continue
                    lock._write_beat()
        except Exception:
            pass


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


def _lock_system_id():
    """
    A short name of the system this process runs on, written into a soft lock file so that a waiter knows
    whether the pid in the file is one it can check: the same name means the same kernel and the same pid
    space. Windows and WSL2 share the host name and have different pids; a container shares the kernel of
    its host (one boot) and has its own pid space; a cloned machine keeps its host name.
      Linux:   the boot id of the kernel and the pid namespace of this process (/proc);
      Windows: the machine's installation id (the registry);
      macOS:   the machine's id (sysctl kern.uuid);
      else, or where those cannot be read: the host name and the platform.
    Twelve hex digits of a hash of it, computed once per process.
    """
    global _lock_system
    if _lock_system is None:
        parts = [sys.platform]
        try:
            if sys.platform.startswith('linux'):
                with open('/proc/sys/kernel/random/boot_id') as f:
                    parts.append(f.read().strip())
                parts.append(str(os.stat('/proc/self/ns/pid').st_ino))
            elif sys.platform == 'win32':
                import winreg
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography') as key:
                    parts.append(str(winreg.QueryValueEx(key, 'MachineGuid')[0]))
            elif sys.platform == 'darwin':
                import ctypes
                libc = ctypes.CDLL(None)
                size = ctypes.c_size_t(0)
                if libc.sysctlbyname(b'kern.uuid', None, ctypes.byref(size), None, 0) == 0 and 0 < size.value < 256:
                    buf = ctypes.create_string_buffer(size.value)
                    if libc.sysctlbyname(b'kern.uuid', buf, ctypes.byref(size), None, 0) == 0:
                        parts.append(buf.value.decode('ascii', 'replace'))
        except Exception:
            pass
        if len(parts) < 2:
            parts.append(_lock_host_name())
        _lock_system = hashlib.sha1('\n'.join(parts).encode('utf-8', 'replace')).hexdigest()[:12]
    return _lock_system


def _soft_lock_paths_from_env():
    """The folders named by CMETA_SOFT_LOCK_PATHS (os.pathsep between them; '*' = everywhere), normalized."""
    value = os.environ.get(LOCK_SOFT_PATHS_ENV, '')
    folders = []
    for folder in value.split(os.pathsep):
        folder = folder.strip()
        if folder == '':
            continue
        folders.append('*' if folder == '*' else os.path.normcase(os.path.abspath(folder)))
    return folders


def use_soft_lock_under(
    folder: str,  # The folder (a home, a repository) whose lock files use the soft lock from now on in this process.
):
    """
        Ask for the soft lock for every lock file under `folder` (see the notes on the path lock: a home or
        repository that several systems write at once through a shared drive, whose OS locks do not see
        each other). The engine calls it for a repository whose descriptor says `lock: soft`; the environment
        variable CMETA_SOFT_LOCK_PATHS names folders at the start of a process. '*' means everywhere.

        Returns:
            dict: {'return': 0}
    """
    folder = '*' if folder == '*' else os.path.normcase(os.path.abspath(folder))
    if folder not in _lock_soft_dirs:
        _lock_soft_dirs.append(folder)
    return {'return': 0}


def _soft_lock_asked_for(lock_file):
    """Whether `lock_file` lies under a folder for which the soft lock was asked (use_soft_lock_under)."""
    if not _lock_soft_dirs:
        return False
    if '*' in _lock_soft_dirs:
        return True
    path = os.path.normcase(os.path.abspath(lock_file))
    for folder in _lock_soft_dirs:
        if path == folder or path.startswith(folder.rstrip(os.sep) + os.sep):
            return True
    return False


_lock_soft_dirs.extend(_soft_lock_paths_from_env())   # CMETA_SOFT_LOCK_PATHS, read once at the start of the process


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
        self._empty_seen = {}             # path -> (identity, monotonic time): the empty soft lock files this waiter watches
        self._own_empty = None            # (identity,) of the empty file this object's refused OS-lock attempt left
        self._noted = False               # a note was written into the held lock file (see _own_identity)
        self._line = None                 # the line of the soft lock this object holds (the heartbeat rewrites it)
        self._wrote = None                # the line of a soft lock file this object wrote and could not confirm
        self._beat_seen = {}              # path -> (identity, content, monotonic time): the lines this waiter watches for a heartbeat
        self._owner_pid = None            # the process that took the lock (a forked child never releases its parent's lock)

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

        self._owner_pid = os.getpid()           # before the lock is taken: the heartbeat thread reads it
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
            self._owner_pid = None
            self._drop_unconfirmed()
            thread_lock.release()
            raise

    def release(self):
        """Release the lock and remove its file (when the file at the path is still the one this lock holds)."""
        if not self.is_locked:
            return

        if self._owner_pid is not None and self._owner_pid != os.getpid():
            # A forked child of the holder: the lock is its parent's. The child's copy forgets it and touches
            # neither the file nor the descriptor (a POSIX record lock is not even the child's to release)
            self._fd = self._thread_lock = None
            self._ident = self._line = None
            self._noted = self.is_locked = False
            self.mode = None
            return

        try:
            if self.mode == 'windows':
                try:
                    msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
                ident = self._own_identity()
                os.close(self._fd)
                self._unlink_own_file(ident)

            elif self.mode in ('flock', 'lockf'):
                self._unlink_own_file(self._own_identity())
                try:
                    self._posix_unlock(self._fd, self.mode)
                except OSError:
                    pass
                os.close(self._fd)

            elif self.mode == 'soft':
                self._stop_heartbeat()
                self._remove_soft_file()

        finally:
            self._fd = None
            self._ident = None
            self._line = None
            self._noted = False
            self._owner_pid = None
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
        self._noted = True
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
        if self.lock_file in _lock_soft_paths or _soft_lock_asked_for(self.lock_file):
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

    @staticmethod
    def _soft_line():
        """The line of a soft lock this process holds: `pid host time system`. The time is the moment of the
        last write (the heartbeat rewrites the line in place, so its length never changes); the system (see
        _lock_system_id) tells a waiter whether it can check the pid."""
        return f"{os.getpid()} {_lock_host_name()} {time.time():.3f} {_lock_system_id()}\n".encode('utf-8', 'replace')

    def _try_soft(self):
        line = self._soft_line()
        try:
            fd = os.open(self.lock_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0), 0o644)
        except FileExistsError as e:
            self._last_error = e
            now = time.monotonic()
            if now < self._next_stale_check:
                return False
            self._next_stale_check = now + LOCK_SOFT_CHECK_SECONDS

            # The file of a holder that is gone is taken over in the same attempt: a single try (timeout 0, the
            # probe of a cache entry) finds the lock of a dead process free
            return self._take_stale_soft_lock(line)
        except OSError as e:
            if self._open_failed_for_the_moment(e):
                return False
            raise

        try:
            os.write(fd, line)
        except BaseException:
            os.close(fd)
            raise
        return self._soft_lock_taken(line, fd)

    def _soft_lock_taken(self, line, fd=None):
        """
        The last step of taking the soft lock: the file at the path must be the file this object wrote. It is
        not when that file was taken over in the instant it was still empty (this process was stopped between
        creating it and writing into it for as long as an empty file is watched) - the lock is then not held,
        and nothing at the path is touched.

        fd: the open descriptor of the written file, when there is one. It stays open while the lock is held:
        an open file keeps its identity (no new file gets its inode number), so "the file at the path is the
        one this descriptor holds" is an exact answer, here and at release, for the price of two calls that
        open nothing. (And on Windows a file that is open cannot be replaced: the lock of a live holder
        cannot be taken over there at all.) Where the identity does not say so - no descriptor (a file
        renamed into place by a take-over, a file found later), a file system without inode numbers or one
        that reports them differently by descriptor and by path - the line in the file decides.
        """
        mine = None
        if fd is not None:
            try:
                mine = self._identity(os.fstat(fd))
                if mine is not None and self._identity(os.stat(self.lock_file)) == mine:
                    return self._hold_soft(line, fd, mine)
            except OSError:
                pass

        status, held = 'unreadable', None
        for _ in range(3):
            status, held = self._open_if_mine(line)
            if status in ('mine', 'other'):
                break
            time.sleep(0.002)               # not readable for an instant (Windows: a scanner holds the new file), or not shown yet

        if status == 'mine':
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            try:
                mine = self._identity(os.fstat(held))
            except OSError:
                mine = None
            return self._hold_soft(line, held, mine)
        if status == 'unreadable' and fd is not None:
            return self._hold_soft(line, fd, mine)      # it cannot be asked: the file this object made is its lock, as before

        # Not held. Should the file with this line be at the path later after all (a file system slow to show
        # a new file), it is this object's lock (_take_stale_soft_lock), and an acquire that gives up removes
        # it (_drop_unconfirmed)
        if fd is not None:
            os.close(fd)
        self._wrote = line
        return False

    def _hold_soft(self, line, fd, ident):
        self._fd = fd
        self._ident = ident
        self._line = line
        self._wrote = None
        self._own_empty = None
        self._empty_seen = {}
        self._beat_seen = {}
        self.mode = 'soft'
        self._start_heartbeat()
        return True

    # ---- the heartbeat of a soft holder ------------------------------------------------------
    #
    # A soft holder rewrites the time in its line every LOCK_SOFT_HEARTBEAT_SECONDS (one daemon thread per
    # process for all the soft locks it holds; the line is rewritten in place through the held descriptor:
    # same length, never empty). A waiter that sees the same line for LOCK_SOFT_SILENT_SECONDS on its own
    # monotonic clock knows the holder is gone - whatever the other system's clock says, however long the
    # holder has held the lock, and without a pid it could not check (a holder on another host, or on
    # another system of this host: Windows and WSL2 share the host name and have different pids). A lock
    # file without a system (3 words: written by cMeta before 0.35.0, which did not beat) is judged as
    # before: the pid when the host name is this one, else the age of its time against LOCK_SOFT_STALE_SECONDS.

    def _start_heartbeat(self):
        if self._fd is None:
            return                          # no descriptor to write through (the line decides for the waiters: see the rules)
        global _beat_thread
        with _beat_lock:
            _beat_held[id(self)] = self
            if _beat_thread is None or not _beat_thread.is_alive():
                _beat_thread = threading.Thread(target=_beat_forever, name='cmeta-soft-lock-heartbeat', daemon=True)
                _beat_thread.start()        # its first beat comes after one interval: a lock held for less never beats

    def _stop_heartbeat(self):
        with _beat_lock:                    # a beat of this lock in flight ends before the lock goes on
            _beat_held.pop(id(self), None)

    def _write_beat(self):
        fd = self._fd
        if fd is None:
            return
        line = self._soft_line()
        try:
            if hasattr(os, 'pwrite'):
                os.pwrite(fd, line, 0)
            else:
                os.lseek(fd, 0, os.SEEK_SET)
                os.write(fd, line)
        except (OSError, ValueError):
            return                          # the drive refuses for the moment: the line stays as it is
        self._line = line

    def _open_if_mine(self, line):
        """Open the file at the lock path and keep it open when it carries `line`: ('mine', descriptor);
        ('other', None) when it carries something else, ('gone', None) when it is not there, ('unreadable',
        None) when it cannot be read at the moment. Open for writing too: the heartbeat writes through it."""
        try:
            fd = os.open(self.lock_file, os.O_RDWR | getattr(os, 'O_BINARY', 0))
        except FileNotFoundError:
            return 'gone', None
        except OSError:
            return 'unreadable', None
        try:
            data = os.read(fd, LOCK_SOFT_READ_MAX)
        except OSError:
            os.close(fd)
            return 'unreadable', None
        if data != line:
            os.close(fd)
            return 'other', None
        return 'mine', fd

    def _drop_unconfirmed(self):
        """An acquire gives up: a file at the path that carries a line this object wrote and could not confirm
        (see _soft_lock_taken) would keep everybody out for as long as this process lives - it goes."""
        wrote, self._wrote = self._wrote, None
        if wrote is None:
            return
        seen = self._read_lock_file(self.lock_file)
        if seen and seen[1] == wrote:
            self._remove_file(self.lock_file, LOCK_SOFT_TAKE_REMOVE_SECONDS)

    @classmethod
    def _read_lock_file(cls, path):
        """(identity, content, time of the file) of a soft lock file; False when it is not there, None when it
        cannot be read at the moment."""
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0))
        except FileNotFoundError:
            return False
        except OSError:
            return None
        try:
            st = os.fstat(fd)
            data = os.read(fd, LOCK_SOFT_READ_MAX) if st.st_size > 0 else b''
        except OSError:
            return None
        finally:
            os.close(fd)
        return cls._identity(st), data, st.st_mtime

    def _lock_file_is(self, path, seen):
        """Whether the file at `path` is still the one read as `seen`: the same content and, where the file
        system reports one, the same identity."""
        now = self._read_lock_file(path)
        return bool(now) and now[1] == seen[1] and (now[0] is None or seen[0] is None or now[0] == seen[0])

    def _soft_file_is_stale(self, path, seen):
        """Whether the soft lock file read as `seen` (or the take file of a waiter, which carries the same
        line) is the leftover of a holder that is gone:
          - marked released by a holder that could not remove it;
          - a line of four words (`pid host time system`: a holder that beats, cMeta 0.35.0 and later): its pid
            is dead on THIS system (the system is this one; taken at least LOCK_SOFT_DEAD_MIN_AGE_SECONDS ago, so
            that a holder that has just released and exited is not a crash), or this waiter has seen the same
            line for LOCK_SOFT_SILENT_SECONDS on its own monotonic clock (the holder beats no more: dead on
            another system or host, or stopped);
          - a line of three words (a holder of cMeta before 0.35.0, which does not beat): its pid is dead on
            this host (the host name is this one), or it was taken longer ago than LOCK_SOFT_STALE_SECONDS;
          - it is empty and this waiter has seen it empty for LOCK_SOFT_EMPTY_STALE_SECONDS (a holder writes
            its line right after it creates the file), or it is the empty file this object's own OS-lock
            attempt has just left.
        How long ago a lock was taken is read from the time its holder wrote into it, on this machine's clock.
        The time the file system gave the file is not used - on a drive that keeps another clock (a Windows
        drive inside WSL2 is seconds off, a network share can be more) a fresh lock file looked old - except
        where nothing else dates the file: a line without a time (not written by this code), and an empty file
        that nobody watches (older than LOCK_SOFT_STALE_SECONDS it is a leftover whatever the clock of the drive)."""
        ident, data, mtime = seen
        words = data.decode('utf-8', 'replace').split()

        if not words:
            if path == self.lock_file and self._own_empty is not None and self._own_empty[0] == ident:
                return True
            now = time.monotonic()
            watched = self._empty_seen.get(path)
            if watched is None or watched[0] != ident:
                watched = self._empty_seen[path] = (ident, now)
            return now - watched[1] > LOCK_SOFT_EMPTY_STALE_SECONDS or time.time() - mtime > LOCK_SOFT_STALE_SECONDS

        self._empty_seen.pop(path, None)
        if words[0] == 'released':
            return True

        try:
            age = time.time() - float(words[2])
        except (IndexError, ValueError):
            age = None
        if age is None or age != age or abs(age) == float('inf'):
            age = time.time() - mtime

        pid = int(words[0]) if words[0].isascii() and words[0].isdigit() else None

        if len(words) >= 4:
            # A holder that beats (cMeta 0.35.0 and later: the fourth word names its system). Its pid is checked
            # when it is a pid of THIS system; whatever the system, a line that has not changed for
            # LOCK_SOFT_SILENT_SECONDS on this waiter's own clock is the leftover of a holder that is gone.
            if pid is not None and words[3] == _lock_system_id() and age > LOCK_SOFT_DEAD_MIN_AGE_SECONDS and not _lock_pid_alive(pid):
                return True
            now = time.monotonic()
            watched = self._beat_seen.get(path)
            if watched is None or watched[0] != ident or watched[1] != data:
                self._beat_seen[path] = (ident, data, now)
                return False
            return now - watched[2] > LOCK_SOFT_SILENT_SECONDS

        # A holder that does not beat (cMeta before 0.35.0): its pid when the host name is this one, else how
        # long ago it was taken
        if pid is not None and len(words) > 1 and words[1] == _lock_host_name():
            return age > LOCK_SOFT_DEAD_MIN_AGE_SECONDS and not _lock_pid_alive(pid)
        return age > LOCK_SOFT_STALE_SECONDS

    def _take_stale_soft_lock(self, line):
        """
        Take the soft lock over from a holder that is gone (see _soft_file_is_stale). Returns True when this
        object holds the lock.

        The stale file is never removed: the waiter REPLACES it by a file that carries its own line (one
        atomic rename), so the path is never free in between and nobody else can slip in. The file to put
        there is made first, exclusively, under a name that says which stale file it is for
        (`<lock file>.take-<checksum of that file's content and identity>`): of the waiters that judged the
        same stale file only one gets to make it, and it then checks that the file at the path is still the
        one it judged before it replaces it. A waiter that comes later finds another file at the path and
        gives up. (Before, the stale file was renamed away, checked and - when it was not the judged one -
        put back: between the two a third process could take the free path, which under load could end
        with two holders and a leftover `.stale-*` file.)
        """
        seen = self._read_lock_file(self.lock_file)
        if not seen:
            return False
        if self._wrote is not None and seen[1] == self._wrote:
            return self._soft_lock_taken(self._wrote)       # the file this object wrote a moment ago
        if not self._soft_file_is_stale(self.lock_file, seen):
            return False

        data = seen[1]
        take = self._take_file(seen)
        try:
            fd = os.open(take, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0), 0o644)
        except FileExistsError:
            # Another waiter is taking this very file over - or died doing so, and its take file is a leftover
            theirs = self._read_lock_file(take)
            if theirs and self._soft_file_is_stale(take, theirs) and self._lock_file_is(take, theirs):
                self._remove_file(take)
            return False
        except OSError:
            return False

        taken = False
        try:
            os.write(fd, line)

            # Closed before the rename, everywhere: Windows refuses to rename a file this process has open,
            # and a Windows drive seen through 9p (WSL2's /mnt/d, a container's bind mount) renames it but
            # shows nothing at the new path until the descriptor is closed (the lock looked "gone" to the
            # taker itself); the file is opened again at its new path to hold it (_soft_lock_taken)
            os.close(fd)
            fd = None
            for _ in range(LOCK_SOFT_TAKE_TRIES):
                if not self._lock_file_is(self.lock_file, seen):
                    break                   # not the file that was judged any more: judged again at the next check
                try:
                    os.replace(take, self.lock_file)
                except PermissionError:
                    # Windows: a waiter that reads one of the two files holds it for an instant - and a holder
                    # that is alive after all holds its file open for as long as it holds the lock
                    time.sleep(0.002)
                    continue
                except OSError:
                    break
                taken = True
                break
        finally:
            if fd is not None:
                try:
                    os.close(fd)            # the write failed before the close above
                except OSError:
                    pass
            if not taken:
                self._wrote = line          # see _soft_lock_taken: a file with this line that reaches the path is this object's
                self._remove_file(take, LOCK_SOFT_TAKE_REMOVE_SECONDS)

        if not taken:
            return False

        words = data.decode('utf-8', 'replace').split()
        left_by = "an empty file" if not words else ("marked released" if words[0] == 'released' else ' '.join(words[:2]))
        self.logger.warning(f"utils.files.PathLock - took over the stale lock file {self.lock_file} (left by {left_by})")
        return self._soft_lock_taken(line)

    def _take_file(self, seen):
        """The name of the file a waiter makes to replace the stale lock file read as `seen`: one name per
        stale file (its content and identity), so that one waiter only can make it."""
        return f"{self.lock_file}.take-{binascii.crc32(seen[1] + repr(seen[0]).encode('ascii', 'replace')) & 0xffffffff:08x}"

    @staticmethod
    def _remove_file(path, seconds=0.0):
        """Remove a file, retrying for `seconds` while it is held (Windows: a reader has it open); best effort."""
        deadline = time.monotonic() + seconds
        while True:
            try:
                os.unlink(path)
                return
            except PermissionError:
                if time.monotonic() >= deadline:
                    return
                time.sleep(0.002)
            except OSError:
                return

    def _fall_back_to_soft(self, why):
        if self.lock_file not in _lock_soft_paths:
            _lock_soft_paths.add(self.lock_file)
            self.logger.warning(f"utils.files.PathLock - the file system refuses OS locks for {self.lock_file} ({why}): a soft lock file is used instead (best effort between hosts)")

        # The empty file the OS-lock attempt created or found is not a soft lock (a soft holder writes its line
        # at once): this object takes it over at once, without the time an empty file is otherwise watched
        try:
            st = os.stat(self.lock_file)
            self._own_empty = (self._identity(st),) if st.st_size == 0 else None
        except OSError:
            self._own_empty = None

    def _remove_soft_file(self):
        """Remove the soft lock file - when it is still the file of this lock (a file taken over by a waiter
        that judged this holder gone is theirs): the file at the path is the one this lock's descriptor holds
        or, where the identity does not say so, it carries this lock's line. On Windows a waiter reading the
        file holds it open for a moment, so the removal is retried, and a file that cannot be removed in time
        is marked released for the waiters to take over."""
        fd, self._fd = self._fd, None
        mine = self._ident
        try:
            if fd is not None:
                try:
                    mine = self._identity(os.fstat(fd))
                except OSError:
                    pass

                # Closed before the removal, everywhere: Windows cannot remove a file this process has open,
                # and a Windows drive seen through 9p keeps the path of an open file in a removed-but-there
                # state until the descriptor is closed. Nothing is lost by it: the soft lock is the line in
                # the file, not the descriptor (a waiter judges the holder by its pid or its heartbeat)
                try:
                    os.close(fd)
                except OSError:
                    pass
                fd = None

            deadline = time.monotonic() + LOCK_SOFT_REMOVE_SECONDS
            while True:
                ours = False
                if mine is not None:
                    try:
                        ours = self._identity(os.stat(self.lock_file)) == mine
                    except FileNotFoundError:
                        return
                    except OSError:
                        ours = False
                if not ours:
                    seen = self._read_lock_file(self.lock_file)
                    if seen is False:
                        return
                    if seen is not None and self._line is not None and seen[1] != self._line:
                        return         # not ours any more
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

        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass

    @staticmethod
    def _identity(st):
        """The (inode, device) of a stat result; None where the file system reports no inode (some FAT drivers)."""
        if not st.st_ino:
            return None
        return (st.st_ino, st.st_dev)

    def _own_identity(self):
        """The identity of the file this lock's descriptor holds. It is the one seen when the lock was taken -
        unless a note was written into the file since: a file system without real inodes can give a file
        another number at its first write (exFAT on macOS: an empty file has a placeholder until `write_note`
        fills it), and the old number would say "not ours" for our own file - the lock file stayed behind
        after every lock with a note. Then the descriptor is asked again, now."""
        if not self._noted:
            return self._ident
        try:
            return self._identity(os.fstat(self._fd))
        except (OSError, TypeError, ValueError):
            return self._ident

    def _unlink_own_file(self, ident):
        """Remove the lock file, unless the file at the path is no longer the one this lock holds (someone
        removed it under us and another process created a new one: that one is theirs). ident: the identity
        of our file (`_own_identity`, taken while the descriptor is open)."""
        if ident is not None:
            try:
                if self._identity(os.stat(self.lock_file)) != ident:
                    return
            except OSError:
                return
        try:
            os.unlink(self.lock_file)
        except OSError:
            pass


##########################################################################################
def lock_timeout(
    default: float = LOCK_TIMEOUT,  # The seconds used when the environment variable is not set.
    env_name: str = LOCK_TIMEOUT_ENV,  # The environment variable that changes it.
    logger = None,  # Optional logger for the warning about a value that is not a number.
):
    """
        The seconds a writer waits for a lock: `default` (LOCK_TIMEOUT, 30 s, for the lock of a file)
        unless the environment variable `env_name` (CMETA_LOCK_TIMEOUT) holds a number of seconds; a value
        that is not a number is ignored with a warning.

        Returns:
            float: The seconds (0 or more).
    """
    x = os.environ.get(env_name, '').strip()
    if x != '':
        try:
            return max(float(x), 0.0)
        except ValueError:
            (logger if logger is not None else logging.getLogger('cmeta.utils.files')).warning(
                f'{env_name}="{x}" is not a number of seconds - {default:g} is used')
    return max(float(default), 0.0)

##########################################################################################
def _acquire_with_notice(
    lock,  # The PathLock to take.
    timeout: float,  # Seconds to wait in all.
    subject: str,  # What is locked, for the messages ("the index in <path>", "'<file>'").
    what: str,  # What waits ("the write of a record"), for the notice.
    env_name: str,  # The environment variable that changes the timeout, named in the messages.
    note: str = None,  # A note left in the lock file for the waiters (see PathLock.acquire).
    logger = None,  # Optional logger: the notice is a warning there too.
):
    """
        Take `lock` within `timeout` seconds. A waiter that has not got it after LOCK_NOTICE_SECONDS says
        so on stderr, naming the holder when it left a note in the lock file, and keeps waiting for the rest
        of the time; when the lock stays held, the TimeoutError names the holder and the environment
        variable that lengthens the wait.

        Returns:
            PathLock: the lock, acquired.

        Raises:
            TimeoutError: the lock stayed held for `timeout` seconds.
    """
    timeout = max(float(timeout), 0.0)
    first = min(float(LOCK_NOTICE_SECONDS), timeout)

    try:
        return lock.acquire(timeout=first, note=note)
    except TimeoutError as e:
        holder = PathLock.read_note(lock.lock_file)
        held_by = f' ({holder})' if holder else ''
        if timeout <= first:
            raise TimeoutError(f'{subject} stayed locked by another process{held_by} for {timeout:g} s ({e}) - set {env_name} to wait longer')

    message = (f'cMeta: {subject} is locked by another process{held_by} - '
               f'{what} continues when it is released (waiting up to {timeout:g} s; {env_name} changes it)')
    print(message, file=sys.stderr, flush=True)
    if logger is not None:
        logger.warning(message)

    try:
        return lock.acquire(timeout=max(timeout - first, 0.0), note=note)
    except TimeoutError as e:
        raise TimeoutError(f'{subject} stayed locked by another process{held_by} for {timeout:g} s ({e}) - set {env_name} to wait longer')

acquire_with_notice = _acquire_with_notice   # the public name (the task engine of cmeta-aops waits on a cache entry with it)

##########################################################################################
def _acquire_lock(
    filepath: str,  # Path to the file to lock.
    timeout: float = None,  # Seconds to wait for the lock; None: the engine's lock timeout (lock_timeout(): 30 s, CMETA_LOCK_TIMEOUT changes it).
    logger = None,  # Optional logger for debug messages.
    what: str = None,  # What waits, named in the notice of a waiter ("the write of '<file>'").
    note: str = None,  # A note left in the lock file for the waiters (who holds it and why).
):
    """
        Acquire the lock of a path (`<filepath>.lock`, see PathLock) for process- and thread-safe
        file operations. Blocks until the lock is acquired or the timeout expires; a waiter says so on
        stderr after LOCK_NOTICE_SECONDS (see _acquire_with_notice).

        Args:
            filepath (str): Path to the file to lock.
            timeout (float | None): Seconds to wait for the lock; None: the engine's lock timeout
                                    (LOCK_TIMEOUT, 30 s; the environment variable CMETA_LOCK_TIMEOUT changes it).
            logger: Optional logger for debug messages.
            what (str | None): What waits, named in the notice of a waiter.
            note (str | None): A note left in the lock file for the waiters.

        Returns:
            PathLock: Acquired lock object that must be released later (`_release_lock`).

        Raises:
            TimeoutError: If lock cannot be acquired within timeout period (the message names the holder
                          when it left a note), or for any other failure of the lock.
    """
    lockfile = _get_lockfile_path(filepath)
    if timeout is None:
        timeout = lock_timeout(logger=logger)
    if logger is not None:
        logger.debug(f"utils.files._acquire_lock - attempting to create {lockfile} ...")

    file_lock = PathLock(lockfile, logger=logger)
    try:
        _acquire_with_notice(file_lock, timeout, f"'{filepath}'", what if what is not None else f"the operation on '{filepath}'",
                             LOCK_TIMEOUT_ENV, note=note, logger=logger)
    except TimeoutError:
        if logger is not None:
            logger.debug(f"utils.files._acquire_lock - failed to lock {lockfile} in time ...")
        raise
    except Exception as e:
        if logger is not None:
            logger.debug(f"utils.files._acquire_lock - failed to create {lockfile} ...")
        raise TimeoutError(f"Could not acquire lock on '{filepath}': {str(e)}")

    if logger is not None:
        logger.debug(f"utils.files._acquire_lock - lock {lockfile} acquired!")
    return file_lock

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
    timeout: float = None,  # With lock=True, seconds to wait for the lock (None: the engine's lock timeout, 30 s, CMETA_LOCK_TIMEOUT changes it); without a lock, how long a read that fails is retried (None: READ_RETRY_SECONDS, 3 s; 0: one try).
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
            timeout: With a lock, seconds to wait for it (None: the engine's lock timeout, see lock_timeout);
                     without a lock, how long a read that fails is retried (None: READ_RETRY_SECONDS; 0: one try).
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
            file_lock = _acquire_lock(filepath, timeout, logger, what=f"the read of '{filepath}'")
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
        # Without a lock a read that fails (a write in progress) is retried for a while
        retry = READ_RETRY_SECONDS if timeout is None else timeout

        if retry == 0:
            try:
                data = _read_file_data(filepath, encoding=encoding)
            except Exception as e:
                return _error(str(e), 1, None, fail_on_error)

        else:
            # Retry reading with timeout when no lock
            start_time = time.time()
            last_error = None

            while time.time() - start_time < retry:
                try:
                    data = _read_file_data(filepath, encoding=encoding)
                    break  # Success, exit retry loop

                except Exception as e:
                    last_error = e
                    if time.time() - start_time < retry:
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
                pickle.dump(data, f, protocol=PICKLE_PROTOCOL)
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
    temp_path: str,  # The file just written (or the folder to rename).
    filepath: str,  # The file (or folder) it replaces.
    logger = None,  # Optional logger for debug messages.
    timeout: float = None,  # Seconds the replace is retried while the target is busy (None: the engine's lock timeout).
):
    """Replace a file atomically (`os.replace`; a folder is renamed the same way). The replace fails while
    another process holds the target open (on Windows: a reader of an index file, a scanner, an antivirus)
    or busy: it is retried with a delay that doubles from LOCK_POLL_START to RETRY_DELAY until `timeout`
    seconds (the lock timeout, CMETA_LOCK_TIMEOUT) have passed. A target that cannot be written at all (a
    read-only file, a folder without write permission) fails at once."""
    if timeout is None:
        timeout = lock_timeout(logger=logger)
    deadline = time.monotonic() + max(float(timeout), 0.0)
    delay = LOCK_POLL_START
    attempt = 0

    while True:
        try:
            os.replace(temp_path, filepath)
            return
        except OSError as e:
            if e.errno not in _REPLACE_BUSY_ERRNOS:
                raise
            attempt += 1
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not _replace_may_succeed_later(filepath):
                raise
            if logger is not None:
                logger.debug(f"utils.files._replace_file - retrying replace for '{temp_path}' -> '{filepath}' (attempt {attempt}) due to error: {str(e)}")
            time.sleep(min(delay, remaining))
            delay = min(delay * 2, RETRY_DELAY)

def _replace_may_succeed_later(filepath):
    """False when a replace of `filepath` cannot succeed by waiting: the target is a read-only file, or its
    folder cannot be written (on Windows os.access tells the read-only attribute of a file only)."""
    try:
        if os.path.isfile(filepath) and not os.access(filepath, os.W_OK):
            return False
        return os.access(os.path.dirname(filepath) or '.', os.W_OK)
    except OSError:
        return True

##########################################################################################
def _install_file(
    temp_path: str,  # The file just written next to its target.
    filepath: str,  # The target.
    logger = None,  # Optional logger for debug messages.
):
    """Put a file written next to its target in place with one atomic replace, so that a reader never sees
    a half-written file: the mode of an existing target is kept (best effort); a target that is a symbolic
    link is written through in place, so that the link stays (a replace would turn it into a plain file); a
    target that cannot be written (read-only) is refused, as a write in place would be."""
    if os.path.islink(filepath):
        with open(temp_path, 'rb') as src, open(filepath, 'wb') as dst:
            shutil.copyfileobj(src, dst)
        _remove_quietly(temp_path)
        return

    if os.path.isfile(filepath):
        if not os.access(filepath, os.W_OK):
            raise PermissionError(errno.EACCES, 'Permission denied', filepath)
        try:
            shutil.copymode(filepath, temp_path)
        except OSError:
            pass

    _replace_file(temp_path, filepath, logger)

def _remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass

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
                _install_file(temp_path, filepath, logger)
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
    timeout: float = None,  # Seconds to wait for the lock (None: the engine's lock timeout, 30 s, CMETA_LOCK_TIMEOUT changes it).
    file_lock = None,  # Existing lock to use. If None, acquires new lock.
    atomic: bool = None,  # If True, the file is written next to its target and put in place with one atomic replace, so that a reader never sees a half-written file and a crash leaves the previous one. None (the default): atomic for JSON, YAML and pickle, in place for text.
    encoding: str = None,  # Character encoding for text files. If None, auto-detected.
    fail_on_error: bool = False,  # If True, raises exception on error instead of returning error dict.
    logger = None,  # Optional logger for debug messages.
    sort_keys: bool = True,  # If True, sorts dictionary keys in JSON/YAML output.
    preserve: bool = False,  # If True, an existing YAML file is edited in place: only the keys that changed are rewritten (see _write_yaml_keeping_text); a YAML file that does not exist yet is written in the keep style.
    keep: bool = False,  # If True, a YAML file is written in the keep style of a new _cmeta.yaml (write_file keep=True). Other formats are not affected.
    safe_dump: bool = False,  # If True, values JSON cannot serialize are written as "#NON-SERIALIZABLE#" (write_file safe_dump=True).
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
            timeout (float | None): Seconds to wait for the lock (None: the engine's lock timeout, see lock_timeout).
            file_lock: Existing lock to use. If None, acquires new lock.
            atomic (bool | None): True: written next to the target and put in place with one atomic replace
                                  (a reader never sees a half-written file; the mode of the target is kept;
                                  a symbolic link is written through). None: atomic for JSON, YAML and
                                  pickle, in place for text. False: in place.
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
            file_lock = _acquire_lock(filepath, timeout, logger, what=f"the write of '{filepath}'")
        except Exception as e:
            return _error(None, 1, e, fail_on_error)

    file_format = _detect_file_format(filepath)

    # A structured file is written atomically unless told otherwise: a reader never sees a half-written
    # file and a crash leaves the previous one (text is written in place, as write_file does)
    if atomic is None:
        atomic = file_format in ('json', 'yaml', 'pickle')

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

            try:
                r = write_file(temp_path, data, encoding=encoding, fail_on_error=fail_on_error, logger=logger, sort_keys=sort_keys, file_format=file_format, keep=keep_style, safe_dump=safe_dump)
            except Exception:
                if atomic:
                    _remove_quietly(temp_path)
                raise
            if r['return']>0:
                if atomic:
                    _remove_quietly(temp_path)
                return r

            if atomic:
                try:
                    _check_lock(filepath, file_lock, logger)
                    _install_file(temp_path, filepath, logger)
                except Exception as e:
                    _remove_quietly(temp_path)
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
    timeout: float = None,  # Seconds to wait for the lock (None: the engine's lock timeout, 30 s, CMETA_LOCK_TIMEOUT changes it).
    fail_on_error: bool = False,  # Whether to raise exceptions or return error dict.
    logger = None,  # Logger instance for debug messages.
    file_lock = None,  # The lock of the folder (its sidecar `<dirpath>.lock`) when the caller holds it already: it is used and NOT released here.
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
            file_lock: The folder's lock when the caller holds it already (a delete that first removes
                       the index record under the same lock); the caller releases it.

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

    lock_acquired = False

    # Try to acquire lock (unless the caller holds it)
    if file_lock is None:
        try:
            file_lock = _acquire_lock(dirpath, timeout, logger, what=f"the removal of '{dirpath}'")
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
    timeout: float = None,  # Seconds to wait for the lock (None: the engine's lock timeout, 30 s, CMETA_LOCK_TIMEOUT changes it).
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
        file_lock = _acquire_lock(path, timeout, logger, what=f"the lock of '{path}'")
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
_file_cache_guard = threading.Lock()   # the cache dicts of safe_read_file_via_cache, for the threads of one process

def safe_read_file_via_cache(
    filepath: str,  # Path to the file to read.
    cache: dict,  # Dictionary to store cached data (modified in-place).
    timeout: int = 10,  # How long a read that fails (a write in progress) is retried, in seconds.
    fail_on_error: bool = False,  # Whether to raise exceptions or return error dict.
    logger = None,  # Optional logger for debug messages
):
    """
        Reads a file with caching keyed by the file's modification time in nanoseconds, size and inode
        (an atomic replace changes the inode): the file is read again when any of them changed, which
        catches two writes within one tick of a coarse file system too. A file read before that is
        missing for a moment (being replaced on a mount whose rename is not atomic, or inside the swap
        of a full reindex) is retried a few times before "not found". The cache dict is read and
        updated under one lock for the threads of one process. The data handed out is the cached object
        itself - do not change it (`Repos.find` copies what a caller may edit).

        WARNING: This function uses blocking I/O operations.

        Args:
            filepath (str): Path to the file to read.
            cache (dict): Dictionary to store cached data (modified in-place).
            timeout (int): How long a read that fails is retried, in seconds.
            fail_on_error (bool): Whether to raise exceptions or return error dict.
            logger: Optional logger for debug messages

        Returns:
            Dict with 'return' (0=success, non-zero=error) and 'data' or 'error'.

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    path = Path(filepath)

    # Retry the stat RETRY_TIMESTAMP_FILE+1 times with small delay. A file this process has read before
    # that is missing is given RETRY_NOT_FOUND_INDEX_FILE short retries: it is being replaced (on a mount
    # whose rename is not atomic, 9p) or its folder is inside the swap of a full reindex; a file never
    # seen is not retried (the index file of a category without artifacts)
    not_found = 0
    for attempt in range(RETRY_TIMESTAMP_FILE + 1):
        try:
            st = path.stat()
            break  # Success, exit retry loop
        except FileNotFoundError:
            with _file_cache_guard:
                seen = filepath in cache
            if seen and not_found < RETRY_NOT_FOUND_INDEX_FILE:
                not_found += 1
                time.sleep(RETRY_NOT_FOUND_DELAY)
                continue
            return _error(f"'{filepath}' does not exist", ERROR_CODE_FILE_NOT_FOUND, None, fail_on_error)
        except Exception as e:
            if attempt < RETRY_TIMESTAMP_FILE:  # Don't delay after last attempt
                if logger is not None:
                    logger.debug(f"utils.files.safe_read_file_via_cache - retrying stat for '{filepath}' (attempt {attempt + 1}) due to error: {str(e)}")
                time.sleep(RETRY_DELAY)
            else:
                return _error(f"Could not get file timestamp: {str(e)}", 1, e, fail_on_error)

    if stat.S_ISDIR(st.st_mode):
        return _error(f"'{filepath}' is a directory; safe_read_file_via_cache only supports files.", 1, None, fail_on_error)

    stamp = (st.st_mtime_ns, st.st_size, st.st_ino)

    # Check if file is in cache and its stamp matches
    with _file_cache_guard:
        cached_entry = cache.get(filepath)

    if cached_entry is not None:
        if cached_entry.get('stamp') == stamp:
            return {'return': 0, 'data': cached_entry['data']}

        if logger is not None:
            logger.debug(f"utils.files.safe_read_file_via_cache - recaching changed index file {filepath} ...")

    # Cache miss or file changed - read the file
    if logger is not None:
        logger.debug(f"utils.files.safe_read_file_via_cache - reading index file {filepath} ...")

    result = safe_read_file(filepath, timeout=timeout, fail_on_error=fail_on_error, logger=logger)

    if result['return'] == 0:
        # Update cache with new data and stamp (a change of the file between the stat and the read is
        # caught at the next call: the stamp stored is the older one)
        with _file_cache_guard:
            cache[filepath] = {
                'data': result['data'],
                'timestamp': st.st_mtime,
                'stamp': stamp
            }

    return result

##########################################################################################
def safe_read_yaml_or_json(
    filepath: str,  # Path to file (extension will be ignored/removed).
    lock: bool = False,  # Whether to use file locking.
    keep_locked: bool = False,  # Whether to keep lock after successful read.
    timeout: float = None,  # Lock timeout (None: the engine's lock timeout), or the read retry without a lock (see safe_read_file).
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
            # Nobody to answer (a script, a detached job): an error that names -f, never a traceback
            r = _ask('  Proceed (y/N)? ', how='-f (--force) to delete without asking')
            if r['return'] > 0: return r
            x = r['answer'].strip().lower()

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
