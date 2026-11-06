"""Fixtures for MCP server tests. One MCP client per identity, just like the API clients."""
import pytest

from framework.mcp_client import McpToolClient
from mcp_server.server import build_server


@pytest.fixture
def make_mcp_client(config):
    """Build an MCP client whose server acts with the token of the given role (None = no token)."""
    def _make(role: str | None) -> McpToolClient:
        token = config.tokens[role] if role else None
        return McpToolClient(build_server(config.base_url, token, config.timeout_seconds))
    return _make


@pytest.fixture
def mcp_admin(make_mcp_client):
    return make_mcp_client("admin")


@pytest.fixture
def mcp_user_a(make_mcp_client):
    return make_mcp_client("user_a")


@pytest.fixture
def mcp_anon(make_mcp_client):
    return make_mcp_client(None)
