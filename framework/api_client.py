"""Thin wrapper over requests.Session. Every call is logged to reports/api.log."""
import logging
import time

import requests

from framework.config import REPORTS_DIR

logger = logging.getLogger("api")


def setup_api_logging() -> None:
    """Send the 'api' logger to reports/api.log (called once per test session)."""
    REPORTS_DIR.mkdir(exist_ok=True)
    handler = logging.FileHandler(REPORTS_DIR / "api.log", mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False


def mask_token(token: str | None) -> str:
    """Show only the first 4 characters so logs never contain a usable token."""
    if not token:
        return "<none>"
    return token[:4] + "****"


class ApiClient:
    def __init__(self, base_url: str, token: str | None = None, timeout: float = 5):
        self.base_url = base_url
        self.token = token
        self.timeout = timeout
        self.session = requests.Session()

    # ---- endpoints ----
    def create_user(self, payload: dict) -> requests.Response:
        return self._request("POST", "/api/users", json=payload)

    def get_user(self, user_id: str) -> requests.Response:
        return self._request("GET", f"/api/users/{user_id}")

    def create_transaction(self, payload: dict) -> requests.Response:
        return self._request("POST", "/api/transactions", json=payload)

    def get_transactions(self, user_id: str) -> requests.Response:
        return self._request("GET", f"/api/transactions/{user_id}")

    def get_notifications(self, user_id: str) -> requests.Response:
        return self._request("GET", f"/api/notifications/{user_id}")

    def reset(self) -> requests.Response:
        return self._request("POST", "/__test__/reset")

    # ---- internals ----
    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        url = self.base_url + path

        start = time.perf_counter()
        response = self.session.request(
            method, url, headers=headers, timeout=self.timeout, **kwargs
        )
        duration_ms = (time.perf_counter() - start) * 1000

        logger.info(
            "%s %s token=%s request_body=%s -> %s in %.0fms response_body=%s",
            method, url, mask_token(self.token), kwargs.get("json"),
            response.status_code, duration_ms, response.text,
        )
        return response
