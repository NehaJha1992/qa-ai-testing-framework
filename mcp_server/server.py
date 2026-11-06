"""MCP server wrapping the fintech API.

MCP (Model Context Protocol) lets an AI assistant discover and call "tools" through a standard interface.
This server turns each API endpoint into a tool. It acts with ONE identity: the bearer token it is built
with. So whatever that token is allowed to do through the API, the assistant can do through the tools,
and nothing more. That is how authorization is enforced end to end.
"""
from typing import Any, Literal

import requests
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

from framework.api_client import ApiClient

READ_ONLY = ToolAnnotations(read_only_hint=True)
WRITES_DATA = ToolAnnotations(read_only_hint=False, destructive_hint=False)


def build_server(base_url: str, token: str | None, timeout: float = 5) -> MCPServer:
    """Create an MCP server that talks to the API at `base_url` using `token`."""
    api = ApiClient(base_url, token, timeout)
    server = MCPServer("fintech-api", instructions="Tools for managing fintech users and transactions.")

    @server.tool(annotations=WRITES_DATA)
    def create_user(name: str, email: str, account_type: Literal["basic", "premium"]) -> dict[str, Any]:
        """Create a new user. Returns the created user, including its id."""
        payload = {"name": name, "email": email, "accountType": account_type}
        return _result(lambda: api.create_user(payload))

    @server.tool(annotations=READ_ONLY)
    def get_user(user_id: str) -> dict[str, Any]:
        """Get one user's details by user id."""
        return _result(lambda: api.get_user(user_id))

    @server.tool(annotations=WRITES_DATA)
    def create_transaction(
        user_id: str,
        amount: float,
        type: Literal["transfer", "deposit", "withdrawal"],
        recipient_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a transaction for a user. The amount must be greater than 0 with at most 2 decimal places.
        A transfer also needs recipient_id (another existing user)."""
        payload: dict[str, Any] = {"userId": user_id, "amount": amount, "type": type}
        if recipient_id is not None:
            payload["recipientId"] = recipient_id
        return _result(lambda: api.create_transaction(payload))

    @server.tool(annotations=READ_ONLY)
    def list_transactions(user_id: str) -> dict[str, Any]:
        """List the transactions a user has sent, as {"transactions": [...]}."""
        return {"transactions": _result(lambda: api.get_transactions(user_id))}

    @server.tool(annotations=READ_ONLY)
    def list_notifications(user_id: str) -> dict[str, Any]:
        """List the notifications a user has received, as {"notifications": [...]}."""
        return {"notifications": _result(lambda: api.get_notifications(user_id))}

    return server


def _result(call) -> Any:
    """Run an API call and return its JSON. API failures become safe, readable tool errors."""
    try:
        response = call()
    except requests.RequestException:
        # Never pass raw exception text to the assistant: it can contain URLs and internals.
        raise ToolError("The backend service is unavailable")

    if response.status_code >= 500:
        raise ToolError("The backend service failed")
    if response.status_code >= 400:
        raise ToolError(_describe_api_error(response))
    return response.json()


def _describe_api_error(response: requests.Response) -> str:
    """Turn the API's standard error body into 'code: message (field)'."""
    try:
        error = response.json()["error"]
    except (ValueError, KeyError, TypeError):
        return f"The API rejected the request (HTTP {response.status_code})"
    field = f" (field: {error['field']})" if error.get("field") else ""
    return f"{error['code']}: {error['message']}{field}"
