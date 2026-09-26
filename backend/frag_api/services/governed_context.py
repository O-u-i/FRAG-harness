from __future__ import annotations

import hashlib
import json

INPUT_BUDGET = 6_000
RESERVED_PERCENT = 25
CONTEXT_OUTPUT_LIMIT = 1_500
INFERENCE_OUTPUT_LIMIT = 2_000


def estimated_tokens(value: object) -> int:
    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return max(1, (len(serialized.encode("utf-8")) + 2) // 3)


def fingerprint(value: object) -> str:
    serialized = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
