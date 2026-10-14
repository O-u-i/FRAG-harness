from types import SimpleNamespace

import pytest

from frag_api.errors import PolicyRejectedError
from frag_api.repositories.tool_store import ToolStore
from frag_api.schemas.native import CompleteInput, FcInput, SourceProfile
from frag_api.services.evidence_tools import EvidenceTools, MAX_PACK_BYTES
from frag_api.request_spec import canonical_json


@pytest.fixture
def tools(tmp_path):
    records = {"monthly-review:2025-03": {"text": "Three months, adjustments and completeness warnings", "revision": "a" * 64},
        "entry:optional": {"text": "Optional detail", "revision": "b" * 64}}
    reader = SimpleNamespace(version="1.3.0", digest="c" * 64, source_revision="d" * 64,
        ensure_current=lambda: None,
        selected_scopes=lambda: {"scopes": [{"id": "sandbox", "records": [{"id": key} for key in records]}]},
        read_selected=lambda _workspace, ids: [{"label": key, **records[key]} for key in ids])
    store = ToolStore(tmp_path / "tools.sqlite3")
    store.save_profile(SourceProfile(id="finance-core", kind="fc", approved=True))
    try:
        yield EvidenceTools(store, tmp_path / "indexes", reader), records
    finally:
        store.close()


def test_required_report_is_generated_server_side_and_cannot_be_omitted(tools):
    service, _ = tools
    pack = service.fc_read(FcInput(operation="read", workspaceId="sandbox", recordIds=["entry:optional", "monthly-review:2025-03"]))
    required = pack["requiredEvidenceIds"]
    assert required == [pack["evidence"][-1]["evidenceId"]]
    with pytest.raises(PolicyRejectedError):
        service.complete(CompleteInput(runId=pack["runId"], omittedEvidenceIds=required))
    assert service.repository.get(pack["runId"]).status == "prepared"
    final = service.complete(CompleteInput(runId=pack["runId"], omittedEvidenceIds=[pack["evidence"][0]["evidenceId"]]))
    assert final["requiredEvidenceIds"] == required and len(final["evidence"]) == 1
    assert final["evidence"][0]["text"] == "Three months, adjustments and completeness warnings"


def test_byte_budget_omits_optional_items_even_when_report_is_last(tools):
    service, records = tools
    records["entry:optional"]["text"] = "x" * MAX_PACK_BYTES
    pack = service.fc_read(FcInput(operation="read", workspaceId="sandbox", recordIds=["entry:optional", "monthly-review:2025-03"]))
    assert len(canonical_json(pack).encode()) <= MAX_PACK_BYTES
    assert len(pack["evidence"]) == 1 and pack["evidence"][0]["locatorId"] == "monthly-review:2025-03"
    assert len(pack["budget"]["omittedEvidenceIds"]) == 1


def test_report_alone_too_large_is_rejected_not_delivered_empty(tools):
    service, records = tools
    records["monthly-review:2025-03"]["text"] = "x" * MAX_PACK_BYTES
    with pytest.raises(PolicyRejectedError):
        service.fc_read(FcInput(operation="read", workspaceId="sandbox", recordIds=["monthly-review:2025-03"]))
