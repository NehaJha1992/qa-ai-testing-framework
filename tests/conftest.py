"""Shared fixtures for API and UI tests."""
import base64
import dataclasses
import os
import re
import socket
import subprocess
import sys
from urllib.parse import urlparse

import pytest
import requests
from pytest_html import extras
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from framework import factories
from framework.api_client import ApiClient, setup_api_logging
from framework.assertions import assert_status
from framework.config import PROJECT_ROOT, REPORTS_DIR, Config, load_config


# ---------- environment ----------

def _free_port() -> int:
    """Ask the OS for an unused port."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def config() -> Config:
    config = load_config()
    if config.start_mock_server:
        # Use a free port so tests never hit a server you started by hand (e.g. on 8000).
        config = dataclasses.replace(config, base_url=f"http://127.0.0.1:{_free_port()}")
    return config


@pytest.fixture(scope="session", autouse=True)
def api_logging():
    setup_api_logging()


def _wait_until_healthy(base_url: str) -> None:
    """Poll /health. urllib3 retries (with growing delays) on connection errors."""
    session = requests.Session()
    retry = Retry(total=15, connect=15, backoff_factor=0.1, backoff_max=1)
    session.mount("http://", HTTPAdapter(max_retries=retry))
    session.get(f"{base_url}/health", timeout=5).raise_for_status()


@pytest.fixture(scope="session", autouse=True)
def mock_server(config):
    """Start the mock app in a background process (local env only) and stop it at the end."""
    if not config.start_mock_server:
        yield
        return

    port = urlparse(config.base_url).port
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "mock_app.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=PROJECT_ROOT,
        env={**os.environ, "APP_ENV": "local"},
    )
    try:
        _wait_until_healthy(config.base_url)
        yield
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.fixture(autouse=True)
def reset_state(config, mock_server, admin_client):
    """Clear all data before every test so tests never depend on each other."""
    if config.start_mock_server:
        assert_status(admin_client.reset(), 200)


# ---------- API clients, one per role ----------

def _client(config: Config, role: str | None) -> ApiClient:
    token = config.tokens[role] if role else None
    return ApiClient(config.base_url, token, config.timeout_seconds)


@pytest.fixture
def admin_client(config):
    return _client(config, "admin")


@pytest.fixture
def user_a_client(config):
    return _client(config, "user_a")


@pytest.fixture
def user_b_client(config):
    return _client(config, "user_b")


@pytest.fixture
def anon_client(config):
    return _client(config, None)


# ---------- data created through the API ----------

@pytest.fixture
def user_a(user_a_client):
    """User A, created with user A's own token (this is what links the token to the user)."""
    response = user_a_client.create_user(factories.user())
    assert_status(response, 201)
    return response.json()


@pytest.fixture
def user_b(user_b_client):
    response = user_b_client.create_user(factories.user())
    assert_status(response, 201)
    return response.json()


@pytest.fixture
def make_user(admin_client):
    """Call make_user() to create another user (as admin). Extra args override the payload."""
    def _make_user(**overrides):
        response = admin_client.create_user(factories.user(**overrides))
        assert_status(response, 201)
        return response.json()
    return _make_user


# ---------- UI settings ----------

@pytest.fixture(scope="session")
def base_url(config):
    """Used by pytest-playwright as the site root."""
    return config.base_url


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args, config):
    return {**browser_type_launch_args, "headless": config.headless}


# ---------- screenshot on UI failure, embedded in the HTML report ----------

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    page = item.funcargs.get("page")
    if report.when == "call" and report.failed and page is not None:
        screenshot_dir = REPORTS_DIR / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        png = page.screenshot()
        safe_name = re.sub(r'[^A-Za-z0-9_.-]', "_", item.name)  # Windows forbids characters like : * ? "
        (screenshot_dir / f"{safe_name}.png").write_bytes(png)
        report.extras = getattr(report, "extras", []) + [
            extras.png(base64.b64encode(png).decode())
        ]
