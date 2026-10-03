"""Canonical, credential-free JSON encoding shared by request preparation and checks."""
import hashlib
import json


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def estimated_tokens(value: object) -> int:
    # Includes the complete JSON request; an estimate, not a model tokenizer count.
    return max(1, (len(canonical_json(value).encode("utf-8")) + 2) // 3)
