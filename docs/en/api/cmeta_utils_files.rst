cmeta.utils.files module
========================

Reusable functions for safe loading, storing and caching of files 

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.

Classes
-------

.. autoclass:: cmeta.utils.files.PathLock
   :members:
   :undoc-members:
   :show-inheritance:

Functions
---------

.. autofunction:: cmeta.utils.files.apply_sharding_to_path

.. autofunction:: cmeta.utils.files.ask_to_delete

.. autofunction:: cmeta.utils.files.cpath

.. autofunction:: cmeta.utils.files.diff_env

.. autofunction:: cmeta.utils.files.edit_yaml_text

.. autofunction:: cmeta.utils.files.files_decode

.. autofunction:: cmeta.utils.files.files_encode

.. autofunction:: cmeta.utils.files.gen_temp_filepath

.. autofunction:: cmeta.utils.files.get_creation_time

.. autofunction:: cmeta.utils.files.get_latest_modification_time

.. autofunction:: cmeta.utils.files.get_latest_tree_modification_time

.. autofunction:: cmeta.utils.files.is_dir_empty

.. autofunction:: cmeta.utils.files.is_dir_within_path

.. autofunction:: cmeta.utils.files.is_path_within

.. autofunction:: cmeta.utils.files.load_files

.. autofunction:: cmeta.utils.files.lock_path

.. autofunction:: cmeta.utils.files.md5sum

.. autofunction:: cmeta.utils.files.order_meta_keys

.. autofunction:: cmeta.utils.files.parse_env_dump

.. autofunction:: cmeta.utils.files.quote_path

.. autofunction:: cmeta.utils.files.quote_path2

.. autofunction:: cmeta.utils.files.read_file

.. autofunction:: cmeta.utils.files.remove_dirs_from_path

.. autofunction:: cmeta.utils.files.remove_files_and_dirs_in_path

.. autofunction:: cmeta.utils.files.safe_delete_directory

.. autofunction:: cmeta.utils.files.safe_delete_directory_if_empty

.. autofunction:: cmeta.utils.files.safe_delete_directory_if_empty_with_sharding

.. autofunction:: cmeta.utils.files.safe_json_dumps

.. autofunction:: cmeta.utils.files.safe_read_file

.. autofunction:: cmeta.utils.files.safe_read_file_via_cache

.. autofunction:: cmeta.utils.files.safe_read_yaml_or_json

.. autofunction:: cmeta.utils.files.safe_write_file

.. autofunction:: cmeta.utils.files.shard_name

.. autofunction:: cmeta.utils.files.unlock_path

.. autofunction:: cmeta.utils.files.unzip

.. autofunction:: cmeta.utils.files.write_file

.. autofunction:: cmeta.utils.files.yaml_dump_keep

.. autofunction:: cmeta.utils.files.zip_directory

Constants
---------

.. autodata:: cmeta.utils.files.ERROR_CODE_FILE_NOT_FOUND

.. autodata:: cmeta.utils.files.LOCK_IDENTITY_RETRIES

.. autodata:: cmeta.utils.files.LOCK_POLL_MAX

.. autodata:: cmeta.utils.files.LOCK_POLL_START

.. autodata:: cmeta.utils.files.LOCK_SOFT_CHECK_SECONDS

.. autodata:: cmeta.utils.files.LOCK_SOFT_DEAD_MIN_AGE_SECONDS

.. autodata:: cmeta.utils.files.LOCK_SOFT_EMPTY_STALE_SECONDS

.. autodata:: cmeta.utils.files.LOCK_SOFT_REMOVE_SECONDS

.. autodata:: cmeta.utils.files.LOCK_SOFT_STALE_SECONDS

.. autodata:: cmeta.utils.files.LOCK_SUFFIX

.. autodata:: cmeta.utils.files.RETRY_DELAY

.. autodata:: cmeta.utils.files.RETRY_DELETE_ATTEMPTS

.. autodata:: cmeta.utils.files.RETRY_NOT_FOUND_FILE

.. autodata:: cmeta.utils.files.RETRY_NOT_FOUND_INDEX_FILE

.. autodata:: cmeta.utils.files.RETRY_REPLACE_FILE

.. autodata:: cmeta.utils.files.RETRY_TIMESTAMP_FILE

.. autodata:: cmeta.utils.files.YAML_DUMP_KEEP

.. autodata:: cmeta.utils.files.YAML_META_KEY_ORDER
