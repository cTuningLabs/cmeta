cmeta.utils.names module
========================

Reusable functions to handle cMeta objects

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.

-------------------------------------------------------
Conventions:

  cMeta UID = 16 hex characters
  cMeta alias = any adopted filename in Linux, Windows and MacOS (since we keep them as directories i repositories)

  cMeta name = alias | UID | alias,UID

  repo_name = repo_alias | repo_uid | repo_alias,repo_uid
  repo == repo_name

  artifact_name = artifact_alias | artifact_uid | artifact_alias,artifact_uid
  artifact_name_dict = {'artifact_alias', 'artifact_uid'}

  artifact_obj = (artifact_repo_name:)artifact_name
  artifact_obj_dict = {artifact_repo_alias, artifact_repo_uid, artifact_alias, artifact_uid}
  artifact == artifact_obj

  category_name = category_alias | category_uid | category_alias,category_uid
  category_name_dict = {category_alias, category_uid}

  category_obj = (category_repo_name:)category_name
  category_obj_dict = {category_repo_alias, category_repo_uid, category_alias, category_uid}
  category == category_obj

  cmeta_ref = category_obj::artifact_obj
  cmeta_ref_dict = {category_repo_alias, category_repo_uid, category_alias, category_uid,
                    artifact_repo_alias, artifact_repo_uid, artifact_alias, artifact_uid}
  cRef == cmeta_ref
  
Find in Fast index:

  records = list of artifacts following search criteria
  record = {'path',
            'cmeta_ref_parts',
            'cmeta'}

Functions
---------

.. autofunction:: cmeta.utils.names.generate_cmeta_uid

.. autofunction:: cmeta.utils.names.get_sort_key_cmeta_obj_alias_or_uid

.. autofunction:: cmeta.utils.names.is_valid_category_alias

.. autofunction:: cmeta.utils.names.is_valid_cmeta_alias

.. autofunction:: cmeta.utils.names.is_valid_cmeta_uid

.. autofunction:: cmeta.utils.names.parse_cmeta_name

.. autofunction:: cmeta.utils.names.parse_cmeta_obj

.. autofunction:: cmeta.utils.names.parse_cmeta_ref

.. autofunction:: cmeta.utils.names.parse_cmeta_ref_with_path

.. autofunction:: cmeta.utils.names.restore_cmeta_name

.. autofunction:: cmeta.utils.names.restore_cmeta_obj

.. autofunction:: cmeta.utils.names.restore_cmeta_ref
