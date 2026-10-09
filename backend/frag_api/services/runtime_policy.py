"""Deterministic outbound evidence redaction; no model-stage policy."""
import re

SECRET = re.compile(r'''(?i)(api[_ -]?key|password|secret|access[_ -]?token|authorization)["']?\s*[:=]\s*(?:bearer\s+)?(?:"[^"\r\n]*"|'[^'\r\n]*'|\S+)''')
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")


def redact(text: str, secrets: tuple[str, ...] = ()) -> str:
    value = EMAIL.sub("[REDACTED_EMAIL]", KEY.sub("[REDACTED_SECRET]", SECRET.sub("[REDACTED_SECRET]", text)))
    for secret in secrets:
        if secret:
            value = value.replace(secret, "[REDACTED_SECRET]")
    return value


def redact_value(value, secrets: tuple[str, ...] = ()):
    if isinstance(value, str):
        return redact(value, secrets)
    if isinstance(value, dict):
        return {key: "[REDACTED_SECRET]" if re.fullmatch(r"(?i)(api[_ -]?key|password|secret|access[_ -]?token|authorization|read[_ -]?token)", key)
                else redact_value(item, secrets) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [redact_value(item, secrets) for item in value]
    return value
