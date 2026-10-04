"""Validate bounded raw Responses items without filling defaults or changing values."""
from frag_api.request_spec import canonical_json

SOL_MODEL = "gpt-6.1-sol"
ITEM_TYPES = frozenset({"reasoning", "message", "function_call"})
TOOL_NAMES = frozenset({"kb_read", "kb_search"})


def shape(value, required, optional=()):
    if not isinstance(value, dict) or not set(required).issubset(value) or set(value) - set(required) - set(optional):
        raise ValueError("Unexpected raw item shape")


def identifier(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 256:
        raise ValueError("Invalid raw item identifier")


def validate_output_items(items, *, require_ciphertext=False):
    if (not isinstance(items, list) or not 1 <= len(items) <= 64
            or len(canonical_json(items).encode("utf-8")) > 256 * 1024):
        raise ValueError("Raw items exceed bounds")
    ids, calls = set(), set()
    for item in items:
        if not isinstance(item, dict) or item.get("type") not in ITEM_TYPES:
            raise ValueError("Unsupported raw output item")
        identifier(item.get("id"))
        if item["id"] in ids:
            raise ValueError("Duplicate raw item identifier")
        ids.add(item["id"])
        if item["type"] == "reasoning":
            shape(item, {"type", "id", "summary"}, {"status", "encrypted_content", "content"})
            if "status" in item and item["status"] != "completed":
                raise ValueError("Incomplete reasoning item")
            encrypted = item.get("encrypted_content")
            if (encrypted is not None and not isinstance(encrypted, str)) or (require_ciphertext and not encrypted):
                raise ValueError("Missing completed reasoning ciphertext")
            for key, kind in (("summary", "summary_text"), ("content", "reasoning_text")):
                if key not in item:
                    continue
                if not isinstance(item[key], list):
                    raise ValueError("Invalid reasoning content")
                for part in item[key]:
                    shape(part, {"type", "text"})
                    if part["type"] != kind or not isinstance(part["text"], str):
                        raise ValueError("Invalid reasoning content")
        elif item["type"] == "message":
            shape(item, {"type", "id", "role", "status", "content"}, {"phase"})
            if (item["role"] != "assistant" or item["status"] != "completed"
                    or item.get("phase") not in (None, "commentary", "final_answer")
                    or not isinstance(item["content"], list) or not item["content"]):
                raise ValueError("Invalid assistant message")
            for part in item["content"]:
                shape(part, {"type", "text", "annotations"}, {"logprobs"})
                if (part["type"] != "output_text" or not isinstance(part["text"], str)
                        or part["annotations"] != [] or ("logprobs" in part and part["logprobs"] != [])):
                    raise ValueError("Unsupported assistant content")
        else:
            shape(item, {"type", "id", "call_id", "name", "arguments"}, {"status"})
            identifier(item["call_id"])
            if (("status" in item and item["status"] != "completed") or item["name"] not in TOOL_NAMES
                    or not isinstance(item["arguments"], str) or not 1 <= len(item["arguments"].encode("utf-8")) <= 16 * 1024
                    or item["call_id"] in calls):
                raise ValueError("Invalid completed function call")
            calls.add(item["call_id"])
    return items


def output_content(items):
    validate_output_items(items)
    text, calls = "", []
    for item in items:
        if item["type"] == "function_call":
            calls.append({"callId": item["call_id"], "itemId": item["id"], "name": item["name"],
                          "argumentsText": item["arguments"]})
        elif item["type"] == "message" and item.get("phase") != "commentary":
            text += "".join(part["text"] for part in item["content"])
    if calls:
        validate_output_items(items, require_ciphertext=True)
        if text.strip():
            raise ValueError("Tool proposal mixed with a final answer")
    elif not text.strip():
        raise ValueError("Missing final structured text")
    return text, calls


def require_sol_profile(call):
    body = call.request_body()
    if (call.model != SOL_MODEL or call.transport != "pi-responses-v1"
            or body.get("reasoning") != {"effort": "low"}
            or body.get("include") != ["reasoning.encrypted_content"]
            or call.request_binding().get("nativeReplayVersion") != 2):
        raise ValueError("Unbound stateless Sol profile")


def validate_sol_response(call, response):
    require_sol_profile(call)
    text, calls = output_content(response["outputItems"])
    if text != response["outputText"] or calls != response["calls"]:
        raise ValueError("Raw output and normalized fields disagree")
    return text, calls
