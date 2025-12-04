"""
Reusable functions for safe loading, storing and caching of files 

cMeta author and developer: (C) 2025 Grigori Fursin

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
def _get_lockfile_path(filepath):
    """
    Returns the path to the lock file, external to the target path.
    """
    return f"{filepath}{LOCK_SUFFIX}"

##########################################################################################
def is_path_within(base, target):
    """
    Checks if base path is within target path
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
def _acquire_lock(filepath, timeout=3, logger=None):
    """
    Tries to acquire a lock file for the target path, with timeout.
    Uses FileLock for cross-platform compatibility.
    Returns FileLock object to be used for release.
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
def _check_lock(filepath, file_lock, logger = None):
    """
    Checks if the lock is still valid.
    """
    if not file_lock.is_locked:
        if logger is not None:
            logger.debug(f"utils.files._check_lock - detected expired lock for {filepath} ...")
        raise TimeoutError(f"Detected expired lock for '{filepath}'")
    if logger is not None:
        logger.debug(f"utils.files._check_lock - lock file checked for {filepath} ...")

##########################################################################################
def _release_lock(filepath, file_lock, logger = None):
    """
    Releases the FileLock.
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
def _cleanup_lock_file(lockfile_path, logger=None):
    """
    Manually removes the lock file if it exists.
    This ensures cleanup on systems where filelock doesn't auto-cleanup.
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
def _detect_file_format(filepath):
    """
    Returns file type based on extension.
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
def _read_file_data(filepath, encoding=None):
    """
    Helper function to read file data based on format.
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
def read_file(filepath, fail_on_error=False, logger=None, encoding=None):
    return safe_read_file(filepath, encoding=encoding, timeout=0, retry_if_not_found=1, fail_on_error=fail_on_error, logger=logger)


##########################################################################################
def safe_read_file(filepath, encoding=None, lock=False, keep_locked=False, timeout=3, retry_if_not_found=0, fail_on_error=False, logger=None):
    """
    Safely reads a file with optional locking. Cleans up lock on error.
    If keep_locked=True and lock=True, the lock is maintained after successful read.
    
    WARNING: This function is NOT thread-safe for async usage. It uses blocking I/O
    operations that will block the event loop. For async usage, consider using
    aiofiles and asyncio-compatible locking mechanisms.
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
            try:
                last_modified = path.stat().st_mtime
            except Exception:
                last_modified = None
            break
        if attempt < retry_not_found_file:  # Don't delay after last attempt
            if logger is not None:
                logger.debug(f"utils.files.safe_read_file - retrying existence check for '{filepath}' (attempt {attempt + 1}) ...")
            time.sleep(RETRY_DELAY)

    if not path.exists() or last_modified is None:
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
def write_file(filepath, data, encoding=None, fail_on_error=False, logger=None, sort_keys=True, file_format=None, newline='\n'):

    if file_format is None:
        file_format = _detect_file_format(filepath)

    encoding = _get_encoding(encoding, file_format)

    mode = "wb" if encoding is None else "w"
    set_newline = None if encoding is None else newline

    try:
        with open(filepath, mode, encoding=encoding, newline=set_newline) as f:
            if file_format == "json":
                json.dump(data, f, indent=2, sort_keys=sort_keys)
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
def safe_write_file(filepath, data, timeout=3, file_lock=None, atomic=False, encoding=None, fail_on_error=False, logger=None, sort_keys=True):
    """
    Safely writes data to a file. Supports atomic write via temp file + rename.
    
    WARNING: This function is NOT thread-safe for async usage. It uses blocking I/O
    operations that will block the event loop. For async usage, consider using
    aiofiles and asyncio-compatible locking mechanisms.
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
def safe_delete_directory(dirpath, timeout=3, fail_on_error=False, logger=None):
    """
    Safely and recursively deletes a directory with all its contents.
    Works cross-platform (Windows, Linux, MacOS) and handles special cases like
    .git directories with read-only attributes.
    
    If lock acquisition fails but directory doesn't exist, returns success.
    
    Args:
        dirpath: Full path to directory to delete
        timeout: Lock timeout in seconds
        fail_on_error: Whether to raise exceptions or return error dict
        logger: Logger instance for debug messages
    
    Returns:
        Dict with 'return' (0=success, non-zero=error) and optional 'error'
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
        
        def handle_remove_readonly(func, path, exc):
            """
            Error handler for shutil.rmtree to handle read-only files.
            This is especially important for .git directories on Windows.
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
def safe_delete_directory_if_empty(dirpath):
    """Check quickly if directory is empty and remove it safely."""
    try:
        if os.path.isdir(dirpath):
            with os.scandir(dirpath) as it:
                if not any(it):  # stops immediately if one entry exists
                    os.rmdir(dirpath)
    except OSError:
        pass  # ignore permission/race/other errors safely

    return {'return':0}

##########################################################################################
def lock_path(path, timeout=3, fail_on_error=False, logger=None):
    """Acquires a lock for any file or directory path."""
    if logger is not None:
        logger.debug(f"utils.files.lock_path - preparing to lock path {path} ...")

    try:
        file_lock = _acquire_lock(path, timeout, logger)
        return {'return': 0, 'file_lock': file_lock}
    except Exception as e:
        return _error(None, 1, e, fail_on_error)

##########################################################################################
def unlock_path(path, file_lock, fail_on_error=False, logger=None):
    """Releases the lock for any file or directory path."""

    if logger is not None:
        logger.debug(f"utils.files.unlock_path - preparing to unlock path {path} ...")

    try:
        _release_lock(path, file_lock, logger)
    except Exception as e:
        return _error(None, 1, e, fail_on_error)

    return {'return':0}

##########################################################################################
def safe_read_file_via_cache(filepath, cache, timeout=10, fail_on_error=False, logger=None):
    """
    Reads a file with caching based on file modification timestamp.
    Automatically reloads if file has been modified since last cache.
    
    WARNING: This function is NOT thread-safe for async usage. The cache dictionary
    can be corrupted by concurrent access, and it uses blocking I/O operations.
    
    Args:
        filepath: Path to the file to read
        cache: Dictionary to store cached data (modified in-place)
        timeout: Lock timeout for file operations
        fail_on_error: Whether to raise exceptions or return error dict
    
    Returns:
        Dict with 'return' (0=success, non-zero=error) and 'data' or 'error'
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
def safe_read_yaml_or_json(filepath, lock=False, keep_locked=False, timeout=3, fail_on_error=False, retry_if_not_found=0, logger=None):
    """
    Safely reads a YAML or JSON file by trying YAML first, then JSON.
    Removes any existing extension from filepath and tries .yaml, then .json.
    
    Args:
        filepath: Path to file (extension will be ignored/removed)
        lock: Whether to use file locking
        keep_locked: Whether to keep lock after successful read
        timeout: Lock timeout
        fail_on_error: Whether to raise exceptions or return error dict
        retry_if_not_found: Number of retries if file not found
        logger: Logger instance for debug messages
    
    Returns:
        Dict with 'return' (0=success, non-zero=error) and 'data' or 'error'
        If keep_locked=True and lock=True, also returns 'file_lock'
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
def _get_encoding(encoding, file_format):
    """
    Helper function to determine the appropriate encoding for file operations.
    """
    if encoding == '': 
        encoding = None
    
    elif encoding is None:
        if file_format in ['json', 'yaml', 'txt', 'text', 'md', 'html', 'htm']:
            encoding = 'utf-8'
    
    return encoding

##########################################################################################
def unzip(filename, path=None, remove_directories=0, skip_directories=None, overwrite=True, clean=False, fail_on_error=False):
    """
    Unzip file to the current directory or 'path'.
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
def zip_directory(source_dir, output_path, skip_directories=None, fail_on_error=True, logger=None):
    """
    Creates a zip archive from a directory.
    
    Args:
        source_dir: Path to the directory to zip
        output_path: Path where the zip file will be created
        skip_directories: List of directory names to skip (e.g., ['.git', '__pycache__'])
        fail_on_error: Whether to raise exceptions or return error dict
        logger: Logger instance for debug messages
    
    Returns:
        Dict with 'return' (0=success, non-zero=error) and optional 'error'
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
                    if parent in skip_directories:
                        skip = True
                        break
                
                if skip:
                    if logger is not None:
                        logger.debug(f"utils.files.zip_directory - skipping {file_path}")
                    continue
                
                # Add file or directory to zip
                if file_path.is_file():
                    arcname = file_path.relative_to(source_path)
                    zip_ref.write(file_path, arcname)
                    if logger is not None:
                        logger.debug(f"utils.files.zip_directory - added {arcname}")
        
        if logger is not None:
            logger.debug(f"utils.files.zip_directory - successfully created {output_path}")
       
    except Exception as e:
        return _error(f"Failed to create zip archive: {str(e)}", 1, e, fail_on_error)

    return {'return': 0, 'output_path': output_path}

##########################################################################################
def shard_name(name: str, slices=None):
    """
    Apply sharding to a single path component (file or directory name).
    Returns a list of subdirectory names + the original name.
    
    If name is shorter than required by slices, underscore-filled placeholders
    will be used (e.g., '___' for a 2-char shard). Placeholder length = shard_length + 1.
    This ensures predictable directory structure for database listing and migration.
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
def apply_sharding_to_path(path: str, name: str, slices: list):
    """
    Takes an input path like "20251109.test" and shard it into 
    directories based on slices schema.
    
    Returns the full sharded path under base_dir.
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
        artifact_path: str,
        sharding_slices: list = None
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
    """
    current_path = os.path.dirname(artifact_path)
    extra_levels = 1 if sharding_slices is None else len(sharding_slices) + 1

    for _i in range(extra_levels):
        r = safe_delete_directory_if_empty(current_path)
        if r['return'] > 0: return r

        if os.path.isdir(current_path): break

        current_path = os.path.dirname(current_path)

    return {'return': 0}
