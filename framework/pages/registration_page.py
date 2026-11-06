from playwright.sync_api import Page, expect


class RegistrationPage:
    """Registration form on the mock frontend. Locators use data-testid only."""

    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url
        self.name_input = page.get_by_test_id("reg-name")
        self.email_input = page.get_by_test_id("reg-email")
        self.account_type_select = page.get_by_test_id("reg-account-type")
        self.submit_button = page.get_by_test_id("reg-submit")
        self.success_message = page.get_by_test_id("reg-success")
        self.user_id = page.get_by_test_id("reg-user-id")
        self.error_message = page.get_by_test_id("reg-error")

    def open(self) -> None:
        self.page.goto(self.base_url)

    def register(self, name: str, email: str, account_type: str = "basic") -> None:
        self.name_input.fill(name)
        self.email_input.fill(email)
        self.account_type_select.select_option(account_type)
        self.submit_button.click()

    def expect_success(self) -> None:
        # expect() retries until the message shows up or the timeout expires
        expect(self.success_message).to_be_visible()
        expect(self.user_id).not_to_be_empty()

    def expect_error(self, message: str) -> None:
        expect(self.error_message).to_have_text(message)
        expect(self.success_message).to_be_hidden()
