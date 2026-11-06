"""Notification Service (simulated). Notifications arrive asynchronously, so tests wait for them."""
import pytest

from framework import factories
from framework.assertions import assert_error, assert_matches_schema, assert_status
from framework.schemas import NotificationSchema
from framework.waiters import wait_until

pytestmark = pytest.mark.api

UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


def wait_for_notifications(client, user_id, count):
    """Wait until the user has at least `count` notifications, then return them."""
    def fetch():
        response = client.get_notifications(user_id)
        assert_status(response, 200)
        notifications = response.json()
        return notifications if len(notifications) >= count else None

    return wait_until(fetch, f"{count} notification(s) for user {user_id}")


@pytest.mark.smoke
def test_transfer_notifies_the_sender(admin_client, make_user):
    sender, recipient = make_user(), make_user()
    created = admin_client.create_transaction(
        factories.transaction(sender["id"], type="transfer", recipientId=recipient["id"], amount=25.50)
    )
    assert_status(created, 201)

    notifications = wait_for_notifications(admin_client, sender["id"], 1)

    notification = assert_matches_schema(notifications[0], NotificationSchema)
    assert notification.type == "transaction_created"
    assert notification.transactionId == created.json()["id"]
    assert "25.50" in notification.message


def test_transfer_notifies_the_recipient(admin_client, make_user):
    sender, recipient = make_user(), make_user()
    created = admin_client.create_transaction(
        factories.transaction(sender["id"], type="transfer", recipientId=recipient["id"])
    )

    notifications = wait_for_notifications(admin_client, recipient["id"], 1)

    notification = assert_matches_schema(notifications[0], NotificationSchema)
    assert notification.type == "transfer_received"
    assert notification.transactionId == created.json()["id"]


def test_deposit_notifies_only_the_user(admin_client, make_user):
    user, other = make_user(), make_user()
    assert_status(admin_client.create_transaction(factories.transaction(user["id"], type="deposit")), 201)

    wait_for_notifications(admin_client, user["id"], 1)

    assert admin_client.get_notifications(other["id"]).json() == []


@pytest.mark.negative
def test_rejected_transaction_sends_no_notification(admin_client, make_user):
    user = make_user()
    rejected = admin_client.create_transaction(factories.transaction(user["id"], amount=-5))
    assert_status(rejected, 400)
    # Notifications arrive in order, so once this later valid transaction's notification has
    # arrived, a notification for the rejected one (if there were a bug) would be there too.
    valid = admin_client.create_transaction(factories.transaction(user["id"], amount=10))

    notifications = wait_for_notifications(admin_client, user["id"], 1)

    assert [n["transactionId"] for n in notifications] == [valid.json()["id"]]


@pytest.mark.security
@pytest.mark.negative
def test_user_cannot_read_another_users_notifications(user_a_client, user_b):
    assert_error(user_a_client.get_notifications(user_b["id"]), code="forbidden", status=403)


@pytest.mark.security
@pytest.mark.negative
def test_notifications_require_a_token(anon_client):
    assert_error(anon_client.get_notifications(UNKNOWN_ID), code="unauthorized", status=401)


@pytest.mark.negative
def test_notifications_for_unknown_user_return_404(admin_client):
    assert_error(admin_client.get_notifications(UNKNOWN_ID), code="not_found", status=404)
