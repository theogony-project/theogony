"""
Theogony MCP (Model Context Protocol) integration.

Lets any MCP-compatible host (Claude Desktop, Cursor, ChatGPT Desktop,
Codex, and other MCP clients) discover and use the Chronik as a tool
without writing a custom integration.

The single public entry point is :func:`theogony.mcp.server.serve_stdio`,
exposed as the ``theogony mcp`` CLI command. Requires the optional
``mcp`` extra (``pip install -e ".[mcp]"``).
"""

from __future__ import annotations

__all__: list[str] = []
