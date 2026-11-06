"""Test data factories. Valid data by default; pass keyword overrides to make it invalid.

    user(email="not-an-email")      -> a user payload with a bad email
    transaction(user_id, amount=-5) -> a transaction payload with a negative amount
Pass remove=["name"] to drop a field entirely.
"""
import uuid

from faker import Faker

_faker = Faker()


def user(remove: list[str] | None = None, **overrides) -> dict:
    payload = {
        "name": _faker.name(),
        # uuid in the local part keeps emails unique across runs and parallel tests
        "email": f"{uuid.uuid4().hex[:12]}@example.com",
        "accountType": "premium",
    }
    return _finish(payload, remove, overrides)


def transaction(user_id: str, remove: list[str] | None = None, **overrides) -> dict:
    payload = {
        "userId": user_id,
        "amount": 100.50,
        "type": "deposit",
    }
    # A transfer needs a recipient; the caller supplies one via recipientId=...
    return _finish(payload, remove, overrides)


def _finish(payload: dict, remove: list[str] | None, overrides: dict) -> dict:
    payload.update(overrides)
    for field in remove or []:
        payload.pop(field, None)
    return payload
