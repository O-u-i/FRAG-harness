"""Project registered tools and rebuild approved native history from durable receipts."""
from copy import deepcopy
import json

from frag_api.errors import RagFingerprintError, RagOutputError
from frag_api.providers.research_native import NATIVE_NAMES, validate_native_replay
from frag_api.request_spec import canonical_json, fingerprint


def closed_schema(value):
    if isinstance(value, list):
        return [closed_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: closed_schema(item) for key, item in value.items() if key != "default"}
    if result.get("type") == "object":
        result["additionalProperties"] = False
        result["required"] = list(result.get("properties", {}))
    return result


def projected_tools(tools):
    names = {host: native for native, host in NATIVE_NAMES.items()}
    result = []
    for definition in tools.registry.catalog():
        if definition.name not in names or not definition.read_only:
            raise RagFingerprintError()
        result.append({"type": "function", "name": names[definition.name], "strict": True,
                       "parameters": closed_schema(json.loads(definition.input_schema))})
    if {item["name"] for item in result} != set(NATIVE_NAMES):
        raise RagFingerprintError()
    return result


def validate_attempt_native(attempt, decision):
    if (fingerprint(attempt.prepared_call.model_dump(by_alias=True, exclude={"fingerprint"}))
            != attempt.prepared_call.fingerprint):
        raise RagFingerprintError()
    if attempt.native_replay is not None and attempt.native_replay_digest is None:
        raise RagFingerprintError()
    try:
        return validate_native_replay(attempt.prepared_call, decision, attempt.native_replay,
                                      attempt.native_replay_digest)
    except RagOutputError as error:
        raise RagFingerprintError() from error


def native_history(report):
    items, raw_ids, item_ids, host_ids = [], set(), set(), []
    for turn in report.research.turns:
        if turn.decision is None:
            continue
        attempt = next((item for item in report.requests if item.id == turn.attempt_id), None)
        if attempt is None:
            raise RagFingerprintError()
        replay = validate_attempt_native(attempt, turn.decision)
        if replay is None:
            if turn.decision.action != "finish":
                raise RagFingerprintError()
            continue
        proposed, observed = [], []
        if replay.version == 2:
            for item in replay.output_items:
                if item["id"] in item_ids:
                    raise RagFingerprintError()
                item_ids.add(item["id"])
        for native in replay.calls:
            if native.call_id in raw_ids or (replay.version == 1 and native.item_id in item_ids):
                raise RagFingerprintError()
            raw_ids.add(native.call_id)
            if replay.version == 1:
                item_ids.add(native.item_id)
            host_ids.append(native.host_call_id)
            tool = next((tool for tool in report.tool_calls if tool.call_id == native.host_call_id), None)
            if tool is None or tool.status not in ("completed", "failed"):
                raise RagFingerprintError()
            output = {"status": tool.status, "result": tool.result.model_dump(by_alias=True) if tool.result else None,
                      "errorCode": tool.error_code}
            proposed.append({"type": "function_call", "id": native.item_id, "call_id": native.call_id,
                             "name": native.name, "arguments": native.arguments_text, "status": "completed"})
            observed.append({"type": "function_call_output", "call_id": native.call_id, "output": canonical_json(output)})
        items.extend([*(deepcopy(replay.output_items) if replay.version == 2 else proposed), *observed])
    if host_ids != [tool.call_id for tool in report.tool_calls]:
        raise RagFingerprintError()
    return items


def prepare_native_wire(report, payload, tools):
    # Native function schemas and the actual transcript already carry these fields.
    initial = {key: value for key, value in payload.items()
               if key not in {"tools", "toolResultSchema", "outputSchema", "decisions", "observations"}}
    return {"tools": projected_tools(tools), "parallel_tool_calls": False, "tool_choice": "auto",
            "input": [{"role": "user", "content": [{"type": "input_text", "text": canonical_json(initial)}]},
                      *native_history(report)]}
