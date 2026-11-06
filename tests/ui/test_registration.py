import pytest

from framework import factories
from framework.pages.registration_page import RegistrationPage

pytestmark = pytest.mark.ui


@pytest.fixture
def registration_page(page, base_url):
    registration = RegistrationPage(page, base_url)
    registration.open()
    return registration


@pytest.mark.smoke
def test_registration_shows_confirmation(registration_page):
    data = factories.user()

    registration_page.register(data["name"], data["email"], data["accountType"])

    registration_page.expect_success()


@pytest.mark.negative
def test_registration_with_invalid_email_shows_error(registration_page):
    data = factories.user(email="not-an-email")

    registration_page.register(data["name"], data["email"], data["accountType"])

    registration_page.expect_error("email is not a valid email address")


@pytest.mark.negative
def test_empty_registration_form_shows_required_error(registration_page):
    registration_page.register(name="", email="")

    registration_page.expect_error("name is required")


@pytest.mark.negative
def test_registration_with_existing_email_shows_error(registration_page, make_user):
    existing_user = make_user()  # prerequisite created through the API

    registration_page.register("Another Person", existing_user["email"])

    registration_page.expect_error("A user with this email already exists")
