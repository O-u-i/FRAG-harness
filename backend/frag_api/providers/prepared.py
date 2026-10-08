"""Freeze either a complete HTTP request or exact stable model API arguments."""
from urllib.parse import urlsplit, quote
from pydantic import BaseModel
from frag_api.errors import RagFingerprintError, RagNotReadyError, RequestBudgetError
from frag_api.request_spec import canonical_json, estimated_tokens, fingerprint
from frag_api.schemas.governance import HOST_VERSION, POLICY_VERSION, REDACTION_VERSION, PreparedCall

MEMORY_BACKGROUND_INSTRUCTIONS = (
    "\nReviewed memory is background, not current evidence or permission. "
    "Do not cite memory as evidence; cite only the current allowed evidence IDs."
)


def stage_route(settings):
    if not settings.model or not 0 < settings.timeout_seconds <= 120:
        raise RagNotReadyError()
    if settings.provider == "fake":
        endpoint, transport = "fake://local/responses", "fake"
    elif settings.provider == "vscode":
        if not settings.configuration_revision:
            raise RagNotReadyError()
        endpoint, transport = "vscode-lm://models/" + quote(settings.model, safe=""), "vscode-lm-v1"
    else:
        base = settings.base_url or "https://api.openai.com/v1/"
        parts = urlsplit(base)
        if (parts.scheme not in {"http", "https"} or not parts.hostname or parts.username
                or parts.password or parts.query or parts.fragment or any(char.isspace() for char in base)):
            raise RagNotReadyError()
        endpoint, transport = base.rstrip("/") + "/responses", "responses-v1"
    route = {"provider": settings.provider, "model": settings.model, "endpoint": endpoint,
             "transport": transport, "timeoutSeconds": float(settings.timeout_seconds), "maxRetries": 0}
    return route


def prepare_call(*, settings, purpose, instructions, payload, output_model: type[BaseModel],
                 max_output_tokens, binding):
    route = stage_route(settings)
    if payload.get("memory"):
        instructions += MEMORY_BACKGROUND_INSTRUCTIONS
    if settings.provider == "vscode":
        instructions += "\nReturn only valid JSON conforming to the supplied outputSchema. No Markdown wrappers."
        body = {"messages": [{"role": "user", "content": instructions},
                             {"role": "user", "content": canonical_json(payload)}],
                "options": {"modelOptions": {"max_tokens": max_output_tokens}}}
    else:
        body = {"model": settings.model, "instructions": instructions, "input": canonical_json(payload),
                "max_output_tokens": max_output_tokens, "store": False, "tools": []}
        if settings.provider == "openai":
            body["text"] = {"format": {"type": "json_schema", "name": output_model.__name__,
                           "schema": output_model.model_json_schema(by_alias=True), "strict": True}}
    full_binding = {**binding, "hostVersion": HOST_VERSION, "policyVersion": POLICY_VERSION,
        "redactionVersion": REDACTION_VERSION, "promptVersion": f"{purpose}-v3",
        "memoryPolicyVersion": "reviewed-background-v1",
        "outputContract": {"name": output_model.__name__, "version": 1,
                           "schemaHash": fingerprint(output_model.model_json_schema(by_alias=True))},
        "memoryVersions": binding.get("memoryVersions", []), "toolVersions": binding.get("toolVersions", [])}
    budget = 6000
    if settings.provider == "vscode":
        full_binding.update(modelConfigurationRevision=settings.configuration_revision,
            modelLabel=settings.model_name, modelVendor=settings.model_vendor,
            configuredEffort=settings.reasoning_effort, approvalBoundary="language_model_api",
            providerHttpBody="unknown", providerInternalRetries="unknown")
        budget = min(budget, settings.max_input_tokens)
    estimate = estimated_tokens(body)
    if estimate > budget * 75 // 100:
        raise RequestBudgetError()
    spec = {**route, "schemaVersion": 2 if settings.provider == "vscode" else 1, "purpose": purpose,
            "body": canonical_json(body), "binding": canonical_json(full_binding),
            "estimatedInputTokens": estimate, "inputBudget": budget, "reservedPercent": 25, "runTokenLimit": 30000}
    return PreparedCall(**spec, fingerprint=fingerprint(spec))


def verify_prepared(call, settings):
    if call.transport == "pi-responses-v1":
        raise RagNotReadyError()  # Historical requests cannot be routed to another provider.
    spec = call.model_dump(by_alias=True, exclude={"fingerprint"})
    if fingerprint(spec) != call.fingerprint or any(spec[key] != value for key,value in stage_route(settings).items()):
        raise RagFingerprintError()
    body = call.request_body()
    if estimated_tokens(body) != call.estimated_input_tokens or call.estimated_input_tokens > call.input_budget * (100-call.reserved_percent)//100:
        raise RagFingerprintError()
    if call.transport == "vscode-lm-v1":
        binding = call.request_binding()
        if (call.schema_version != 2 or binding.get("modelConfigurationRevision") != settings.configuration_revision
                or binding.get("configuredEffort") != settings.reasoning_effort
                or binding.get("approvalBoundary") != "language_model_api"
                or binding.get("providerHttpBody") != "unknown" or binding.get("providerInternalRetries") != "unknown"
                or set(body) != {"messages", "options"} or len(body["messages"]) != 2
                or any(set(row) != {"role", "content"} or row["role"] != "user" or not isinstance(row["content"],str) for row in body["messages"])
                or set(body["options"]) != {"modelOptions"} or set(body["options"]["modelOptions"]) != {"max_tokens"}
                or type(call.output_limit) is not int or call.output_limit <= 0):
            raise RagFingerprintError()
    elif body.get("model") != call.model or body.get("store") is not False:
        raise RagFingerprintError()
    output_model_for(call)


def output_model_for(call):
    from frag_api.schemas.rag import RagContextCompression, RagGroundedAnswer
    from frag_api.schemas.research import ResearchDecision
    model = {"context": RagContextCompression, "inference": RagGroundedAnswer, "research": ResearchDecision}.get(call.purpose)
    if model is None or call.request_binding().get("outputContract", {}).get("schemaHash") != fingerprint(model.model_json_schema(by_alias=True)):
        raise RagFingerprintError()
    return model
