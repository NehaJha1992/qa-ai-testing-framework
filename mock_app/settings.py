"""Settings for the mock gateway. Everything here is fake and only meant for local testing."""
import os

# "local" enables the test-only reset endpoint. Any other value disables it.
APP_ENV = os.getenv("APP_ENV", "local")

# Seeded bearer tokens. Role "user" tokens get bound to a user id the first time
# that token is used to create a user (see main.create_user). Role "admin" can read any user.
TOKENS = {
    "token-user-a": {"role": "user"},
    "token-user-b": {"role": "user"},
    "token-admin": {"role": "admin"},
}
