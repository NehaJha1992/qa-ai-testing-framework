from playwright.sync_api import Page, expect


class TransactionPage:
    """Transaction form on the mock frontend. Locators use data-testid only."""

    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url
        self.user_id_input = page.get_by_test_id("tx-user-id")
        self.amount_input = page.get_by_test_id("tx-amount")
        self.type_select = page.get_by_test_id("tx-type")
        self.recipient_input = page.get_by_test_id("tx-recipient-id")
        self.submit_button = page.get_by_test_id("tx-submit")
        self.success_message = page.get_by_test_id("tx-success")
        self.transaction_id = page.get_by_test_id("tx-id")
        self.error_message = page.get_by_test_id("tx-error")

    def open(self) -> None:
        self.page.goto(self.base_url)

    def create(self, user_id: str, amount: str, tx_type: str, recipient_id: str = "") -> None:
        self.user_id_input.fill(user_id)
        self.amount_input.fill(amount)
        self.type_select.select_option(tx_type)
        self.recipient_input.fill(recipient_id)
        self.submit_button.click()

    def expect_success(self) -> None:
        expect(self.success_message).to_be_visible()
        expect(self.transaction_id).not_to_be_empty()

    def expect_error(self, message: str) -> None:
        expect(self.error_message).to_have_text(message)
        expect(self.success_message).to_be_hidden()
