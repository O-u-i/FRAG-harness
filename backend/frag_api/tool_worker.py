"""Isolated stdlib-only selected-snapshot read worker. No file or network access."""
from __future__ import annotations

import json
import sys

INPUT_BYTES = 128 * 1024
_ROW_FIELDS = {"evidenceId", "documentId", "sourceId", "locatorId", "locatorLabel", "text"}


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate key")
        result[key] = value
    return result


def nonfinite(_):
    raise ValueError("Nonfinite number")


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def unique_ids(value):
    if not isinstance(value, list) or not value or not all(nonempty(item) for item in value) or len(set(value)) != len(value):
        raise ValueError("Invalid identifiers")
    return value


def read_selected(payload):
    if not isinstance(payload, dict) or set(payload) != {"callId", "arguments", "evidence"} or not nonempty(payload["callId"]):
        raise ValueError("Invalid envelope")
    arguments = payload["arguments"]
    if not isinstance(arguments, dict) or set(arguments) != {"identity", "revision", "locatorIds", "evidenceIds"}:
        raise ValueError("Invalid arguments")
    identity = arguments["identity"]
    if (not isinstance(identity, dict) or set(identity) - {"kind", "namespace", "resourceId", "workspaceId"}
            or set(identity) < {"kind", "namespace", "resourceId"}
            or identity.get("kind") not in {"local_file", "synthetic"}
            or not nonempty(identity.get("namespace")) or not nonempty(identity.get("resourceId"))
            or identity.get("workspaceId") is not None or not nonempty(arguments["revision"])):
        raise ValueError("Invalid source identity")
    locators, evidence_ids = unique_ids(arguments["locatorIds"]), unique_ids(arguments["evidenceIds"])
    rows = payload["evidence"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("Missing selected evidence")
    by_id = {}
    for row in rows:
        if (not isinstance(row, dict) or set(row) != _ROW_FIELDS
                or not all(nonempty(value) for value in row.values()) or row["evidenceId"] in by_id):
            raise ValueError("Invalid evidence")
        by_id[row["evidenceId"]] = row
    if any(evidence_id not in by_id for evidence_id in evidence_ids):
        raise ValueError("Evidence outside selected snapshot")
    selected = [by_id[evidence_id] for evidence_id in evidence_ids]
    if not {row["locatorId"] for row in selected}.issubset(locators):
        raise ValueError("Locator selection mismatch")
    return {"callId": payload["callId"], "evidence": selected, "missingInformation": []}


def main():
    try:
        if sys.argv[1:] != ["read"]:
            raise ValueError("Unknown command")
        data = sys.stdin.buffer.read(INPUT_BYTES + 1)
        if len(data) > INPUT_BYTES:
            raise ValueError("Input limit")
        payload = json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=nonfinite)
        response = read_selected(payload)
        encoded = json.dumps(response, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        sys.stdout.buffer.write(encoded)
        sys.stdout.buffer.flush()
        return 0
    except (ValueError, TypeError, UnicodeError, RecursionError, OSError):
        sys.stderr.write("Selected read request rejected.\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
