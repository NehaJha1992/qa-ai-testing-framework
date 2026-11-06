import pytest

from framework.pages.transaction_page import TransactionPage

pytestmark = pytest.mark.ui


@pytest.fixture
def transaction_page(page, base_url):
    transactions = TransactionPage(page, base_url)
    transactions.open()
    return transactions


def test_transfer_shows_confirmation(transaction_page, make_user):
    sender, recipient = make_user(), make_user()  # prerequisites created through the API

    transaction_page.create(sender["id"], "25.50", "transfer", recipient["id"])

    transaction_page.expect_success()


@pytest.mark.negative
def test_negative_amount_shows_error(transaction_page, make_user):
    sender = make_user()

    transaction_page.create(sender["id"], "-5", "deposit")

    transaction_page.expect_error("amount must be greater than 0")


@pytest.mark.negative
def test_transfer_to_yourself_shows_error(transaction_page, make_user):
    user = make_user()

    transaction_page.create(user["id"], "10", "transfer", recipient_id=user["id"])

    transaction_page.expect_error("Cannot transfer to yourself")
