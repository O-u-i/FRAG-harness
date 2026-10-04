"""Bounded loopback HTTP client and the registered host CLI process binding."""
from __future__ import annotations

import ipaddress
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from pydantic import TypeAdapter, ValidationError

from frag_api.request_spec import strict_json
from frag_api.schemas.cli import HostCLIRequest, HostCLIResponse
from frag_api.schemas.context_source import LocalFileInspectResponse, LocalFileSource
from frag_api.schemas.governance import CapabilityCatalog, CLIDefinition
from frag_api.schemas.harness import HarnessPreview
from frag_api.schemas.rag import RagPreview
from frag_api.schemas.runtime import RecoveryPreview, RunRecord, RunReport, SessionRecord
from frag_api.schemas.tools import ToolCallRecord

DEFAULT_BASE_URL = "http://127.0.0.1:8787"
MAX_REQUEST_BYTES = 16 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024


class HostCLIError(Exception):
    def __init__(self, code="HOST_CLI_ERROR", message="The host operation could not be completed."):
        self.code, self.message = code, message
        super().__init__(message)


def loopback_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        address = ipaddress.ip_address(parts.hostname or "")
        port = 80 if parts.port is None else parts.port
        if (parts.scheme != "http" or not address.is_loopback or parts.username is not None
                or parts.password is not None or parts.path not in {"", "/"}
                or "?" in value or "#" in value or any(character.isspace() for character in value)
                or not 1 <= port <= 65535):
            raise ValueError()
        host = f"[{address}]" if address.version == 6 else str(address)
        return f"http://{host}:{port}"
    except (ValueError, TypeError) as error:
        raise HostCLIError("INVALID_HOST_URL", "Use a numeric loopback HTTP URL without credentials, path, query or fragment.") from error


class HostClient:
    def __init__(self, base_url=DEFAULT_BASE_URL, *, transport=None):
        self.base_url = loopback_url(base_url)
        self.transport = transport

    def request(self, method, path, payload=None, *, params=None, markdown=False, timeout=10):
        body = None
        if payload is not None:
            try:
                body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
            except (TypeError, ValueError) as error:
                raise HostCLIError("INVALID_INPUT", "Provide a valid structured JSON object.") from error
            if len(body) > MAX_REQUEST_BYTES:
                raise HostCLIError("INPUT_TOO_LARGE", "Input exceeds the 16 KiB host request limit.")
        if not 0 < timeout <= 185:
            raise HostCLIError("INVALID_TIMEOUT", "The host timeout is outside its allowed range.")
        deadline = time.monotonic() + timeout
        headers = {"Accept": "text/markdown" if markdown else "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        try:
            with httpx.Client(trust_env=False, follow_redirects=False, timeout=timeout, transport=self.transport) as client:
                with client.stream(method, self.base_url + path, params=params, content=body, headers=headers) as response:
                    if response.status_code >= 300:
                        # Do not display server exceptions, request echoes or Location headers.
                        raise HostCLIError("HOST_REQUEST_REJECTED", "The local host rejected the operation; inspect its governed UI or safe diagnostics.")
                    media_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                    expected = "text/markdown" if markdown else "application/json"
                    if media_type != expected:
                        raise HostCLIError("INVALID_HOST_RESPONSE", "The host returned an unexpected response format.")
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        if time.monotonic() > deadline:
                            raise HostCLIError("HOST_TIMEOUT", "The local host operation timed out; do not automatically retry model execution.")
                        if len(content) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise HostCLIError("HOST_RESPONSE_TOO_LARGE", "The host response exceeds the 1 MiB CLI limit.")
                        content.extend(chunk)
            if markdown:
                return bytes(content).decode("utf-8")
            result = strict_json(content)
            if not isinstance(result, (dict, list)) or (isinstance(result, dict) and "error" in result):
                raise ValueError()
            return result
        except HostCLIError:
            raise
        except httpx.TimeoutException as error:
            raise HostCLIError("HOST_TIMEOUT", "The local host operation timed out; do not automatically retry model execution.") from error
        except httpx.HTTPError as error:
            raise HostCLIError("HOST_UNAVAILABLE", "The local FastAPI host is unavailable.") from error
        except (ValueError, UnicodeError, RecursionError) as error:
            raise HostCLIError("INVALID_HOST_RESPONSE", "The host returned invalid structured data.") from error

    def operate(self, request: HostCLIRequest) -> HostCLIResponse:
        command, run_id = request.command, request.run_id
        if command == "recovery-preview":
            try:
                saved = RunReport.model_validate(self.request("GET", f"/api/runtime/runs/{run_id}/report.json"))
            except ValidationError:
                raise HostCLIError("INVALID_HOST_RESPONSE", "The host returned invalid Run metadata.") from None
            if saved.run.id != run_id or (request.kind is not None and request.kind != saved.run.kind):
                raise HostCLIError("INVALID_HOST_RESPONSE", "The selected Run identity does not match the requested recovery.")
            # Preserve the explicitly supplied source contents; refresh only host-owned lineage.
            request.payload["sourceRequest"]["sessionId"] = saved.run.session_id
            request.payload["sourceRequest"]["parentRunId"] = saved.run.parent_run_id
        paths = {"health":"/api/health", "capabilities":"/api/harness/capabilities",
                 "sources":"/api/context-sources/files", "sessions":"/api/runtime/sessions",
                 "runs":"/api/runtime/runs"}
        posts = {"source-inspect":"/api/context-sources/files/inspect", "session-create":"/api/runtime/sessions",
                 "preview":f"/api/{request.kind}/preview", "recovery-preview":f"/api/runtime/runs/{run_id}/resume/preview",
                 "reopen":f"/api/runtime/runs/{run_id}/reopen", "review":f"/api/runtime/runs/{run_id}/review",
                 "revision":f"/api/runtime/runs/{run_id}/revisions", "tool-execute":f"/api/runtime/runs/{run_id}/tools/execute"}
        if command == "research-preview":
            from frag_api.schemas.research import ResearchPreview
            body = {"sourceRequest": request.payload}
            path = f"/api/runtime/runs/{run_id}/research/preview" if run_id else "/api/runtime/research/preview"
            if not run_id:
                body["kind"] = request.kind
            else:
                saved = RunReport.model_validate(self.request("GET", f"/api/runtime/runs/{run_id}/report.json"))
                if saved.run.id != run_id or saved.run.kind != request.kind or saved.research is None:
                    raise HostCLIError("INVALID_HOST_RESPONSE", "The selected Run does not match the Research continuation.")
                # Research binds the original complete typed selection, including lineage.
                # The caller must retain that selection; a changed input requires Reopen.
            result = self.request("POST", path, body)
            ResearchPreview.model_validate(result)
        elif command in paths:
            params = {"sessionId":request.session_id} if request.session_id else None
            result = self.request("GET", paths[command], params=params)
        elif command == "report":
            suffix = "report.md" if request.format == "markdown" else "report.json"
            result = self.request("GET", f"/api/runtime/runs/{run_id}/{suffix}", markdown=request.format == "markdown")
        else:
            result = self.request("POST", posts[command], request.payload)
        models = {"capabilities":CapabilityCatalog, "sources":list[LocalFileSource], "source-inspect":LocalFileInspectResponse,
                  "sessions":list[SessionRecord], "session-create":SessionRecord, "runs":list[RunRecord],
                  "report":RunReport, "preview":HarnessPreview if request.kind == "harness" else RagPreview,
                  "recovery-preview":RecoveryPreview, "reopen":RecoveryPreview, "review":RunReport,
                  "revision":RunReport, "tool-execute":ToolCallRecord}
        try:
            if command in models and not (command == "report" and request.format == "markdown"):
                TypeAdapter(models[command]).validate_python(result)
            elif command == "health" and (not isinstance(result, dict) or result.get("status") != "ok"
                                          or result.get("service") != "frag-harness"):
                raise ValueError()
        except (ValidationError, ValueError):
            raise HostCLIError("INVALID_HOST_RESPONSE", "The host returned a result outside its declared operation contract.") from None
        return HostCLIResponse(command=command, result=result)


def host_cli_binding(base_url=DEFAULT_BASE_URL):
    """Return a fixed real process binding; JSON mode cannot approve model calls."""
    from frag_api.services.cli_executor import ControlledCLI

    directory = Path(__file__).resolve().parents[1]
    definition = CLIDefinition(
        name="frag.host", version="1.0.0", executable=str(Path(sys.executable).resolve()),
        subcommand=("-X", "utf8", "-m", "frag_api.cli", "--base-url", loopback_url(base_url), "json"),
        workingDirectory=str(directory), environmentNames=("SYSTEMROOT", "WINDIR"),
        inputSchema=json.dumps(HostCLIRequest.model_json_schema(by_alias=True)),
        outputSchema=json.dumps(HostCLIResponse.model_json_schema(by_alias=True)),
    )
    carrier = ControlledCLI(definition, allowed_working_root=directory, timeout_seconds=10,
                            output_bytes=MAX_RESPONSE_BYTES, role="host")
    return definition, carrier.execute
