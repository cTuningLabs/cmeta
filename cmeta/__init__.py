"""
cMeta – a Common Meta Framework for unifying and interconnecting code, data, and knowledge.

cMeta author and developer: (C) 2025 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

from .core import CMeta

from .cli import process as cli
from .cli import catch
from .cli import set_fail_on_error

from .version import __version__
