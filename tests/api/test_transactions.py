import pytest

from framework import factories
from framework.assertions import (
    assert_error,
    assert_matches_schema,
    assert_money_equal,
    assert_status,
)
from framework.schemas import TransactionSchema

pytestmark = pytest.mark.api

UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


@pytest.mark.smoke
def test_transfer_can_be_fetched_back(admin_client, make_user):
    sender, recipient = make_user(), make_user()
    payload = factories.transaction(sender["id"], type="transfer", recipientId=recipient["id"])

    created = admin_client.create_transaction(payload)
    assert_status(created, 201)
    tx = assert_matches_schema(created.json(), TransactionSchema)
    assert tx.userId == sender["id"]
    assert tx.recipientId == recipient["id"]

    listed = admin_client.get_transactions(sender["id"])
    assert_status(listed, 200)
    assert [t["id"] for t in listed.json()] == [tx.id]


@pytest.mark.parametrize("tx_type", ["deposit", "withdrawal"])
def test_deposit_and_withdrawal_need_no_recipient(admin_client, make_user, tx_type):
    sender = make_user()

    response = admin_client.create_transaction(factories.transaction(sender["id"], type=tx_type))

    assert_status(response, 201)
    assert response.json()["type"] == tx_type
    assert response.json()["recipientId"] is None


@pytest.mark.negative
@pytest.mark.parametrize("bad_amount", [0, -5, 100.505, "abc"])
def test_invalid_amount_is_rejected(admin_client, make_user, bad_amount):
    sender = make_user()

    response = admin_client.create_transaction(factories.transaction(sender["id"], amount=bad_amount))

    assert_error(response, code="invalid_amount", field="amount", status=400)


@pytest.mark.negative
@pytest.mark.parametrize("missing_field", ["userId", "amount", "type"])
def test_missing_required_field_is_rejected(admin_client, make_user, missing_field):
    sender = make_user()

    response = admin_client.create_transaction(
        factories.transaction(sender["id"], remove=[missing_field])
    )

    assert_error(response, code="required_field", field=missing_field, status=400)


@pytest.mark.negative
def test_invalid_transaction_type_is_rejected(admin_client, make_user):
    sender = make_user()

    response = admin_client.create_transaction(factories.transaction(sender["id"], type="refund"))

    assert_error(response, code="invalid_type", field="type", status=400)


@pytest.mark.negative
def test_transfer_without_recipient_is_rejected(admin_client, make_user):
    sender = make_user()

    response = admin_client.create_transaction(factories.transaction(sender["id"], type="transfer"))

    assert_error(response, code="required_field", field="recipientId", status=400)


@pytest.mark.negative
def test_unknown_sender_returns_404(admin_client, make_user):
    recipient = make_user()
    payload = factories.transaction(UNKNOWN_ID, type="transfer", recipientId=recipient["id"])

    response = admin_client.create_transaction(payload)

    assert_error(response, code="not_found", field="userId", status=404)


@pytest.mark.negative
def test_unknown_recipient_returns_404(admin_client, make_user):
    sender = make_user()
    payload = factories.transaction(sender["id"], type="transfer", recipientId=UNKNOWN_ID)

    response = admin_client.create_transaction(payload)

    assert_error(response, code="not_found", field="recipientId", status=404)


@pytest.mark.negative
def test_transfer_to_self_is_rejected(admin_client, make_user):
    sender = make_user()
    payload = factories.transaction(sender["id"], type="transfer", recipientId=sender["id"])

    response = admin_client.create_transaction(payload)

    assert_error(response, code="self_transfer", field="recipientId", status=400)


@pytest.mark.parametrize("amount", [100.10, 0.01])
def test_amount_precision_is_preserved(admin_client, make_user, amount):
    sender = make_user()
    assert_status(admin_client.create_transaction(factories.transaction(sender["id"], amount=amount)), 201)

    listed = admin_client.get_transactions(sender["id"])

    assert_money_equal(listed.json()[0]["amount"], amount)


@pytest.mark.negative
def test_list_transactions_for_unknown_user_returns_404(admin_client):
    response = admin_client.get_transactions(UNKNOWN_ID)

    assert_error(response, code="not_found", status=404)


def test_user_without_transactions_gets_empty_list(admin_client, make_user):
    user = make_user()

    response = admin_client.get_transactions(user["id"])

    assert_status(response, 200)
    assert response.json() == []
