"""Halyard MCP: expose component invocables as Model Context Protocol tools."""

from .server import ToolBinding, build_server, collect_tools, run_stdio
from .tool import ToolMeta, is_tool, tool

__all__ = [
    "ToolBinding",
    "ToolMeta",
    "build_server",
    "collect_tools",
    "is_tool",
    "run_stdio",
    "tool",
]
