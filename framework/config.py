"""Loads config/<TEST_ENV>.yaml (default: local). Secrets can be overridden by env vars."""
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"


@dataclass(frozen=True)
class Config:
    env: str
    base_url: str
    timeout_seconds: float
    headless: bool
    start_mock_server: bool
    tokens: dict


def load_config() -> Config:
    env = os.getenv("TEST_ENV", "local")
    path = PROJECT_ROOT / "config" / f"{env}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No config file for TEST_ENV='{env}': {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))

    tokens = dict(data["tokens"])
    for role in tokens:
        tokens[role] = os.getenv(f"{role.upper()}_TOKEN", tokens[role])

    return Config(
        env=env,
        base_url=os.getenv("BASE_URL", data["base_url"]).rstrip("/"),
        timeout_seconds=float(data["timeout_seconds"]),
        headless=data["headless"],
        start_mock_server=data["start_mock_server"],
        tokens=tokens,
    )
