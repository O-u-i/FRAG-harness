from __future__ import annotations

import secrets
from collections import OrderedDict
from threading import Lock


class ApprovalRegistry:
    """Short-lived, single-use approval for an exact outbound fingerprint."""

    def __init__(self, maximum: int = 128):
        self._maximum = maximum
        self._pending: OrderedDict[str, str] = OrderedDict()
        self._lock = Lock()

    def issue(self, fingerprint: str) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._pending[token] = fingerprint
            while len(self._pending) > self._maximum:
                self._pending.popitem(last=False)
        return token

    def consume(self, token: str, fingerprint: str) -> bool:
        with self._lock:
            stored = self._pending.pop(token, None)
        return stored is not None and secrets.compare_digest(stored, fingerprint)
