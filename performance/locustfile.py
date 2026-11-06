"""Load test for the transaction endpoints, run with Locust.

Each virtual user:
  1. creates two users when it starts (a sender and a recipient)
  2. then repeatedly creates transfers and lists the sender's transactions

Pass/fail thresholds are checked when the run ends (see check_thresholds at the bottom).
"""
import uuid

from locust import HttpUser, between, events, task

# ---- thresholds: the run fails if either is broken ----
MAX_P95_MS = 500          # 95% of requests must finish faster than this
MAX_FAILURE_RATE = 0.01   # at most 1% of requests may fail

ADMIN_HEADERS = {"Authorization": "Bearer token-admin"}


class TransactionUser(HttpUser):
    # Each virtual user pauses 0.1-0.5 seconds between tasks, like a real person would.
    wait_time = between(0.1, 0.5)

    def on_start(self):
        """Runs once per virtual user, before its tasks. Creates the users it needs."""
        self.sender_id = self._create_user("sender")
        self.recipient_id = self._create_user("recipient")

    def _create_user(self, name):
        response = self.client.post(
            "/api/users",
            json={
                "name": f"Load {name}",
                "email": f"{uuid.uuid4().hex}@example.com",  # unique, so no 409 conflicts
                "accountType": "basic",
            },
            headers=ADMIN_HEADERS,
            name="POST /api/users (setup)",
        )
        return response.json()["id"]

    @task(3)  # weight 3: runs three times as often as the task below
    def create_transfer(self):
        self.client.post(
            "/api/transactions",
            json={
                "userId": self.sender_id,
                "amount": 10.25,
                "type": "transfer",
                "recipientId": self.recipient_id,
            },
            headers=ADMIN_HEADERS,
            name="POST /api/transactions",
        )

    @task(1)
    def list_transactions(self):
        # name= groups all these URLs into one row in the report (the id differs per user)
        self.client.get(
            f"/api/transactions/{self.sender_id}",
            headers=ADMIN_HEADERS,
            name="GET /api/transactions/:userId",
        )


@events.quitting.add_listener
def check_thresholds(environment, **_kwargs):
    """Runs when Locust finishes. Sets a non-zero exit code if a threshold is broken."""
    stats = environment.stats.total
    p95 = stats.get_response_time_percentile(0.95)

    if stats.fail_ratio > MAX_FAILURE_RATE:
        print(f"THRESHOLD FAILED: failure rate {stats.fail_ratio:.2%} > {MAX_FAILURE_RATE:.2%}")
        environment.process_exit_code = 1
    elif p95 > MAX_P95_MS:
        print(f"THRESHOLD FAILED: p95 {p95} ms > {MAX_P95_MS} ms")
        environment.process_exit_code = 1
    else:
        print(f"THRESHOLDS PASSED: p95 {p95} ms, failure rate {stats.fail_ratio:.2%}")
