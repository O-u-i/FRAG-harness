"""Host CLI uses bounded loopback HTTP and cannot bypass stage approval."""
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
from pydantic import ValidationError

from frag_api import cli
from frag_api.cli_client import HostClient, HostCLIError, MAX_RESPONSE_BYTES, host_cli_binding, loopback_url
from frag_api.main import create_app
from frag_api.providers.llm import FakeLlmProvider, LlmSettings, LlmStageSettings
from frag_api.schemas.cli import HostCLIRequest, HostCLIResponse
from frag_api.services.context_source_service import ContextSourceService
from frag_api.services.harness_service import HarnessService
from frag_api.services.runtime_registry import CLIRegistry


class CountingProvider(FakeLlmProvider):
    def __init__(self):
        self.calls = []

    def execute_prepared(self, call):
        self.calls.append(call.purpose)
        return super().execute_prepared(call)


@pytest.fixture
def application(tmp_path, source_root):
    provider = CountingProvider()
    stage = LlmStageSettings("fake", "synthetic-cli", None, None, 120)
    harness = HarnessService(ContextSourceService(source_root), settings=LlmSettings(stage, stage),
                             context_provider=provider, inference_provider=provider)
    app = create_app(context_source_root=source_root, harness_service=harness,
                     runtime_path=tmp_path / "runtime.sqlite3", rag_index_path=tmp_path / "rag.sqlite3",
                     plugin_root=tmp_path / "absent-plugins")
    return app, provider


def source_for(client):
    inspected = client.post("/api/context-sources/files/inspect", json={"relativePath":"evidence.md"}).json()
    return {"goal":"Review the synthetic finding", "fileSelections":[{
        "relativePath":"evidence.md", "locatorIds":[inspected["locators"][0]["id"]],
        "relevanceReason":"Selected synthetic test scope"}]}


def via_api(client):
    def handler(request):
        response = client.request(request.method, request.url.path, params=request.url.params,
                                  content=request.content, headers=request.headers)
        return httpx.Response(response.status_code, content=response.content, headers=response.headers)
    return HostClient(transport=httpx.MockTransport(handler))


class Terminal(io.StringIO):
    def isatty(self):
        return True


@pytest.mark.parametrize("value", [
    "https://127.0.0.1:8787", "http://8.8.8.8", "http://localhost:8787", "http://user:secret@127.0.0.1",
    "http://127.0.0.1/api", "http://127.0.0.1?secret=value", "http://127.0.0.1#fragment", "http://127.0.0.1:0",
])
def test_rejects_noncanonical_or_nonloopback_destinations(value):
    with pytest.raises(HostCLIError, match="numeric loopback"):
        loopback_url(value)


def test_loopback_ipv6_and_default_port():
    assert loopback_url("http://[::1]:8787/") == "http://[::1]:8787"
    assert loopback_url("http://127.1.2.3") == "http://127.1.2.3:80"


@pytest.mark.parametrize("response", [
    httpx.Response(302, headers={"Location":"https://secret.example/"}),
    httpx.Response(500, json={"secret":"never-echo-this"}),
    httpx.Response(200, headers={"Content-Type":"text/html"}, content="never-echo-this"),
    httpx.Response(200, headers={"Content-Type":"application/json"}, content='{"value":1,"value":2}'),
    httpx.Response(200, headers={"Content-Type":"application/json"}, content='{"value":1e999}'),
    httpx.Response(200, headers={"Content-Type":"application/json"}, content="{"),
    httpx.Response(200, json={"error":{"message":"never-echo-this"}}),
    httpx.Response(200, json=[]),
])
def test_rejects_redirect_error_and_invalid_response_without_echo(response):
    calls = []
    client = HostClient(transport=httpx.MockTransport(lambda request: (calls.append(request), response)[1]))
    with pytest.raises(HostCLIError) as caught:
        client.operate(HostCLIRequest(command="health"))
    assert len(calls) == 1
    assert "never-echo-this" not in str(caught.value)
    assert "secret.example" not in str(caught.value)


def test_transport_has_no_proxy_or_redirect_authority_and_limits(monkeypatch):
    actual_client = httpx.Client
    options = []
    def make_client(**kwargs):
        options.append(kwargs)
        return actual_client(**kwargs)
    monkeypatch.setattr(httpx, "Client", make_client)
    response = httpx.Response(200, headers={"Content-Type":"application/json"},
                              content=b'{"value":"' + b"x" * MAX_RESPONSE_BYTES + b'"}')
    client = HostClient(transport=httpx.MockTransport(lambda _:response))
    with pytest.raises(HostCLIError) as caught:
        client.operate(HostCLIRequest(command="health"))
    assert caught.value.code == "HOST_RESPONSE_TOO_LARGE"
    assert options[0]["trust_env"] is False and options[0]["follow_redirects"] is False
    with pytest.raises(HostCLIError) as caught:
        client.request("POST", "/api/harness/preview", {"value":"x" * 16384})
    assert caught.value.code == "INPUT_TOO_LARGE"


def test_timeout_does_not_retry_or_echo_destination():
    calls = []
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("secret connection details", request=request)
    with pytest.raises(HostCLIError) as caught:
        HostClient(transport=httpx.MockTransport(handler)).operate(HostCLIRequest(command="health"))
    assert caught.value.code == "HOST_TIMEOUT" and len(calls) == 1
    assert "secret connection details" not in str(caught.value)


def test_structured_carrier_contract_rejects_approval_url_override_and_path_escape():
    for payload in [{"command":"execute-context", "approved":True}, {"command":"health", "baseUrl":"http://127.0.0.1:9999"},
                    {"command":"report", "runId":"../secret"}, {"command":"preview", "kind":"harness", "payload":{}},
                    {"command":"report", "runId":"valid", "payload":{"approvalToken":"secret"}}]:
        with pytest.raises(ValidationError):
            HostCLIRequest.model_validate(payload)


def test_cli_input_duplicate_nonfinite_credentials_and_invalid_arguments_are_sanitized(tmp_path, monkeypatch, capsys):
    for raw in ['{"command":"health","command":"health"}', '{"command":"health","payload":{"x":NaN}}']:
        monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
        assert cli.main(["json"]) == 2
        captured = capsys.readouterr()
        assert not captured.out and "INVALID_INPUT" in captured.err
    key_file = tmp_path / ".env"
    key_file.write_text("DO_NOT_READ=sentinel")
    with pytest.raises(HostCLIError):
        cli.read_input(str(key_file))
    assert cli.main(["--secret-argument", "private-sentinel", "health"]) == 2
    assert "private-sentinel" not in capsys.readouterr().err


def test_noninteractive_or_missing_approve_never_requests_preview(monkeypatch, capsys):
    class ForbiddenClient:
        def __init__(self, *args):
            pass
        def operate(self, _):
            raise AssertionError("No request is authorized")
    monkeypatch.setattr(cli, "HostClient", ForbiddenClient)
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    for arguments in [["execute-context", "--kind", "harness"], ["execute-context", "--kind", "harness", "--approve"]]:
        assert cli.main(arguments) == 2
        assert "INTERACTIVE_APPROVAL_REQUIRED" in capsys.readouterr().err


def test_cli_http_history_review_reopen_and_reports_share_runtime_owner(application):
    app, provider = application
    with TestClient(app) as api:
        client = via_api(api)
        source = source_for(api)
        session = client.operate(HostCLIRequest(command="session-create", payload={"title":"Synthetic CLI session"})).result
        source["sessionId"] = session["id"]
        preview = client.operate(HostCLIRequest(command="preview", kind="harness", payload=source)).result
        run_id = preview["runId"]
        assert client.operate(HostCLIRequest(command="sessions")).result[0]["id"] == session["id"]
        assert client.operate(HostCLIRequest(command="runs", sessionId=session["id"])).result[0]["id"] == run_id
        assert client.operate(HostCLIRequest(command="sources")).result[0]["relativePath"] == "evidence.md"
        inspected = client.operate(HostCLIRequest(command="source-inspect", payload={"relativePath":"evidence.md"})).result
        assert inspected["locators"]
        binding = preview["sourceBindings"][0]
        arguments = {"identity":binding["identity"], "revision":binding["revision"], "locatorIds":binding["locatorIds"]}
        for name, extra in [("kb.search", {"query":"finding"}), ("kb.read", {"evidenceIds":binding["evidenceIds"]})]:
            call_id = name.replace(".", "-")
            tool = client.operate(HostCLIRequest(command="tool-execute", runId=run_id, payload={"sourceRequest":source,
                "call":{"callId":call_id, "name":name, "arguments":{**arguments, **extra}}})).result
            assert tool["status"] == "completed" and tool["result"]["callId"] == call_id
            assert tool["result"]["evidence"]
        report = client.operate(HostCLIRequest(command="report", runId=run_id)).result
        markdown = client.operate(HostCLIRequest(command="report", runId=run_id, format="markdown")).result
        assert report["run"]["id"] == run_id and run_id in markdown
        paused = client.operate(HostCLIRequest(command="review", runId=run_id,
            payload={"decision":"paused", "checklist":report["selection"]["task"], "note":"Synthetic pause"})).result
        assert paused["run"]["status"] == "paused"
        recovery = client.operate(HostCLIRequest(command="recovery-preview", runId=run_id, payload={"sourceRequest":source})).result
        assert recovery["preview"]["approvalToken"] != preview["approvalToken"]
        reopened = client.operate(HostCLIRequest(command="reopen", runId=run_id, payload={"sourceRequest":source})).result
        assert reopened["runId"] != run_id
        assert api.get(f'/api/runtime/runs/{reopened["runId"]}').json()["run"]["parentRunId"] == run_id
        assert provider.calls == []


def test_exact_interactive_approval_dispatches_each_stage_once_and_cancellation_none(application, monkeypatch):
    app, provider = application
    with TestClient(app) as api:
        client = via_api(api)
        source = source_for(api)
        from argparse import Namespace
        args = Namespace(command="execute-context", kind="harness", run_id=None, approve=True)
        monkeypatch.setattr(sys, "stdin", Terminal("cancel\n"))
        monkeypatch.setattr(sys, "stderr", Terminal())
        with pytest.raises(HostCLIError) as caught:
            cli.execute_stage(client, args, source)
        assert caught.value.code == "APPROVAL_CANCELLED" and provider.calls == []
        approved = []
        original_confirm = cli.confirm
        def typed_confirmation(prepared):
            approved.append(prepared)
            monkeypatch.setattr(sys, "stdin", Terminal(f"APPROVE {prepared.fingerprint}\n"))
            original_confirm(prepared)
        monkeypatch.setattr(sys, "stdin", Terminal())
        monkeypatch.setattr(sys, "stderr", Terminal())
        monkeypatch.setattr(cli, "confirm", typed_confirmation)
        context = cli.execute_stage(client, args, source)
        assert provider.calls == ["context"]
        assert context["inferencePreview"]["approvalToken"] == "[REDACTED]"
        args.command, args.run_id = "execute-inference", context["preview"]["runId"]
        finished = cli.execute_stage(client, args, source)
        assert provider.calls == ["context", "inference"] and len(approved) == 2
        assert approved[0].purpose == "context" and approved[1].purpose == "inference"
        assert finished["result"]["claims"]
        revised = client.operate(HostCLIRequest(command="revision", runId=args.run_id,
            payload={"result":finished["result"], "note":"Synthetic independent revision"})).result
        assert revised["revisions"][0]["reviewStatus"] == "pending"
        # A reopened Run has new host-owned lineage even when the retained selection came from its parent.
        source["sessionId"], source["parentRunId"] = finished["preview"]["sessionId"], None
        reopened = client.operate(HostCLIRequest(command="reopen", runId=args.run_id, payload={"sourceRequest":source})).result
        args.command, args.run_id = "execute-context", reopened["runId"]
        resumed = cli.execute_stage(client, args, source)
        assert provider.calls == ["context", "inference", "context"]
        saved = api.get(f'/api/runtime/runs/{args.run_id}').json()
        assert saved["run"]["parentRunId"] == finished["preview"]["runId"]
        assert resumed["preview"]["runId"] == reopened["runId"]


def test_registered_host_carrier_launches_real_process_to_running_fastapi(application):
    app, provider = application
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    url = f"http://127.0.0.1:{listener.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False))
    thread = threading.Thread(target=lambda:server.run(sockets=[listener]), daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    try:
        while not server.started:
            if time.monotonic() >= deadline or not thread.is_alive():
                pytest.fail("Synthetic local host did not start")
            time.sleep(0.01)
        definition, execute = host_cli_binding(url)
        assert definition.name == "frag.host" and "PYTHONPATH" not in definition.environment_names
        registry = CLIRegistry()
        registry.register(definition, execute)
        for command in ["health", "capabilities"]:
            result = HostCLIResponse.model_validate(registry.get("frag.host").execute({"command":command}))
            assert result.command == command
            if command == "health":
                assert result.result["service"] == "frag-harness"
            else:
                assert {item["name"] for item in result.result["cli"]} >= {"frag.host"}
        env = {name:value for name, value in os.environ.items() if name.upper() in {"SYSTEMROOT", "WINDIR"}}
        process = subprocess.run([sys.executable, "-X", "utf8", "-m", "frag_api.cli", "--base-url", url, "health"],
                                 cwd=Path(__file__).resolve().parents[1], env=env, text=True, capture_output=True, timeout=10)
        assert process.returncode == 0 and json.loads(process.stdout)["status"] == "ok"
        assert provider.calls == []
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()
        assert not thread.is_alive()
