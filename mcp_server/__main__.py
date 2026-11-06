"""Run the MCP server over stdio:  python -m mcp_server

Settings come from environment variables:
    API_BASE_URL   where the fintech API runs (default http://127.0.0.1:8000)
    API_TOKEN      the bearer token the server acts as (default: none)
"""
import os

from mcp_server.server import build_server

if __name__ == "__main__":
    server = build_server(
        base_url=os.getenv("API_BASE_URL", "http://127.0.0.1:8000"),
        token=os.getenv("API_TOKEN"),
    )
    server.run("stdio")
