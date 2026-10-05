"""Read explicitly selected local files through FRAG's existing snapshot parser."""
import os
import hashlib
from pathlib import Path

from fastapi import APIRouter
from frag_api.services import context_source_service


def create_router():
    return APIRouter()


def _sources():
    root = os.environ.get("FRAG_KB_SOURCE_ROOT") or Path(context_source_service.__file__).resolve().parents[3] / "local-sources"
    return context_source_service.ContextSourceService(root)


def source_revision():
    return hashlib.sha256(str(_sources().root).encode("utf-8")).hexdigest()


def list_scopes(scope_id=None):
    source = _sources()
    if scope_id is None:
        return {"scopes": [{"id": item.relative_path, "label": item.relative_path, "records": []}
                           for item in source.list_files() if item.status == "ready"]}
    selected = source.inspect(scope_id)
    return {"scopes": [{"id": selected.source.relative_path, "label": selected.source.relative_path,
                        "records": [{"id": item.id, "label": item.label} for item in selected.locators]}]}


def read_evidence_request(request):
    if (not isinstance(request, dict) or set(request) != {"protocolVersion", "pluginId", "scopeId", "recordIds"}
            or type(request["protocolVersion"]) is not int or request["protocolVersion"] != 2 or request["pluginId"] != "kb"
            or not isinstance(request["scopeId"], str) or not isinstance(request["recordIds"], list)):
        raise ValueError("Invalid selected KB request.")
    ids = request["recordIds"]
    if not 1 <= len(ids) <= 10 or any(not isinstance(item, str) or not item for item in ids) or len(set(ids)) != len(ids):
        raise ValueError("Select distinct KB locators.")
    parsed = _sources().parse(request["scopeId"])
    sections = {item.locator.id: item for item in parsed.sections}
    if not set(ids).issubset(sections):
        raise ValueError("Selected KB locator is unavailable.")
    return {"protocolVersion": 2, "pluginId": "kb", "scopeId": request["scopeId"], "records": [
        {"recordId": locator, "label": sections[locator].locator.label, "text": sections[locator].text,
         "revision": parsed.source.sha256} for locator in ids]}
