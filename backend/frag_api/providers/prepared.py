"""Prepare the complete Responses request before approval, without credentials."""
from __future__ import annotations

import json
from urllib.parse import urlsplit

from pydantic import BaseModel

from frag_api.errors import RagFingerprintError, RagNotReadyError, RequestBudgetError
from frag_api.request_spec import canonical_json, estimated_tokens, fingerprint
from frag_api.schemas.governance import HOST_VERSION, POLICY_VERSION, REDACTION_VERSION, PreparedCall


def stage_route(settings) -> dict:
    if not settings.model or not 0 < settings.timeout_seconds <= 120:
        raise RagNotReadyError()
    if settings.provider == "fake":
        endpoint, transport = "fake://local/responses", "fake"
    else:
        base = settings.base_url or "https://api.openai.com/v1/"
        parts = urlsplit(base)
        if (parts.scheme not in {"http", "https"} or not parts.hostname or parts.username
                or parts.password or parts.query or parts.fragment or any(char.isspace() for char in base)):
            raise RagNotReadyError()
        endpoint, transport = base.rstrip("/") + "/responses", "responses-v1"
    return {"provider": settings.provider, "model": settings.model, "endpoint": endpoint,
            "transport": transport, "timeoutSeconds": float(settings.timeout_seconds), "maxRetries": 0}


def prepare_call(*, settings, purpose: str, instructions: str, payload: dict,
                 output_model: type[BaseModel], max_output_tokens: int, binding: dict) -> PreparedCall:
    route = stage_route(settings)
    body = {"model": settings.model, "instructions": instructions,
            "input": canonical_json(payload), "max_output_tokens": max_output_tokens,
            "store": False, "tools": []}
    if settings.provider == "openai":
        # These output models require every field and forbid extra fields, including $defs.
        body["text"] = {"format": {"type": "json_schema", "name": output_model.__name__,
                                  "schema": output_model.model_json_schema(by_alias=True), "strict": True}}
    full_binding = {**binding, "hostVersion": HOST_VERSION, "policyVersion": POLICY_VERSION,
                    "redactionVersion": REDACTION_VERSION, "promptVersion": f"{purpose}-v2",
                    "outputContract": {"name": output_model.__name__, "version": 1,
                                       "schemaHash": fingerprint(output_model.model_json_schema(by_alias=True))},
                    "memoryVersions": binding.get("memoryVersions", []), "toolVersions": []}
    estimate = estimated_tokens(body)
    if estimate > 6000 * 75 // 100:
        raise RequestBudgetError()
    spec = {**route, "schemaVersion": 1, "purpose": purpose, "body": canonical_json(body),
            "binding": canonical_json(full_binding), "estimatedInputTokens": estimate,
            "inputBudget": 6000, "reservedPercent": 25, "runTokenLimit": 30_000}
    return PreparedCall(**spec, fingerprint=fingerprint(spec))


def verify_prepared(call: PreparedCall, settings) -> None:
    spec = call.model_dump(by_alias=True, exclude={"fingerprint"})
    if fingerprint(spec) != call.fingerprint:
        raise RagFingerprintError()
    route = stage_route(settings)
    if any(spec[key] != value for key, value in route.items()):
        raise RagFingerprintError()
    body = call.request_body()
    if (body.get("model") != call.model or body.get("store") is not False
            or estimated_tokens(body) != call.estimated_input_tokens
            or call.estimated_input_tokens > call.input_budget * (100 - call.reserved_percent) // 100):
        raise RagFingerprintError()


def output_model_for(call: PreparedCall) -> type[BaseModel]:
    from frag_api.schemas.rag import RagContextCompression, RagGroundedAnswer
    models = {"context": RagContextCompression, "inference": RagGroundedAnswer}
    output_model = models.get(call.purpose)
    if output_model is None:
        raise RagFingerprintError()
    contract = call.request_binding().get("outputContract", {})
    if contract.get("schemaHash") != fingerprint(output_model.model_json_schema(by_alias=True)):
        raise RagFingerprintError()
    return output_model


def strict_json(text: str):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON field.")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=pairs, parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()))
