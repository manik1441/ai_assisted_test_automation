import allure
import pytest
import re
from playwright.sync_api import Page, expect


class LinkedInLoginPage:
    def __init__(self, page: Page) -> None:
        self.page = page
        self.email_input = page.get_by_label("Email or phone", exact=True).and_(page.locator(":visible"))
        self.password_input = page.get_by_label("Password", exact=True).and_(page.locator(":visible"))
        self.login_button = page.get_by_role("button", name="Sign in", exact=True).and_(page.locator(":visible"))
        self.forgot_password_link = page.get_by_text("Forgot password?").and_(page.locator(":visible"))
        self.remember_me_checkbox = page.get_by_label("Keep me signed in").and_(page.locator(":visible"))

    def navigate(self, base_url: str) -> None:
        if not base_url.endswith("/login"):
            base_url = base_url.rstrip("/") + "/login"
        self.page.goto(base_url)

    def login(self, email: str, password: str) -> None:
        self.email_input.fill(email)
        self.password_input.fill(password)
        self.login_button.click()

    def check_remember_me(self) -> None:
        self.remember_me_checkbox.check()


@allure.title("Verify successful login with valid credentials")
@allure.severity(allure.severity_level.CRITICAL)
def test_verify_successful_login_with_valid_credentials(page: Page) -> None:
    login_page = LinkedInLoginPage(page)
    login_page.navigate("https://linkedin.com")
    login_page.login("valid_user@example.com", "valid_password")
    expect(page).to_have_url(re.compile(r"/feed"))
    expect(page.get_by_text("Welcome")).to_be_visible()


@allure.title("Check error message when using invalid credentials")
@allure.severity(allure.severity_level.CRITICAL)
def test_check_error_message_when_using_invalid_credentials(page: Page) -> None:
    login_page = LinkedInLoginPage(page)
    login_page.navigate("https://linkedin.com")
    login_page.login("invalid_user@example.com", "wrong_password")
    expect(page.get_by_text("Hmm, we don’t recognize that email.")).to_be_visible()


@allure.title("Verify login functionality with empty email and password fields")
@allure.severity(allure.severity_level.NORMAL)
def test_verify_login_functionality_with_empty_fields(page: Page) -> None:
    login_page = LinkedInLoginPage(page)
    login_page.navigate("https://linkedin.com")
    login_page.login("", "")
    # LinkedIn uses HTML5 'required' validation, so the form never submits.
    # We verify that we are still on the login page and the email input is focused.
    expect(page).to_have_url(re.compile(r"/login"))
    expect(login_page.email_input).to_be_focused()


@allure.title("Test login with an unregistered email address")
@allure.severity(allure.severity_level.NORMAL)
def test_login_with_unregistered_email(page: Page) -> None:
    login_page = LinkedInLoginPage(page)
    login_page.navigate("https://linkedin.com")
    login_page.login("unregistered_user@example.com", "any_password")
    expect(page.get_by_text("We couldn’t find an account with that email address.")).to_be_visible()


@allure.title("Check the 'Forgot password?' link functionality")
@allure.severity(allure.severity_level.NORMAL)
def test_check_forgot_password_link_functionality(page: Page) -> None:
    login_page = LinkedInLoginPage(page)
    login_page.navigate("https://linkedin.com")
    login_page.forgot_password_link.click()
    expect(page).to_have_url(re.compile(r"/password-reset"))


@allure.title("Test login with a valid email but incorrect password")
@allure.severity(allure.severity_level.NORMAL)
def test_login_with_valid_email_incorrect_password(page: Page) -> None:
    login_page = LinkedInLoginPage(page)
    login_page.navigate("https://linkedin.com")
    login_page.login("valid_user@example.com", "incorrect_password")
    expect(page.get_by_text("The password you entered is incorrect.")).to_be_visible()


@allure.title("Verify the remember me option retains user login")
@allure.severity(allure.severity_level.NORMAL)
def test_verify_remember_me_option_retains_user_login(page: Page) -> None:
    login_page = LinkedInLoginPage(page)
    login_page.navigate("https://linkedin.com")
    login_page.login("valid_user@example.com", "valid_password")
    login_page.check_remember_me()
    login_page.navigate("https://linkedin.com")
    expect(page).to_have_url(re.compile(r"/feed"))


@allure.title("Check login functionality on a mobile device")
@allure.severity(allure.severity_level.NORMAL)
def test_check_login_functionality_on_mobile_device(page: Page) -> None:
    login_page = LinkedInLoginPage(page)
    login_page.navigate("https://linkedin.com")
    page.set_viewport_size({"width": 375, "height": 667})
    login_page.login("valid_user@example.com", "valid_password")
    expect(page).to_have_url(re.compile(r"/feed"))