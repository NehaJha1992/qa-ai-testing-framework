import pytest
import requests

from framework import factories
from framework.api_client import ApiClient
from framework.assertions import assert_error, assert_status

pytestmark = [pytest.mark.api, pytest.mark.security]

SOME_ID = "00000000-0000-0000-0000-000000000000"


@pytest.mark.negative
@pytest.mark.parametrize("call", [
    lambda c: c.create_user(factories.user()),
    lambda c: c.get_user(SOME_ID),
    lambda c: c.create_transaction(factories.transaction(SOME_ID)),
    lambda c: c.get_transactions(SOME_ID),
], ids=["create_user", "get_user", "create_transaction", "get_transactions"])
def test_no_token_returns_401(anon_client, call):
    assert_error(call(anon_client), code="unauthorized", status=401)


@pytest.mark.negative
def test_invalid_token_returns_401(config):
    client = ApiClient(config.base_url, "not-a-real-token", config.timeout_seconds)

    assert_error(client.get_user(SOME_ID), code="unauthorized", status=401)


@pytest.mark.negative
def test_non_bearer_authorization_header_returns_401(config):
    response = requests.get(
        f"{config.base_url}/api/users/{SOME_ID}",
        headers={"Authorization": f"Basic {config.tokens['admin']}"},
        timeout=config.timeout_seconds,
    )

    assert_error(response, code="unauthorized", status=401)


@pytest.mark.negative
def test_user_cannot_read_another_users_details(user_a_client, user_b):
    assert_error(user_a_client.get_user(user_b["id"]), code="forbidden", status=403)


@pytest.mark.negative
def test_user_cannot_read_another_users_transactions(user_a_client, user_b):
    assert_error(user_a_client.get_transactions(user_b["id"]), code="forbidden", status=403)


def test_user_can_read_own_details_and_transactions(user_a_client, user_a):
    assert_status(user_a_client.get_user(user_a["id"]), 200)
    assert_status(user_a_client.get_transactions(user_a["id"]), 200)


def test_admin_can_read_any_users_details(admin_client, user_a):
    assert_status(admin_client.get_user(user_a["id"]), 200)


def test_admin_can_read_any_users_transactions(admin_client, user_a):
    assert_status(admin_client.get_transactions(user_a["id"]), 200)


@pytest.mark.negative
def test_user_cannot_create_transaction_for_another_user(user_a_client, user_b):
    payload = factories.transaction(user_b["id"], type="withdrawal")

    assert_error(user_a_client.create_transaction(payload), code="forbidden", status=403)
