"""Custom assertions with failure messages that show the status, body and what was expected."""
from decimal import Decimal

import requests
from pydantic import BaseModel, ValidationError

from framework.schemas import ErrorSchema


def assert_status(response: requests.Response, expected: int) -> None:
    assert response.status_code == expected, (
        f"Expected HTTP {expected} but got {response.status_code} "
        f"for {response.request.method} {response.url}\nBody: {response.text}"
    )


def assert_matches_schema(data: dict, schema: type[BaseModel]) -> BaseModel:
    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        raise AssertionError(f"Response does not match {schema.__name__}:\n{exc}\nData: {data}")


def assert_error(response: requests.Response, code: str, field: str | None = None,
                 status: int | None = None) -> None:
    """Check the standard error body. Optionally check the HTTP status and the field."""
    if status is not None:
        assert_status(response, status)
    error = assert_matches_schema(response.json(), ErrorSchema).error
    assert error.code == code, f"Expected error code '{code}' but got '{error.code}': {error.message}"
    if field is not None:
        assert error.field == field, f"Expected error field '{field}' but got '{error.field}'"


def assert_money_equal(actual, expected) -> None:
    """Compare money as Decimal built from strings. Never use == on floats for money."""
    actual_d, expected_d = Decimal(str(actual)), Decimal(str(expected))
    assert actual_d == expected_d, f"Money mismatch: got {actual_d}, expected {expected_d}"
