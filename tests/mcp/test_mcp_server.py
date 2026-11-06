"""Tests for the MCP server that exposes the fintech API as tools.

Each test calls a tool the way an AI assistant would, then (where useful) checks the result against the API itself.
"""
import os
import sys

import pytest
from mcp.client.stdio import StdioServerParameters

from framework import factories
from framework.assertions import (
    assert_matches_schema,
    assert_money_equal,
    assert_status,
)
from framework.config import PROJECT_ROOT
from framework.mcp_client import McpToolClient
from framework.schemas import NotificationSchema, TransactionSchema, UserSchema
from framework.waiters import wait_until
from mcp_server.server import build_server

pytestmark = pytest.mark.mcp

EXPECTED_TOOLS = {"create_user", "get_user", "create_transaction", "list_transactions", "list_notifications"}
READ_ONLY_TOOLS = {"get_user", "list_transactions", "list_notifications"}
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


# ---------- tool discovery ----------

@pytest.mark.smoke
def test_server_lists_exactly_the_expected_tools(mcp_admin):
    assert {tool.name for tool in mcp_admin.list_tools()} == EXPECTED_TOOLS


def test_every_tool_has_a_description_and_an_input_schema(mcp_admin):
    problems = []
    for tool in mcp_admin.list_tools():
        if not tool.description or len(tool.description) < 10:
            problems.append(f"{tool.name}: description is missing or too short")
        if tool.input_schema.get("type") != "object" or not tool.input_schema.get("required"):
            problems.append(f"{tool.name}: input schema has no required fields")
    assert not problems, "Tool definitions are incomplete:\n" + "\n".join(problems)


def test_read_tools_are_marked_read_only(mcp_admin):
    for tool in mcp_admin.list_tools():
        is_marked_read_only = bool(tool.annotations and tool.annotations.read_only_hint)
        assert is_marked_read_only == (tool.name in READ_ONLY_TOOLS), (
            f"{tool.name}: read_only_hint is {is_marked_read_only}, expected {tool.name in READ_ONLY_TOOLS}"
        )


@pytest.mark.security
def test_server_exposes_no_destructive_tools(mcp_admin):
    risky = [t.name for t in mcp_admin.list_tools() if any(w in t.name for w in ("delete", "reset", "drop"))]
    assert not risky, f"Unexpected destructive tools exposed: {risky}"


# ---------- happy paths ----------

@pytest.mark.smoke
def test_create_user_tool_stores_the_user(mcp_admin, admin_client):
    payload = factories.user()

    result = mcp_admin.call("create_user", {
        "name": payload["name"], "email": payload["email"], "account_type": payload["accountType"],
    })

    assert not result.is_error, result.text
    user = assert_matches_schema(result.data, UserSchema)
    fetched = admin_client.get_user(user.id)  # check through the API, not through the tool
    assert_status(fetched, 200)
    assert fetched.json() == result.data


def test_transfer_tool_stores_the_transaction(mcp_admin, admin_client, make_user):
    sender, recipient = make_user(), make_user()

    result = mcp_admin.call("create_transaction", {
        "user_id": sender["id"], "amount": 25.5, "type": "transfer", "recipient_id": recipient["id"],
    })

    assert not result.is_error, result.text
    transaction = assert_matches_schema(result.data, TransactionSchema)
    stored = admin_client.get_transactions(sender["id"]).json()
    assert [t["id"] for t in stored] == [transaction.id]
    assert_money_equal(stored[0]["amount"], "25.50")


def test_list_transactions_tool_returns_created_transactions(mcp_admin, admin_client, make_user):
    user = make_user()
    created = admin_client.create_transaction(factories.transaction(user["id"], amount=10)).json()

    result = mcp_admin.call("list_transactions", {"user_id": user["id"]})

    assert not result.is_error, result.text
    assert [t["id"] for t in result.data["transactions"]] == [created["id"]]


def test_notification_is_visible_through_the_tool(mcp_admin, admin_client, make_user):
    user = make_user()
    assert_status(admin_client.create_transaction(factories.transaction(user["id"], type="deposit")), 201)

    def fetch():  # notifications arrive asynchronously, so poll with a timeout
        result = mcp_admin.call("list_notifications", {"user_id": user["id"]})
        return result.data["notifications"] or None

    notifications = wait_until(fetch, "a notification through the MCP tool")
    assert_matches_schema(notifications[0], NotificationSchema)


# ---------- invalid arguments (rejected by the tool's input schema) ----------

@pytest.mark.negative
@pytest.mark.parametrize("tool, arguments, expected_in_message", [
    ("create_user", {"name": "A", "email": "a@example.com"}, "account_type"),                        # missing field
    ("create_user", {"name": "A", "email": "a@example.com", "account_type": "gold"}, "account_type"),  # not an allowed value
    ("create_transaction", {"user_id": "x", "amount": "abc", "type": "deposit"}, "amount"),           # wrong type
    ("get_user", {}, "user_id"),                                                                       # missing field
], ids=["missing_account_type", "invalid_account_type", "non_numeric_amount", "missing_user_id"])
def test_invalid_arguments_return_a_tool_error(mcp_admin, tool, arguments, expected_in_message):
    result = mcp_admin.call(tool, arguments)

    assert result.is_error
    assert expected_in_message in result.text


# ---------- API business rules still apply through the tools ----------

@pytest.mark.negative
@pytest.mark.parametrize("bad_amount", [-5, 100.505])
def test_invalid_amount_is_rejected_by_the_api_rules(mcp_admin, make_user, bad_amount):
    user = make_user()

    result = mcp_admin.call("create_transaction", {"user_id": user["id"], "amount": bad_amount, "type": "deposit"})

    assert result.is_error
    assert "invalid_amount" in result.text


@pytest.mark.negative
def test_transfer_to_self_is_rejected(mcp_admin, make_user):
    user = make_user()

    result = mcp_admin.call("create_transaction", {
        "user_id": user["id"], "amount": 10, "type": "transfer", "recipient_id": user["id"],
    })

    assert result.is_error
    assert "self_transfer" in result.text


@pytest.mark.negative
def test_unknown_user_returns_not_found(mcp_admin):
    result = mcp_admin.call("get_user", {"user_id": UNKNOWN_ID})

    assert result.is_error
    assert "not_found" in result.text


@pytest.mark.negative
def test_duplicate_email_is_rejected(mcp_admin, make_user):
    existing = make_user()

    result = mcp_admin.call("create_user", {
        "name": "Someone Else", "email": existing["email"], "account_type": "basic",
    })

    assert result.is_error
    assert "duplicate_email" in result.text


# ---------- authorization: the tools can never do more than the token allows ----------

@pytest.mark.security
@pytest.mark.negative
@pytest.mark.parametrize("tool", ["get_user", "list_transactions", "list_notifications"])
def test_user_cannot_read_another_users_data_through_tools(mcp_user_a, user_b, tool):
    result = mcp_user_a.call(tool, {"user_id": user_b["id"]})

    assert result.is_error
    assert "forbidden" in result.text


@pytest.mark.security
@pytest.mark.negative
def test_user_cannot_create_a_transaction_for_another_user(mcp_user_a, user_b):
    result = mcp_user_a.call("create_transaction", {"user_id": user_b["id"], "amount": 10, "type": "withdrawal"})

    assert result.is_error
    assert "forbidden" in result.text


@pytest.mark.security
def test_user_can_read_own_data_through_tools(mcp_user_a, user_a):
    assert not mcp_user_a.call("get_user", {"user_id": user_a["id"]}).is_error
    assert not mcp_user_a.call("list_transactions", {"user_id": user_a["id"]}).is_error


@pytest.mark.security
def test_admin_can_read_any_users_data_through_tools(mcp_admin, user_a):
    assert not mcp_admin.call("get_user", {"user_id": user_a["id"]}).is_error


@pytest.mark.security
@pytest.mark.negative
def test_server_without_a_token_is_unauthorized(mcp_anon):
    result = mcp_anon.call("get_user", {"user_id": UNKNOWN_ID})

    assert result.is_error
    assert "unauthorized" in result.text


# ---------- safety: errors and outputs must not leak internals ----------

@pytest.mark.security
@pytest.mark.negative
def test_backend_outage_gives_a_safe_error(config):
    unreachable = McpToolClient(build_server("http://127.0.0.1:1", "token-admin", timeout=1))

    result = unreachable.call("get_user", {"user_id": UNKNOWN_ID})

    assert result.is_error
    assert result.text.endswith("The backend service is unavailable")
    assert "127.0.0.1" not in result.text and "Traceback" not in result.text


@pytest.mark.security
def test_tokens_never_appear_in_tool_output(mcp_admin, make_user, config):
    user = make_user()
    outputs = [
        mcp_admin.call("get_user", {"user_id": user["id"]}).text,
        mcp_admin.call("list_transactions", {"user_id": user["id"]}).text,
        mcp_admin.call("get_user", {"user_id": UNKNOWN_ID}).text,   # an error response too
    ]

    for text in outputs:
        assert config.tokens["admin"] not in text


@pytest.mark.security
@pytest.mark.negative
def test_unknown_tool_name_returns_an_error(mcp_admin):
    result = mcp_admin.call("delete_everything", {})

    assert result.is_error
    assert "Unknown tool" in result.text


# ---------- real transport ----------

def test_server_works_over_stdio_as_a_real_subprocess(config, make_user):
    """The other tests connect in process. This one starts `python -m mcp_server` and talks to it over stdio."""
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server"],
        cwd=str(PROJECT_ROOT),
        env={**os.environ, "API_BASE_URL": config.base_url, "API_TOKEN": config.tokens["admin"]},
    )
    client = McpToolClient(parameters)
    user = make_user()

    assert {tool.name for tool in client.list_tools()} == EXPECTED_TOOLS
    result = client.call("get_user", {"user_id": user["id"]})
    assert not result.is_error, result.text
    assert result.data["id"] == user["id"]
