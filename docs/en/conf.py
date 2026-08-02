import os
import sys

# Get version from the package
from cmeta.version import __version__

# Project information
project = 'cMeta documentation'
copyright = '2025-2026, Grigori Fursin and cTuning Labs'
author = 'Grigori Fursin'

# The short X.Y version
version = __version__
# The full version, including alpha/beta/rc tags
release = __version__

# Add version substitutions
rst_prolog = f""".. |version| replace:: {version}
.. |release| replace:: {release}
"""

# Extensions
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.viewcode',
    'sphinx.ext.napoleon',
    'sphinx.ext.autosummary',
    'sphinx.ext.intersphinx',
    'myst_parser',      # lets Sphinx read the Markdown guides in docs/en/guides/
]

# MyST (Markdown) settings
# The written guides live in docs/*.md and are copied into docs/en/guides/ by
# build_docs.py (which also rewrites their repo-relative links).
source_suffix = {
    '.rst': 'restructuredtext',
    '.md': 'markdown',
}

# Generate anchors for headings up to level 4 so cross-document links of the
# form `guide.md#3-some-heading` resolve inside the built site.
myst_heading_anchors = 4

# Autodoc settings
autodoc_default_options = {
    'members': True,
    'member-order': 'bysource',
    'special-members': '__init__',
    'undoc-members': True,
    'exclude-members': '__weakref__'
}

# Autosummary settings
autosummary_generate = True

# Napoleon settings (for Google/NumPy style docstrings)
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = False
napoleon_include_private_with_doc = False

# HTML theme
html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']
templates_path = ['_templates']

# Custom CSS for dark theme and scoped styles
html_css_files = [
    'custom.css',
]

# Theme options for better embedding in FastAPI
html_theme_options = {
    'navigation_depth': 4,
    'collapse_navigation': False,
    'sticky_navigation': True,
    'style_external_links': False,
    'style_nav_header_background': '#2d2d30',
}

# Don't include unnecessary elements
html_show_sourcelink = True
html_show_sphinx = False
html_show_copyright = True

# Compact HTML output
html_use_index = True
html_split_index = False
html_copy_source = True

# Source file suffix
source_suffix = '.rst'

# Master document
master_doc = 'index'

# Language
language = 'en'

# Exclude patterns
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']
