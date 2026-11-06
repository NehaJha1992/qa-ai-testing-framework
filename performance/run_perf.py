"""Starts the mock app, runs a Locust load test against it, then stops the app.

Works on Windows, macOS and Linux.  Usage:  python performance/run_perf.py
Optional: set DURATION (e.g. DURATION=10s) to change the run length.
"""
import os
import subprocess
import sys
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PORT = 8100
USERS = 20          # virtual users running at the same time
SPAWN_RATE = 5      # new users started per second
DURATION = os.getenv("DURATION", "30s")
BASE_URL = f"http://127.0.0.1:{PORT}"


def wait_until_healthy() -> None:
    """Retry /health with growing delays (urllib3 does the waiting, no fixed sleep)."""
    session = requests.Session()
    retry = Retry(total=15, connect=15, backoff_factor=0.1, backoff_max=1)
    session.mount("http://", HTTPAdapter(max_retries=retry))
    session.get(f"{BASE_URL}/health", timeout=5).raise_for_status()


def main() -> int:
    (PROJECT_ROOT / "reports").mkdir(exist_ok=True)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "mock_app.main:app",
         "--port", str(PORT), "--log-level", "warning"],
        cwd=PROJECT_ROOT, env={**os.environ, "APP_ENV": "local"},
    )
    try:
        wait_until_healthy()
        result = subprocess.run(
            [sys.executable, "-m", "locust", "-f", "performance/locustfile.py",
             "--headless", "--host", BASE_URL,
             "--users", str(USERS), "--spawn-rate", str(SPAWN_RATE), "--run-time", DURATION,
             "--html", "reports/performance.html", "--csv", "reports/performance"],
            cwd=PROJECT_ROOT,
        )
        return result.returncode  # non-zero if a threshold in locustfile.py failed
    finally:
        server.terminate()
        server.wait(timeout=10)


if __name__ == "__main__":
    sys.exit(main())
