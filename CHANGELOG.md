# Changelog

All notable changes to cMeta are documented here, newest first.

## 0.29.0
- Fixed various bugs and added more basic functionality for agents, tasks and contexts
- Fixed repo indexing when getting new repos

## 0.28.0
- Fixed bug and added safe dump of agents/tasks context

## 0.27.0
- Fixed bug in handling repos with mixed upper and lower case characters

## 0.26.0
- Started new clean version based on 0.25.14
- Added `last_update_timestamp`

## 0.25.0
- Changed API version handling logic (now using the last one by default)
- Many minor updates and improvements for cMeta tasks

## 0.24.0
- Simplified error and logging handling logic
- Updated `state` -> `ctx` (context)

## 0.23.0
- Many improvements and minor bug fixes

## 0.22.0
- Added state extensions for reproducibility
- Fixed and extended `load_files` in artifact read/find logic
- Improved sub-package installation
- Added `uses_categories` to cmeta
- Added advanced `match_version` to packages for tools

## 0.21.0
- Many various bug fixes and important extensions

## 0.20.0
- Many regular improvements and some serious bug fixes

## 0.19.0
- Many improvements and bug fixes

## 0.18.0
- Various improvements including `cx repo plug`/`unplug` USB repos

## 0.17.0
- Many updates
- Added `cx {category} read --load_files,=`

## 0.16.0
- Extended `cx note create`, `cx work create`, `cx experiment create`
- Extended `cx config`

## 0.15.0
- Added cms - common meta server
- Added `app run`

## 0.14.0
- Fixed bug in mixed case artifact handling

## 0.13.0
- Added `state['deps']` for python packages

## 0.12.0
- Added new categories to support CK

## 0.11.0
- Updated documentation for all functions

## 0.10.0
- Fixed more bugs; added on-the-fly package management; added common functions

## 0.9.0
- Fixed bugs in sharding schema

## 0.8.0
- Simplified sharding schema
- Changed default API handling

## 0.7.0
- Added `no_index` artifacts

## 0.6.0
- Added sharding for artifacts

## 0.4.0
- Fixed another major bug in the category module loader

## 0.3.0
- Fixed a major bug in the category module loader

## 0.2.0
- Added async support for FastAPI

## 0.1.0
- Removed explicit UID ordering from the index. Dictionary key insertion order
  (Python 3.10+) now defines the ordering
