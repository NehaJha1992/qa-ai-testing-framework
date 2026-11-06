"""Mock API gateway: simulates the User + Transaction services behind one app.

State lives in plain dicts, so restarting the server (or calling /__test__/reset) clears it.
Validation is done by hand (not pydantic request models) so every error uses the same body:
{"error": {"code": "...", "message": "...", "field": "..."}}
"""
import asyncio
import json
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from mock_app import settings

app = FastAPI(title="Mock API Gateway")

USERS: dict[str, dict] = {}
TRANSACTIONS: dict[str, dict] = {}
TOKEN_TO_USER_ID: dict[str, str] = {}  # which user a "user" token belongs to

# Simulated Notification Service. In the real system it listens to events (e.g. via Redis);
# here the gateway hands it the transaction in a background task, and it stores the result in memory.
NOTIFICATIONS: dict[str, list[dict]] = {}  # user id -> notifications
NOTIFICATION_DELAY_SECONDS = 0.2           # delivery is asynchronous, like a real queue
STATE = {"generation": 0}                  # bumped by reset so late deliveries are dropped

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ACCOUNT_TYPES = ["basic", "premium"]
TRANSACTION_TYPES = ["transfer", "deposit", "withdrawal"]
MAX_NAME_LENGTH = 50
MAX_EMAIL_LENGTH = 254


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, field: str | None = None):
        self.status = status
        self.code = code
        self.message = message
        self.field = field


@app.exception_handler(ApiError)
async def handle_api_error(_request: Request, exc: ApiError):
    body = {"error": {"code": exc.code, "message": exc.message, "field": exc.field}}
    return JSONResponse(status_code=exc.status, content=body)


# ---------- helpers ----------

def authenticate(request: Request) -> dict:
    """Return {"role": ..., "user_id": ...} for the caller, or raise 401."""
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme != "Bearer" or token not in settings.TOKENS:
        raise ApiError(401, "unauthorized", "Missing or invalid bearer token")
    return {
        "token": token,
        "role": settings.TOKENS[token]["role"],
        "user_id": TOKEN_TO_USER_ID.get(token),
    }


def require_self_or_admin(caller: dict, user_id: str) -> None:
    if caller["role"] != "admin" and caller["user_id"] != user_id:
        raise ApiError(403, "forbidden", "You are not allowed to access this user's data")


async def read_json_object(request: Request) -> dict:
    raw = await request.body()
    try:
        # parse_float=Decimal keeps amounts exact, so 100.505 is not silently rounded.
        body = json.loads(raw, parse_float=Decimal)
    except ValueError:
        raise ApiError(400, "invalid_body", "Request body must be valid JSON")
    if not isinstance(body, dict):
        raise ApiError(400, "invalid_body", "Request body must be a JSON object")
    return body


def require_string(body: dict, field: str) -> str:
    value = body.get(field)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ApiError(400, "required_field", f"{field} is required", field)
    if not isinstance(value, str):
        raise ApiError(400, "invalid_field", f"{field} must be a string", field)
    return value.strip()


def public_transaction(tx: dict) -> dict:
    return {**tx, "amount": float(tx["amount"])}  # JSON number; tests compare with Decimal


# ---------- infrastructure endpoints ----------

@app.get("/health")
def health():
    return {"status": "ok"}


if settings.APP_ENV == "local":

    @app.post("/__test__/reset")
    def reset():
        USERS.clear()
        TRANSACTIONS.clear()
        TOKEN_TO_USER_ID.clear()
        NOTIFICATIONS.clear()
        STATE["generation"] += 1  # pending deliveries from before the reset must not appear later
        return {"status": "reset"}


@app.get("/")
def frontend():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


# ---------- users ----------

@app.post("/api/users", status_code=201)
async def create_user(request: Request):
    caller = authenticate(request)
    body = await read_json_object(request)

    name = require_string(body, "name")
    email = require_string(body, "email")
    account_type = require_string(body, "accountType")

    if not name[0].isalnum():
        raise ApiError(400, "invalid_name", "name must start with a letter or digit", "name")
    if len(name) > MAX_NAME_LENGTH:
        raise ApiError(400, "invalid_name",
                       f"name must be at most {MAX_NAME_LENGTH} characters", "name")
    if len(email) > MAX_EMAIL_LENGTH:
        raise ApiError(400, "invalid_email",
                       f"email must be at most {MAX_EMAIL_LENGTH} characters", "email")
    if not EMAIL_PATTERN.match(email):
        raise ApiError(400, "invalid_email", "email is not a valid email address", "email")
    if account_type not in ACCOUNT_TYPES:
        raise ApiError(400, "invalid_account_type",
                       f"accountType must be one of {ACCOUNT_TYPES}", "accountType")
    if any(u["email"].lower() == email.lower() for u in USERS.values()):
        raise ApiError(409, "duplicate_email", "A user with this email already exists", "email")

    user = {"id": str(uuid.uuid4()), "name": name, "email": email, "accountType": account_type}
    USERS[user["id"]] = user

    # A "user" token is bound to the first user it creates. This is how the mock
    # knows which user id the token owns (real systems would put it in the token).
    if caller["role"] == "user" and caller["user_id"] is None:
        TOKEN_TO_USER_ID[caller["token"]] = user["id"]
    return user


@app.get("/api/users/{user_id}")
def get_user(user_id: str, request: Request):
    caller = authenticate(request)
    require_self_or_admin(caller, user_id)
    if user_id not in USERS:
        raise ApiError(404, "not_found", "User not found")
    return USERS[user_id]


# ---------- transactions ----------

@app.post("/api/transactions", status_code=201)
async def create_transaction(request: Request, background_tasks: BackgroundTasks):
    caller = authenticate(request)
    body = await read_json_object(request)

    user_id = require_string(body, "userId")

    # amount: a JSON number, > 0, at most 2 decimal places
    amount = body.get("amount")
    if amount is None:
        raise ApiError(400, "required_field", "amount is required", "amount")
    if isinstance(amount, bool) or not isinstance(amount, (int, Decimal)):
        raise ApiError(400, "invalid_amount", "amount must be a number", "amount")
    amount = Decimal(amount)
    if amount <= 0:
        raise ApiError(400, "invalid_amount", "amount must be greater than 0", "amount")
    if amount.as_tuple().exponent < -2:
        raise ApiError(400, "invalid_amount", "amount can have at most 2 decimal places", "amount")

    tx_type = require_string(body, "type")
    if tx_type not in TRANSACTION_TYPES:
        raise ApiError(400, "invalid_type", f"type must be one of {TRANSACTION_TYPES}", "type")

    recipient_id = None  # only transfers have a recipient
    if tx_type == "transfer":
        recipient_id = require_string(body, "recipientId")
        if recipient_id == user_id:
            raise ApiError(400, "self_transfer", "Cannot transfer to yourself", "recipientId")

    # Authorization before existence checks, so callers cannot probe which ids exist.
    require_self_or_admin(caller, user_id)
    if user_id not in USERS:
        raise ApiError(404, "not_found", "Sender not found", "userId")
    if tx_type == "transfer" and recipient_id not in USERS:
        raise ApiError(404, "not_found", "Recipient not found", "recipientId")

    tx = {
        "id": str(uuid.uuid4()),
        "userId": user_id,
        "amount": amount,
        "type": tx_type,
        "recipientId": recipient_id,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    TRANSACTIONS[tx["id"]] = tx
    # "Publish the event": the notification service handles it after the response is sent.
    background_tasks.add_task(deliver_notifications, tx, STATE["generation"])
    return public_transaction(tx)


@app.get("/api/transactions/{user_id}")
def list_transactions(user_id: str, request: Request):
    caller = authenticate(request)
    require_self_or_admin(caller, user_id)
    if user_id not in USERS:
        raise ApiError(404, "not_found", "User not found")
    return [public_transaction(t) for t in TRANSACTIONS.values() if t["userId"] == user_id]


# ---------- notifications (simulated Notification Service) ----------

def add_notification(user_id: str, kind: str, message: str, tx: dict) -> None:
    NOTIFICATIONS.setdefault(user_id, []).append({
        "id": str(uuid.uuid4()),
        "userId": user_id,
        "type": kind,
        "message": message,
        "transactionId": tx["id"],
        "createdAt": datetime.now(timezone.utc).isoformat(),
    })


async def deliver_notifications(tx: dict, generation: int) -> None:
    """The sender is always notified. For transfers, the recipient is notified too."""
    await asyncio.sleep(NOTIFICATION_DELAY_SECONDS)
    if generation != STATE["generation"]:
        return  # state was reset while this was waiting
    amount = format(tx["amount"], ".2f")
    add_notification(tx["userId"], "transaction_created",
                     f"Your {tx['type']} of {amount} was successful", tx)
    if tx["type"] == "transfer":
        add_notification(tx["recipientId"], "transfer_received", f"You received {amount}", tx)


@app.get("/api/notifications/{user_id}")
def list_notifications(user_id: str, request: Request):
    caller = authenticate(request)
    require_self_or_admin(caller, user_id)
    if user_id not in USERS:
        raise ApiError(404, "not_found", "User not found")
    return NOTIFICATIONS.get(user_id, [])
