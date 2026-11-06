# Fintech API + UI Test Automation Framework

## Overview
A test automation framework for a hypothetical fintech platform (User, Transaction and Notification
services behind an API Gateway). None of those services exist, so this repo includes a small
**mock gateway** (`mock_app/`, FastAPI, in-memory storage) that simulates the User and Transaction
services behind one app, plus a tiny HTML frontend. The framework tests that mock through its API
and its UI. The Notification Service is simulated inside the same app (in memory, no Redis): creating a transaction publishes an event, and notifications appear shortly after.

Stack: Python 3.11+, pytest, pytest-playwright (Chromium), requests, pydantic, Faker, PyYAML,
pytest-html + JUnit XML.

## Quick start
Requires Python 3.11 or newer. Works on Windows, macOS and Linux.

**macOS / Linux** (or Windows with `make`):
```bash
make install   # creates .venv, installs pinned requirements, installs Chromium
make test      # starts the mock app automatically, runs all tests, writes reports/
```

**Windows (PowerShell), no `make` needed:**
```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
pytest
```
If PowerShell blocks the activate script, run `Set-ExecutionPolicy -Scope Process RemoteSigned` first, or use `.venv\Scripts\activate.bat` in Command Prompt.

**macOS / Linux without `make`:** `python3 -m venv .venv && source .venv/bin/activate`, then the same `pip install`, `playwright install chromium` and `pytest` commands.

With the virtual environment active, these work on every OS:
- `pytest -m api`, `pytest -m ui`, `pytest -m smoke`: run a subset
- `python performance/run_perf.py`: the load test (about 30 seconds)
- open `reports/report.html` in a browser to see the results

The `make` shortcuts are `make test-api`, `make test-ui`, `make test-smoke`, `make test-perf` and `make report` (opens the HTML report).

## Project structure
```
mock_app/            Mock gateway: main.py (endpoints, auth, validation), settings.py (tokens), static/index.html
framework/
  config.py          Loads config/<TEST_ENV>.yaml, env-var overrides for tokens/base URL
  waiters.py         wait_until(): polls until an async result (e.g. a notification) shows up, with a timeout
  api_client.py      requests.Session wrapper, one method per endpoint, logs to reports/api.log
  factories.py       Valid user/transaction payloads with unique data; override kwargs for invalid variants
  assertions.py      assert_status, assert_matches_schema, assert_error, assert_money_equal
  schemas.py         Pydantic models for user, transaction and error responses
  pages/             Page objects (RegistrationPage, TransactionPage), data-testid locators
config/              local.yaml, staging.yaml
performance/         locustfile.py (load test scenario + thresholds), run_perf.py (starts the mock app, runs Locust; works on any OS)
tests/
  conftest.py        Server start, per-test reset, role-based clients, data fixtures, failure screenshots
  api/               test_users.py, test_transactions.py, test_auth.py, test_notifications.py
  ui/                test_registration.py, test_transactions.py
.github/workflows/   tests.yml (install, run, upload reports/)
```

## Test strategy
- **Risk-based.** Money movement (amount validation, precision, sender/recipient checks, self-transfer)
  and authorization (401/403, no cross-user access, no creating transactions for someone else) get the deepest coverage.
- **Test pyramid.** Most tests (54 of 61) are at the API layer, where they are fast and precise. Only
  7 UI tests cover the critical flows: registration and transaction creation, each with a happy path and the main error paths (empty form, duplicate email, invalid email, negative amount, transfer to yourself).
- **Markers:** `smoke`, `api`, `ui`, `negative`, `security` (registered in `pytest.ini`). Example: `pytest -m "api and security"`.
- Validation cases are parametrized so each rule is one readable table of inputs.
- Money is compared with `Decimal` built from strings, never float `==`.

## Performance testing
A small Locust load test (`performance/locustfile.py`) exercises the transaction endpoints. It is separate from
the pytest suite, so `make test` stays fast. Run it with `make test-perf` or `python performance/run_perf.py`.
- **Scenario:** 20 virtual users for 30 seconds. Each creates a sender and a recipient, then repeatedly
  creates transfers (`POST /api/transactions`, 3x weight) and lists transactions (`GET /api/transactions/:userId`, 1x weight).
- **Thresholds (the run fails if broken):** p95 response time under 500 ms and failure rate under 1%.
- **Output:** `reports/performance.html` and CSV files, plus the console summary.
- **In CI:** the GitHub Actions workflow runs it after the functional tests, and fails the build if a threshold is broken. The Locust report is uploaded with the other reports.
- **Caveat:** the target is a single-process in-memory mock, so the numbers show the framework works,
  not how a real deployment performs. Against a real environment, I would run it from a separate machine with realistic data and thresholds.

## Test data management
- Factories (`framework/factories.py`) produce valid payloads with unique emails (UUID-based), so tests never collide across runs.
- Invalid variants come from overrides: `factories.user(email="not-an-email")`, or `factories.user(remove=["name"])`.
- All prerequisite data (users) is created through the API by fixtures, including for UI tests.
- Isolation: before every test, `POST /__test__/reset` clears the mock's state (only exists when `APP_ENV=local`).

## Environment configuration
- `TEST_ENV` selects `config/<env>.yaml` (default `local`). Each file has base URL, timeouts, tokens, headless flag.
- Environment variables override values: `BASE_URL` (ignored when the suite starts its own mock app), `ADMIN_TOKEN`, `USER_A_TOKEN`, `USER_B_TOKEN`. See `.env.example`.
- `local` starts the mock app in a background process on a free port (so it never clashes with a server you run by hand) and waits for `/health`. `staging.yaml` is a placeholder
  to show the pattern; no real staging exists.

## Reporting
Every run writes to `reports/` (git-ignored):
- `report.html`: self-contained pytest-html report; failed UI tests have the screenshot embedded.
- `junit.xml`: for CI systems.
- `api.log`: every API request/response (method, URL, status, duration, bodies). Tokens are masked to their first 4 characters.
- `screenshots/` and `playwright/`: failure screenshots and Playwright traces (`trace.zip`, kept only for failures;
  view with `playwright show-trace`).
The GitHub Actions workflow uploads the whole `reports/` folder as an artifact.

## Assumptions
- The gateway is modeled as one app. The Notification Service is simulated in the same app, with no Redis: this notification behavior is my own design, since the brief does not define one.
- **Notification behavior:** after a transaction is created, the sender gets a `transaction_created` notification, and for transfers the recipient also gets `transfer_received`. Rejected transactions create none. Notifications are delivered about 0.2s after the API response (asynchronous, like a queue), and are read with `GET /api/notifications/:userId` (the user themself or an admin; 401/403/404 as for the other endpoints). Tests wait for them with a polling helper (`framework/waiters.py`), never a fixed sleep.
- Auth is `Authorization: Bearer <token>` with three seeded tokens (user A, user B, admin). A user token is
  tied to the first user it creates (a stand-in for a real token carrying the user id).
- Any valid token may create a user (registration must be possible). Non-admins can only read their own
  user and transactions, and cannot create transactions with someone else as `userId` (403). The last rule goes slightly beyond the brief because it matters most for money movement.
- `GET /api/transactions/:userId` returns transactions the user **sent** (as a list). Receiving side is not modeled.
- Authorization is checked before existence, so a non-admin gets 403 (not 404) for unknown ids. Existence is not leaked.
- A user `name` must start with a letter or digit (so `*` or `@john` is rejected with `invalid_name`); the rest of the name is not restricted.
- Length limits (my choice, the brief gave none): name at most 50 characters, email at most 254. Exactly at the limit is accepted, one over is rejected with 400.
- `amount` must be a JSON number; strings like `"100"` are rejected. Max 2 decimal places.
- Only `recipientId` on transfers is used; deposits and withdrawals have `recipientId: null`.
- The mock frontend calls the API with the admin token so it can act for any user.
- Screenshots are taken by a small hook in `tests/conftest.py` (so they can be embedded in the HTML report); traces use pytest-playwright's `--tracing retain-on-failure`.

## Known risks not covered
A real payments system has risks this suite does not test, because the mock (and the brief's payloads)
have no balances, currency, status field or database. I would test these first, roughly in priority order (idempotency, concurrency and atomicity are listed under "What I'd add next"):
- **Insufficient balance:** a withdrawal or transfer larger than the balance must be rejected. Needs account balances.
- **Authorization after creation:** user A must still get 403 for user B's transactions once B has real data. Current 403 tests mostly run before B has transactions.
- **Currency:** valid currencies, rounding, and conversion rules. Needs a currency field.
- **Transaction status:** valid transitions between pending, completed and failed. Needs a status field.
- **Database failure:** how the API responds when storage is down or slow. Needs fault injection against real services.

## Why Python
The brief allowed it, and it's my strongest language.

## What I'd add next
- Contract tests between services (e.g., Pact) once service contracts are available
- Notification Service verification against real Redis once an event contract is defined (today it is simulated in memory)
- Performance testing against the transaction endpoint at higher load using Locust
- Test data seeding against a real MongoDB in an integration environment
- Parallel execution with pytest-xdist; the current shared reset would need per-worker isolation or worker-specific test environments
- Additional production-level scenarios such as idempotency, concurrency, transaction atomicity, and failure/retry behavior
