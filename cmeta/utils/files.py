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

from .common import _error

try:
    import yaml
except ImportError:
    yaml = None  # YAML is optional

try:
    from filelock import FileLock
except ImportError:
    raise ImportError("filelock library is required. Install with: pip install filelock")

LOCK_SUFFIX = ".lock"
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
def _acquire_lock(
    filepath: str,  # Path to the file to lock.
    timeout: int = 3,  # Maximum seconds to wait for lock acquisition. Default is 3.
    logger = None,  # Optional logger for debug messages.
):
    """
        Acquire a file lock for cross-platform thread/process-safe file operations.

        Uses FileLock library to create and acquire a lock file. Blocks until lock
        is acquired or timeout expires.

        Args:
            filepath (str): Path to the file to lock.
            timeout (int): Maximum seconds to wait for lock acquisition. Default is 3.
            logger: Optional logger for debug messages.

        Returns:
            FileLock: Acquired lock object that must be released later.

        Raises:
            TimeoutError: If lock cannot be acquired within timeout period.
    """
    lockfile = _get_lockfile_path(filepath)
    if logger is not None:
        logger.debug(f"utils.files._acquire_lock - attempting to create {lockfile} ...")
    
    file_lock = FileLock(lockfile, timeout=timeout)
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
    file_lock,  # FileLock object to check.
    logger = None,  # Optional logger for debug messages.
):
    """
        Verify that a file lock is still valid.

        Args:
            filepath (str): Path to the locked file.
            file_lock: FileLock object to check.
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
    file_lock,  # FileLock object to release.
    logger = None,  # Optional logger for debug messages.
):
    """
        Release a previously acquired file lock.

        Args:
            filepath (str): Path to the locked file.
            file_lock: FileLock object to release.
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
                
        # Explicitly clean up lock file - filelock doesn't always do this on Linux
        _cleanup_lock_file(lockfile, logger)
        
    except Exception as e:
        if logger is not None:
            logger.debug(f"utils.files._release_lock - error releasing lock {lockfile} ({str(e)})")
        
        # Still try to cleanup lock file even if release failed
        _cleanup_lock_file(lockfile, logger)
        raise e

##########################################################################################
def _cleanup_lock_file(
    lockfile_path: str,  # Path to the lock file to remove.
    logger = None,  # Optional logger for debug messages.
):
    """
        Manually remove lock file if it exists.

        Ensures cleanup on systems where filelock doesn't auto-cleanup.
        Errors are logged but not raised since this is a cleanup operation.

        Args:
            lockfile_path (str): Path to the lock file to remove.
            logger: Optional logger for debug messages.

        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """
    try:
        if os.path.exists(lockfile_path):
            os.remove(lockfile_path)
            if logger is not None:
                logger.debug(f"utils.files._cleanup_lock_file - manually removed {lockfile_path}")
    except Exception as e:
        if logger is not None:
            logger.debug(f"utils.files._cleanup_lock_file - failed to remove {lockfile_path}: {str(e)}")
        # Don't raise - this is a cleanup operation

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

        Returns:
            dict: Dictionary with 'return': 0 and 'data', or 'return' > 0 and 'error'.

        Raises:
            Exception: Propagated runtime errors, if any.
    """

    r = safe_read_file(filepath, encoding=encoding, timeout=0, retry_if_not_found=1, fail_on_error=fail_on_error, logger=logger)

    if remove_after_read and os.path.isfile(remove_after_read):
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
                json.dump(data, f, indent=2, sort_keys=sort_keys)
                f.write("\n")
            elif file_format == "yaml":
                yaml.safe_dump(data, f, sort_keys=sort_keys)
            elif file_format == "pickle":
                pickle.dump(data, f)
            else:
                f.write(str(data))

    except Exception as e:
        return _error(None, 1, e, fail_on_error)

    return {'return':0, 'encoding':encoding, 'mode':mode}



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
):
    """
        Safely write data to file with locking and optional atomic write.

        Provides thread/process-safe file writing with file locking support.
        Supports atomic writes via temp file + rename for data integrity.

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

        Returns:
            dict: Dictionary with 'return': 0 on success, or 'return' > 0 and 'error' on failure.

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

    temp_path = f"{filepath}.tmp" if atomic else filepath

    r = write_file(temp_path, data, encoding=encoding, fail_on_error=fail_on_error, logger=logger, sort_keys=sort_keys, file_format=file_format)
    if r['return']>0: return r

    release_error = None

    try:
        if atomic:
            try:
                _check_lock(filepath, file_lock, logger)
            except Exception as e:
                return _error(None, 1, e, fail_on_error)

            # Retry replacing the file with RETRY_REPLACE_FILE attempts
            for attempt in range(RETRY_REPLACE_FILE + 1):
                try:
                    os.replace(temp_path, filepath)
                    break  # Success, exit retry loop
                except Exception as e:
                    if attempt < RETRY_REPLACE_FILE:
                        if logger is not None:
                            logger.debug(f"utils.files.safe_read_file - retrying replace for '{temp_path}' -> '{filepath}' (attempt {attempt + 1}) due to error: {str(e)}")
                        time.sleep(RETRY_DELAY)
                    else:
                        return _error(None, 1, e, fail_on_error)

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

    return {'return': 0}

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
    skip_directories: list = None,  # List of directory names to skip (e.g., ['.git', '__pycache__']).
    fail_on_error: bool = True,  # Whether to raise exceptions or return error dict.
    logger = None,  # Logger instance for debug messages
    skip_files: list = None,  # List of file names or glob patterns to exclude from the archive.
):
    """
        Creates a zip archive from a directory.

        Args:
            source_dir (str): Path to the directory to zip.
            output_path (str): Path where the zip file will be created.
            skip_directories (list | None): List of directory names to skip (e.g., ['.git', '__pycache__']).
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
                    if skip_directories and parent in skip_directories:
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
def _handle_remove_readonly(
    func,  # Value for func.
    path,  # Filesystem path.
    exc_info,  # Value for exc info.
):
    """
        Error handler for shutil.rmtree that removes read-only attributes.

        Args:
            func: Value for func.
            path: Filesystem path.
            exc_info: Value for exc info.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        raise

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
                    os.chmod(item, stat.S_IWRITE)
                    item.unlink()
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
            clean: Value for clean.
        Returns:
            dict: Operation result.
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

