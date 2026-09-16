"""Actions and providers: ergonomic callable units built on components.

An `Action` is a component with one operation, ``execute``, callable as the
object itself and auto-exposed as an MCP tool. A `Provider` is its internal
sibling - infrastructure wired in as a dependency, never an entry point.
"""

from .action import Action
from .params import ActionParams
from .provider import Provider

__all__ = [
    "Action",
    "ActionParams",
    "Provider",
]
