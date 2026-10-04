"""Normalize complete Pi native calls; never dispatch tools or accept partial JSON."""
from copy import deepcopy
import hashlib

from pydantic import ValidationError

from frag_api.errors import RagOutputError
from frag_api.providers.prepared import strict_json
from frag_api.request_spec import canonical_json, fingerprint
from frag_api.schemas.research import NativeResearchReplay, NativeResearchReplayV2, ResearchDecision, ResearchFinish
from frag_api.schemas.tools import ReadArguments, SearchArguments
from frag_api.providers.response_items import SOL_MODEL, output_content, require_sol_profile, validate_sol_response

NATIVE_NAMES = {"kb_read": "kb.read", "kb_search": "kb.search"}


def host_call_id(call, raw_id, item_id):
    return "pi_" + hashlib.sha256(canonical_json([call.fingerprint, raw_id, item_id]).encode()).hexdigest()


def required_shape(schema, value, root):
    """Check strict wire-required properties, including nullable Workspace and search limit."""
    if "$ref" in schema:
        prefix = "#/$defs/"
        if not schema["$ref"].startswith(prefix):
            raise ValueError()
        return required_shape(root["$defs"][schema["$ref"][len(prefix):]], value, root)
    if "anyOf" in schema:
        for option in schema["anyOf"]:
            try:
                required_shape(option, value, root)
                return
            except (ValueError, TypeError):
                pass
        raise ValueError()
    kind = schema.get("type")
    if kind == "null" and value is not None:
        raise ValueError()
    if kind == "object":
        properties = schema.get("properties", {})
        if (not isinstance(value, dict) or set(value) != set(properties)
                or schema.get("additionalProperties") is not False
                or set(schema.get("required", [])) != set(properties)):
            raise ValueError()
        for key, child in properties.items():
            required_shape(child, value[key], root)
    if kind == "array":
        if not isinstance(value, list):
            raise ValueError()
        for child in value:
            required_shape(schema["items"], child, root)
    if kind == "string" and not isinstance(value, str):
        raise ValueError()
    if kind == "integer" and type(value) is not int:
        raise ValueError()


def normalized_calls(call, replay):
    definitions = call.request_body().get("tools", [])
    result = []
    for native in replay.calls:
        entries = [row for row in definitions if row.get("name") == native.name]
        if len(entries) != 1 or entries[0].get("type") != "function" or entries[0].get("strict") is not True:
            raise ValueError()
        arguments = strict_json(native.arguments_text)
        schema = entries[0]["parameters"]
        required_shape(schema, arguments, schema)
        model = ReadArguments if native.name == "kb_read" else SearchArguments
        model.model_validate_json(canonical_json(arguments), strict=True)
        expected = host_call_id(call, native.call_id, native.item_id)
        if native.host_call_id != expected:
            raise ValueError()
        result.append({"callId": expected, "name": NATIVE_NAMES[native.name], "arguments": arguments})
    return result


def validate_native_replay(call, decision, replay, digest=None):
    try:
        native = call.transport == "pi-responses-v1" and call.purpose == "research"
        if native and call.model == SOL_MODEL:
            require_sol_profile(call)
            typed = NativeResearchReplayV2.model_validate(replay)
            data = typed.model_dump(by_alias=True)
            if digest is not None and fingerprint(data) != digest:
                raise ValueError()
            text, raw = output_content(typed.output_items)
            calls = [{key: value for key, value in item.model_dump(by_alias=True).items() if key != "hostCallId"}
                     for item in typed.calls]
            if raw != calls or normalized_calls(call, typed) != [item.model_dump(by_alias=True) for item in decision.tool_calls]:
                raise ValueError()
            if decision.action == "finish":
                finish = ResearchFinish.model_validate(strict_json(text))
                if typed.calls or ResearchDecision(**finish.model_dump(by_alias=True), toolCalls=[]) != decision:
                    raise ValueError()
            elif not typed.calls or text.strip():
                raise ValueError()
            return typed
        if not native or decision.action == "finish":
            if replay is not None or digest is not None:
                raise ValueError()
            return None
        typed = NativeResearchReplay.model_validate(replay)
        data = typed.model_dump(by_alias=True)
        if digest is not None and fingerprint(data) != digest:
            raise ValueError()
        if normalized_calls(call, typed) != [item.model_dump(by_alias=True) for item in decision.tool_calls]:
            raise ValueError()
        return typed
    except (ValueError, TypeError, KeyError, ValidationError) as error:
        raise RagOutputError() from error


def normalize_pi_research(call, response):
    try:
        if (not isinstance(response, dict) or call.transport != "pi-responses-v1"
                or call.purpose != "research" or response.get("status") != "completed"):
            raise ValueError()
        raw = response["calls"]
        text = response["outputText"]
        if not isinstance(raw, list) or not isinstance(text, str):
            raise ValueError()
        if call.model == SOL_MODEL:
            text, raw = validate_sol_response(call, response)
            calls = [{**entry, "hostCallId": host_call_id(call, entry["callId"], entry["itemId"])} for entry in raw]
            replay = NativeResearchReplayV2(version=2, calls=calls, outputItems=deepcopy(response["outputItems"]))
            history = call.request_body()["input"]
            if not isinstance(history, list) or any(not isinstance(item, dict) for item in history):
                raise ValueError()
            prior_ids = {item["id"] for item in history if item.get("type") in ("function_call", "reasoning", "message") and "id" in item}
            prior_calls = {item["call_id"] for item in history if item.get("type") == "function_call"}
            if (any(item["id"] in prior_ids for item in replay.output_items)
                    or any(entry.call_id in prior_calls for entry in replay.calls)):
                raise ValueError()
            if raw:
                decision = ResearchDecision(action="continue", toolCalls=normalized_calls(call, replay), evidenceIds=[], missingInformation=[])
            else:
                finish = ResearchFinish.model_validate(strict_json(text))
                decision = ResearchDecision(**finish.model_dump(by_alias=True), toolCalls=[])
            validate_native_replay(call, decision, replay)
            return decision, replay.model_dump(by_alias=True)
        if not raw:
            finish = ResearchFinish.model_validate(strict_json(text))
            return ResearchDecision(**finish.model_dump(by_alias=True), toolCalls=[]), None
        if text.strip():
            raise ValueError()
        if any(not isinstance(entry, dict) or set(entry) != {"callId", "itemId", "name", "argumentsText"}
               for entry in raw):
            raise ValueError()
        calls = [{**entry, "hostCallId": host_call_id(call, entry["callId"], entry["itemId"])} for entry in raw]
        replay = NativeResearchReplay(version=1, calls=calls)
        history = call.request_body()["input"]
        if not isinstance(history, list) or any(not isinstance(item, dict) for item in history):
            raise ValueError()
        prior = [item for item in history if item.get("type") == "function_call"]
        if (any(entry.call_id in {item["call_id"] for item in prior} for entry in replay.calls)
                or any(entry.item_id in {item["id"] for item in prior} for entry in replay.calls)):
            raise ValueError()
        decision = ResearchDecision(action="continue", toolCalls=normalized_calls(call, replay), evidenceIds=[], missingInformation=[])
        return decision, replay.model_dump(by_alias=True)
    except (ValueError, TypeError, KeyError, ValidationError) as error:
        raise RagOutputError() from error
