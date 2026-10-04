"""Canonical, credential-free JSON encoding shared by request preparation and checks."""
import hashlib
import json
import math


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def estimated_tokens(value: object) -> int:
    # Includes the complete JSON request; an estimate, not a model tokenizer count.
    return max(1, (len(canonical_json(value).encode("utf-8")) + 2) // 3)


def strict_json(value: str | bytes | bytearray):
    """Reject ambiguous objects and nonfinite numbers at JSON input boundaries."""
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError("Duplicate JSON field.")
            result[key] = item
        return result

    def nonfinite(_):
        raise ValueError("Nonfinite JSON number.")

    def finite_float(text):
        number = float(text)
        if not math.isfinite(number):
            raise ValueError("Nonfinite JSON number.")
        return number

    return json.loads(value, object_pairs_hook=pairs, parse_constant=nonfinite, parse_float=finite_float)
