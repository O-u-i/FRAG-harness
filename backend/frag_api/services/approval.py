from __future__ import annotations

import secrets
import time
from collections import OrderedDict
from threading import Lock
from typing import Any


class ApprovalRegistry:
    """Short-lived, single-use approval for an exact outbound fingerprint."""

    def __init__(self, maximum: int = 128, ttl_seconds: int = 600):
        self._maximum = maximum
        self._ttl_seconds = ttl_seconds
        self._pending: OrderedDict[str, tuple[str, float, Any]] = OrderedDict()
        self._lock = Lock()

    def issue(self, fingerprint: str, state: Any = None) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._pending[token] = (fingerprint, time.monotonic() + self._ttl_seconds, state)
            while len(self._pending) > self._maximum:
                self._pending.popitem(last=False)
        return token

    def consume(self, token: str, fingerprint: str) -> bool:
        return self.consume_state(token, fingerprint)[0]

    def consume_state(self, token: str, fingerprint: str) -> tuple[bool, Any]:
        with self._lock:
            stored = self._pending.pop(token, None)
        valid = stored is not None and time.monotonic() < stored[1] and secrets.compare_digest(stored[0], fingerprint)
        return valid, stored[2] if valid else None


class PendingInferenceRegistry:
    """Bounded, expiring, single-use server-side state for the second model call."""

    def __init__(self, maximum: int = 128, ttl_seconds: int = 600):
        self._maximum = maximum
        self._ttl_seconds = ttl_seconds
        self._pending: OrderedDict[str, tuple[str, float, Any]] = OrderedDict()
        self._lock = Lock()

    def issue(self, fingerprint: str, state: Any) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._pending[token] = (fingerprint, time.monotonic() + self._ttl_seconds, state)
            while len(self._pending) > self._maximum:
                self._pending.popitem(last=False)
        return token

    def consume(self, token: str, fingerprint: str) -> Any | None:
        with self._lock:
            stored = self._pending.pop(token, None)
        if stored is None or time.monotonic() >= stored[1] or not secrets.compare_digest(stored[0], fingerprint):
            return None
        return stored[2]
