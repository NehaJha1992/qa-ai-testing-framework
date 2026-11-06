import pytest

from framework import factories
from framework.assertions import assert_error, assert_matches_schema, assert_status
from framework.schemas import UserSchema

pytestmark = pytest.mark.api


@pytest.mark.smoke
def test_create_and_get_user_round_trip(admin_client):
    payload = factories.user()

    created = admin_client.create_user(payload)
    assert_status(created, 201)
    user = assert_matches_schema(created.json(), UserSchema)
    assert user.name == payload["name"]
    assert user.email == payload["email"]
    assert user.accountType == payload["accountType"]

    fetched = admin_client.get_user(user.id)
    assert_status(fetched, 200)
    assert fetched.json() == created.json()


@pytest.mark.negative
@pytest.mark.parametrize("missing_field", ["name", "email", "accountType"])
def test_create_user_missing_required_field(admin_client, missing_field):
    response = admin_client.create_user(factories.user(remove=[missing_field]))

    assert_error(response, code="required_field", field=missing_field, status=400)


@pytest.mark.negative
@pytest.mark.parametrize("bad_name", ["*", "@john", "-Bob"])
def test_create_user_name_cannot_start_with_special_character(admin_client, bad_name):
    response = admin_client.create_user(factories.user(name=bad_name))

    assert_error(response, code="invalid_name", field="name", status=400)


def test_create_user_name_at_max_length_is_accepted(admin_client):
    response = admin_client.create_user(factories.user(name="A" * 50))

    assert_status(response, 201)


@pytest.mark.negative
def test_create_user_name_over_max_length_is_rejected(admin_client):
    response = admin_client.create_user(factories.user(name="A" * 51))

    assert_error(response, code="invalid_name", field="name", status=400)


def test_create_user_email_at_max_length_is_accepted(admin_client):
    domain = "@example.com"
    email = "a" * (254 - len(domain)) + domain  # exactly 254 characters

    response = admin_client.create_user(factories.user(email=email))

    assert_status(response, 201)


@pytest.mark.negative
def test_create_user_email_over_max_length_is_rejected(admin_client):
    domain = "@example.com"
    email = "a" * (255 - len(domain)) + domain  # 255 characters, one too many

    response = admin_client.create_user(factories.user(email=email))

    assert_error(response, code="invalid_email", field="email", status=400)


@pytest.mark.negative
@pytest.mark.parametrize("bad_email", ["not-an-email", "missing-domain@"])
def test_create_user_invalid_email(admin_client, bad_email):
    response = admin_client.create_user(factories.user(email=bad_email))

    assert_error(response, code="invalid_email", field="email", status=400)


@pytest.mark.negative
def test_create_user_invalid_account_type(admin_client):
    response = admin_client.create_user(factories.user(accountType="gold"))

    assert_error(response, code="invalid_account_type", field="accountType", status=400)


@pytest.mark.negative
def test_create_user_duplicate_email(admin_client):
    payload = factories.user()
    assert_status(admin_client.create_user(payload), 201)

    response = admin_client.create_user(factories.user(email=payload["email"]))

    assert_error(response, code="duplicate_email", field="email", status=409)


@pytest.mark.negative
def test_get_unknown_user_returns_404(admin_client):
    response = admin_client.get_user("00000000-0000-0000-0000-000000000000")

    assert_error(response, code="not_found", status=404)
