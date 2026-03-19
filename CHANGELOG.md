cMeta (0.25.0):
  * changed API version handling logic (now using the last one by default)
  * many minor updates and improvements for cMeta tasks

cMeta (0.24.0):
  * simplified error and logging handling logic
  * updated state -> ctx (context)
   
cMeta (0.23.0):
  * many improvements and minor bug fixes

cMeta (0.22.0):
  * added state extensions for reproducibility
  * fixed and extended 'load_files' in artifact read/find logic
  * improved sub-package installation
  * added uses_categories to cmeta
  * added advanced match_version to packages for tools

cMeta (0.21.0):
  * many various bug fixes and important extensions

cMeta (0.20.0):
  * many regular improvements and some serious bug fixes

cMeta (0.19.0):
  * many improvements and bug fixes

cMeta (0.18.0):
  * various improvements including cx repo plug/unplug USB repos

cMeta (0.17.0):
  * many updates
  * added cx {category} read --load_files,=

cMeta (0.16.0):
  * Extended cx note create; cx work create; cx experiment create
  * Extended cx config

cMeta (0.15.0):
  * Added cms - common meta server
  * Added app run

cMeta (0.14.0):
  * Fixed bug in mixed case artifact handling

cMeta (0.13.0):
  * Added state['deps'] for python packages

cMeta (0.12.0):
  * Added new categories to support CK

cMeta (0.11.0):
  * Updated documentation for all functions

cMeta (0.10.0):
  * Fixed more bugs; added on-the-fly package management; added common functions

cMeta (0.9.0):
  * Fixed bugs in sharding schema

cMeta (0.8.0):
  * Simplified sharding schema
  * Changed default API handling

cMeta (0.7.0):
  * Added no_index artifacts

cMeta (0.6.0):
  * Added sharding for artifacts

cMeta (0.4.0):
  * Fixed another major bug in the category module loader.

cMeta (0.3.0):
  * Fixed a major bug in the category module loader.

cMeta (0.2.0): 

  * Added async support for FastAPI.

cMeta (0.1.0):

  * Removed explicit UID ordering from the index. 
    Dictionary key insertion order (Python 3.10+) 
    now defines the ordering.
