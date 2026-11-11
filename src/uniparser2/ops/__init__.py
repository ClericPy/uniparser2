"""Built-in operator package.

**Importing this package performs registration** (``core.registry`` is an explicit registry and
does not rely on ``__subclasses__``). ``core`` never imports this package — the dependency
direction is one-way downward (01 §1.1 invariant I2).
"""

from . import basic as _basic
from . import code as _code
from . import ctx as _ctx
from . import htmldom as _htmldom
from . import jsonquery as _jsonquery
from . import node as _node
from . import pyops as _pyops
from . import regex as _regex
from . import typeop as _typeop
from . import udf as _udf
from . import xmlxpath as _xmlxpath

__all__ = [
    "_basic",
    "_code",
    "_ctx",
    "_htmldom",
    "_jsonquery",
    "_node",
    "_pyops",
    "_regex",
    "_typeop",
    "_udf",
    "_xmlxpath",
]
