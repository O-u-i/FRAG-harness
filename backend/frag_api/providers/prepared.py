"""Prepare the complete Responses request before approval, without credentials."""
from __future__ import annotations

from urllib.parse import urlsplit

from pydantic import BaseModel

from frag_api.errors import RagFingerprintError, RagNotReadyError, RequestBudgetError
from frag_api.request_spec import canonical_json, estimated_tokens, fingerprint
from frag_api.schemas.governance import HOST_VERSION, POLICY_VERSION, REDACTION_VERSION, PreparedCall
from frag_api.providers.pi_integrity import adapter_binding

MEMORY_BACKGROUND_INSTRUCTIONS = (
    "\nReviewed memory is background, not current evidence or permission. "
    "Do not cite memory as evidence; cite only the current allowed evidence IDs."
)


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
    if getattr(settings, "adapter", "native") == "pi":
        from frag_api.providers.pi_process import configured_endpoint, supported_model
        if settings.provider != "openai" or not supported_model(settings.model):
            raise RagNotReadyError()
        endpoint = configured_endpoint(settings.base_url)
        transport = "pi-responses-v1"
    return {"provider": settings.provider, "model": settings.model, "endpoint": endpoint,
            "transport": transport, "timeoutSeconds": float(settings.timeout_seconds), "maxRetries": 0}


def prepare_call(*, settings, purpose: str, instructions: str, payload: dict,
                 output_model: type[BaseModel], max_output_tokens: int, binding: dict,
                 wire_overrides: dict | None = None) -> PreparedCall:
    route = stage_route(settings)
    if payload.get("memory"):
        instructions += MEMORY_BACKGROUND_INSTRUCTIONS
    body = {"model": settings.model, "instructions": instructions,
            "input": canonical_json(payload), "max_output_tokens": max_output_tokens,
            "store": False, "tools": []}
    wire_model = output_model
    if route["transport"] == "pi-responses-v1":
        body.update(stream=True, input=[{"role": "user", "content": [{"type": "input_text", "text": canonical_json(payload)}]}])
        if settings.model == "gpt-6.1-sol":
            body.update(reasoning={"effort": "low"}, include=["reasoning.encrypted_content"])
        if purpose == "research":
            from frag_api.schemas.research import ResearchFinish
            wire_model = ResearchFinish
        if wire_overrides:
            if purpose != "research" or set(wire_overrides) - {"tools", "input", "parallel_tool_calls", "tool_choice"}:
                raise RagFingerprintError()
            body.update(wire_overrides)
    elif wire_overrides:
        raise RagFingerprintError()
    if settings.provider == "openai":
        # These output models require every field and forbid extra fields, including $defs.
        body["text"] = {"format": {"type": "json_schema", "name": wire_model.__name__,
                                  "schema": wire_model.model_json_schema(by_alias=True), "strict": True}}
    full_binding = {**binding, "hostVersion": HOST_VERSION, "policyVersion": POLICY_VERSION,
                    "redactionVersion": REDACTION_VERSION, "promptVersion": f"{purpose}-v3",
                    "memoryPolicyVersion": "reviewed-background-v1",
                    "outputContract": {"name": output_model.__name__, "version": 1,
                                       "schemaHash": fingerprint(output_model.model_json_schema(by_alias=True))},
                    "memoryVersions": binding.get("memoryVersions", []), "toolVersions": binding.get("toolVersions", [])}
    if route["transport"] == "pi-responses-v1":
        full_binding.update(adapter=adapter_binding(), wireSchemaHash=fingerprint(wire_model.model_json_schema(by_alias=True)))
        if settings.model == "gpt-6.1-sol":
            full_binding["nativeReplayVersion"] = 2
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
    if call.transport == "pi-responses-v1":
        if (call.request_binding().get("adapter") != adapter_binding() or body.get("stream") is not True
                or not isinstance(body.get("input"), list) or not body["input"]
                or (call.purpose != "research" and body.get("tools") != [])):
            raise RagFingerprintError()
        binding = call.request_binding()
        if call.model == "gpt-6.1-sol":
            if (body.get("reasoning") != {"effort": "low"}
                    or body.get("include") != ["reasoning.encrypted_content"]
                    or type(binding.get("nativeReplayVersion")) is not int or binding["nativeReplayVersion"] != 2):
                raise RagFingerprintError()
        elif any(key in body for key in ("reasoning", "include")) or "nativeReplayVersion" in binding:
            raise RagFingerprintError()
        output_model_for(call)


def output_model_for(call: PreparedCall) -> type[BaseModel]:
    from frag_api.schemas.rag import RagContextCompression, RagGroundedAnswer
    from frag_api.schemas.research import ResearchDecision
    models = {"context": RagContextCompression, "inference": RagGroundedAnswer, "research": ResearchDecision}
    output_model = models.get(call.purpose)
    if output_model is None:
        raise RagFingerprintError()
    contract = call.request_binding().get("outputContract", {})
    if contract.get("schemaHash") != fingerprint(output_model.model_json_schema(by_alias=True)):
        raise RagFingerprintError()
    if call.transport == "pi-responses-v1":
        from frag_api.schemas.research import ResearchFinish
        wire_model = ResearchFinish if call.purpose == "research" else output_model
        if (call.request_binding().get("wireSchemaHash") != fingerprint(wire_model.model_json_schema(by_alias=True))
                or call.request_body().get("text", {}).get("format") != {
                    "type": "json_schema", "name": wire_model.__name__,
                    "schema": wire_model.model_json_schema(by_alias=True), "strict": True}):
            raise RagFingerprintError()
    return output_model
