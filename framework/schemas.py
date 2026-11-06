"""Pydantic models describing what the API promises to return."""
from typing import Literal

from pydantic import BaseModel, ConfigDict


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")  # unexpected fields fail the schema check


class UserSchema(_Strict):
    id: str
    name: str
    email: str
    accountType: Literal["basic", "premium"]


class TransactionSchema(_Strict):
    id: str
    userId: str
    amount: float
    type: Literal["transfer", "deposit", "withdrawal"]
    recipientId: str | None
    createdAt: str


class NotificationSchema(_Strict):
    id: str
    userId: str
    type: Literal["transaction_created", "transfer_received"]
    message: str
    transactionId: str
    createdAt: str


class ErrorDetail(_Strict):
    code: str
    message: str
    field: str | None


class ErrorSchema(_Strict):
    error: ErrorDetail
