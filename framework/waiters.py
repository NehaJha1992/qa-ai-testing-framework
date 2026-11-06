"""Helper for things that happen asynchronously (like notifications arriving after an API call)."""
import time


def wait_until(condition, description: str, timeout: float = 5.0, interval: float = 0.1):
    """Call condition() until it returns something truthy, then return that value.

    Fails with a clear message if it is still falsy after `timeout` seconds. This waits only
    as long as needed (unlike a fixed sleep) and is the one place in the framework that polls.
    """
    deadline = time.monotonic() + timeout
    while True:
        result = condition()
        if result:
            return result
        if time.monotonic() >= deadline:
            raise AssertionError(f"Timed out after {timeout}s waiting for: {description}")
        time.sleep(interval)
