"""Bounded timeout + retry for backend calls.

Only errors marked retryable (transient TIMEOUT / BACKEND_UNAVAILABLE) are retried,
at most max_attempts times and never beyond total_budget_s. Permission, auth,
version, mapping and scope errors are never retried, and the Gateway never signs
in, switches backend or widens the whitelist to get past an error.
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Callable, TypeVar

from .errors import GatewayError

T = TypeVar("T")


def run_with_timeout(fn: Callable[[], T], timeout_s: float) -> T:
    box: queue.Queue = queue.Queue(maxsize=1)

    def target() -> None:
        try:
            box.put((True, fn()))
        except BaseException as e:  # noqa: BLE001 - relayed to the caller below
            box.put((False, e))

    threading.Thread(target=target, daemon=True, name="gateway-backend-call").start()
    try:
        ok, value = box.get(timeout=timeout_s)
    except queue.Empty:
        raise GatewayError("TIMEOUT", f"backend call exceeded {timeout_s:.1f}s", retryable=True) from None
    if ok:
        return value
    if isinstance(value, GatewayError):
        raise value
    # Unknown failure: report the type only, never the message (it may echo backend data).
    raise GatewayError("BACKEND_UNAVAILABLE", f"backend raised {type(value).__name__}", retryable=False)


def call_with_retry(fn: Callable[[], T], *, timeout_s: float, max_attempts: int, total_budget_s: float,
                    backoff_s: float = 0.5, sleep: Callable[[float], None] = time.sleep,
                    clock: Callable[[], float] = time.monotonic, on_attempt: Callable[[int], None] | None = None) -> T:
    deadline = clock() + total_budget_s
    last: GatewayError | None = None
    for attempt in range(1, max_attempts + 1):
        remaining = deadline - clock()
        if remaining <= 0:
            break
        if on_attempt:
            on_attempt(attempt)
        try:
            return run_with_timeout(fn, min(timeout_s, remaining))
        except GatewayError as e:
            last = e
            if not e.retryable or attempt == max_attempts:
                e.details = {**e.details, "attempts": attempt}
                raise
            sleep(max(0.0, min(backoff_s * (2 ** (attempt - 1)), deadline - clock())))
    err = GatewayError("TIMEOUT", "retry budget exhausted", retryable=True,
                       details={"last_error": last.code if last else None, "budget_s": total_budget_s})
    raise err
