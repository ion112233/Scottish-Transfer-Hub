"""Small retry-with-backoff helper shared by every network-facing step."""
import time


def retry(fn, attempts: int, base_delay: float, description: str):
    """Calls fn() up to `attempts` times, sleeping base_delay * 2**n between
    tries. Re-raises the last exception if every attempt fails."""
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < attempts:
                delay = base_delay * (2 ** (attempt - 1))
                print(f"{description} failed (attempt {attempt}/{attempts}): {exc} - retrying in {delay:.0f}s.")
                time.sleep(delay)
            else:
                print(f"{description} failed (attempt {attempt}/{attempts}): {exc} - giving up.")
    raise last_exc
