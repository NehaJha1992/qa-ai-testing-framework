"""A small synchronous helper for testing MCP servers, so tests read like the rest of the suite.

The MCP SDK is asynchronous. Each call here opens a short-lived connection with asyncio.run, so the
tests themselves can stay plain, simple functions.
"""
import asyncio
import json
from dataclasses import dataclass
from typing import Any

from mcp import Client


@dataclass
class ToolResult:
    is_error: bool
    text: str          # all text the tool returned, joined together
    data: Any = None   # the text parsed as JSON, when it is JSON


class McpToolClient:
    """Talks to an MCP server. `target` can be an MCPServer object (in process) or StdioServerParameters (a real subprocess)."""

    def __init__(self, target):
        self.target = target

    def list_tools(self):
        async def run():
            async with Client(self.target) as client:
                return (await client.list_tools()).tools
        return asyncio.run(run())

    def call(self, name: str, arguments: dict | None = None) -> ToolResult:
        async def run():
            async with Client(self.target) as client:
                return await client.call_tool(name, arguments or {})
        result = asyncio.run(run())

        text = "\n".join(block.text for block in result.content if hasattr(block, "text"))
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        return ToolResult(is_error=result.is_error, text=text, data=data)
