import json
import sys

import pytest
from frag_api.errors import PolicyRejectedError, RequestBudgetError
from frag_api.schemas.common import ApiModel, ProviderUsage
from frag_api.schemas.governance import CLIDefinition, LoopDefinition, SourceBinding, SourceIdentity, ToolDefinition
from frag_api.services import model_preview
from frag_api.services.runtime_policy import HostPolicy, RunBudget
from frag_api.services.runtime_registry import CLIRegistry, LoopRegistry, ToolRegistry
from test_harness import selection


class ReadInput(ApiModel):
    locator: str


class ReadOutput(ApiModel):
    text: str


def tool_definition(**changes):
    return ToolDefinition(name="kb.read", version="1.0.0", inputSchema=json.dumps(ReadInput.model_json_schema(by_alias=True)),
                          outputSchema=json.dumps(ReadOutput.model_json_schema(by_alias=True)), readOnly=True,
                          sourceKinds=("local_file", "synthetic"), carrier="native", carrierId="selected-kb", **changes)


def test_registered_tools_do_not_grant_scope_workspace_or_permission():
    definition = tool_definition()
    identity = SourceIdentity(kind="local_file", namespace="selected-root", resourceId="selected-doc")
    selected = (SourceBinding(identity=identity, revision="rev1", parserVersion="snapshot-v2",
                              locatorIds=("section-1",), evidenceIds=("evidence-1",)),)
    assert HostPolicy.require_tool(definition, frozenset({"kb.read"}), selected, identity, "rev1", ("section-1",)) == selected[0]
    forbidden = [
        (frozenset(), identity, "rev1", ("section-1",)),
        (frozenset({"kb.read"}), identity, "changed-revision", ("section-1",)),
        (frozenset({"kb.read"}), identity, "rev1", ("section-2",)),
        (frozenset({"kb.read"}), identity.model_copy(update={"resource_id": "other-doc"}), "rev1", ("section-1",)),
        (frozenset({"kb.read"}), identity.model_copy(update={"namespace": "other-root"}), "rev1", ("section-1",)),
        (frozenset({"kb.read"}), SourceIdentity(kind="fc_record", namespace="finance-core", resourceId="record-1", workspaceId="other"), "rev1", ("section-1",)),
    ]
    for allowed, source, revision, locators in forbidden:
        with pytest.raises(PolicyRejectedError):
            HostPolicy.require_tool(definition, allowed, selected, source, revision, locators)


def test_registration_requires_executable_and_matching_schema_bindings(tmp_path):
    registry = ToolRegistry()
    definition = tool_definition()
    with pytest.raises(ValueError):
        registry.register(definition, input_model=ReadInput, output_model=ReadOutput, execute=None)
    with pytest.raises(ValueError):
        registry.register(definition, input_model=ReadOutput, output_model=ReadOutput, execute=lambda value: value)
    registry.register(definition, input_model=ReadInput, output_model=ReadOutput,
                      execute=lambda value: ReadOutput(text=f"Synthetic {value.locator}"))
    with pytest.raises(ValueError):
        registry.register(definition, input_model=ReadInput, output_model=ReadOutput, execute=lambda value: value)
    with pytest.raises(PolicyRejectedError):
        registry.get("unknown.read")
    assert registry.get("kb.read").execute(ReadInput(locator="section-1")).text == "Synthetic section-1"
    cli_definition = CLIDefinition(name="selected-reader", version="1.0.0", executable=sys.executable,
                                  subcommand=("-m", "selected_reader"), workingDirectory=str(tmp_path),
                                  inputSchema=definition.input_schema, outputSchema=definition.output_schema)
    cli = CLIRegistry()
    with pytest.raises(ValueError):
        cli.register(cli_definition, None)
    cli.register(cli_definition, lambda value: {"text": value["locator"]})
    cli_tool = definition.model_copy(update={"name": "kb.cli-read", "carrier": "cli", "carrier_id": "selected-reader"})
    with pytest.raises(ValueError):
        registry.register(cli_tool, input_model=ReadInput, output_model=ReadOutput, execute=lambda value: value)
    registry.register(cli_tool, input_model=ReadInput, output_model=ReadOutput, execute=lambda value: value, cli_registry=cli)


def test_fixed_and_research_runners_have_distinct_executable_interfaces(client):
    catalog = client.get("/api/harness/capabilities").json()
    assert [loop["name"] for loop in catalog["loops"]] == ["fixed", "research"]
    assert {tool["name"] for tool in catalog["tools"]} == {"kb.search", "kb.read"}
    assert {cli["name"] for cli in catalog["cli"]} == {"kb.read.cli", "frag.host"}
    assert catalog["planned"] == []
    loops = LoopRegistry()
    with pytest.raises(ValueError):
        loops.register(LoopDefinition(name="research", version="1.0.0", stages=("research", "context", "inference")), object())
    research = client.app.state.harness_service.flow.loops.get("research").runner
    assert all(callable(getattr(research, name)) for name in ("start", "preview", "execute"))
    with pytest.raises(ValueError):
        loops.register(LoopDefinition(name="fixed", version="1.0.0", stages=("context", "inference")), research)


def test_complete_input_budget_includes_schema_and_instructions(client, monkeypatch):
    body = selection(client)
    old = model_preview.context_input
    monkeypatch.setattr(model_preview, "context_input", lambda evidence: ("Synthetic instruction " * 1500, old(evidence)[1]))
    result = client.post("/api/harness/preview", json=body)
    assert result.status_code == 422 and result.json()["error"]["code"] == "REQUEST_BUDGET_EXCEEDED"


def test_inference_budget_is_checked_before_second_approval(client, monkeypatch):
    from frag_api.services import governed_flow
    body = selection(client)
    preview = client.post("/api/harness/preview", json=body).json()
    old = governed_flow.inference_input
    monkeypatch.setattr(governed_flow, "inference_input", lambda *args: ("Synthetic inference " * 1500, old(*args)[1]))
    result = client.post("/api/harness/run", json={**body, "contextFingerprint": preview["contextFingerprint"],
        "approvalToken": preview["approvalToken"], "approved": True})
    assert result.status_code == 422 and result.json()["error"]["code"] == "REQUEST_BUDGET_EXCEEDED"


def test_cumulative_run_reservation_and_unknown_usage_do_not_reset_budget(client):
    from frag_api.schemas.harness import HarnessRequest
    call = client.app.state.harness_service.preview(HarnessRequest.model_validate(selection(client))).prepared_call
    reservation = call.estimated_input_tokens + call.request_body()["max_output_tokens"]
    budget = RunBudget(limit=reservation * 2 - 1)
    budget.reserve(call)
    charged = budget.charge(call, ProviderUsage())
    assert charged.consumed == reservation
    with pytest.raises(RequestBudgetError):
        charged.reserve(call)
    with pytest.raises(RequestBudgetError):
        RunBudget(limit=reservation).charge(call, ProviderUsage(inputTokens=reservation + 1, outputTokens=0))
