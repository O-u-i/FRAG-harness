"""User-operated HTTP CLI. Importing this module never starts the application."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from frag_api.cli_client import DEFAULT_BASE_URL, MAX_REQUEST_BYTES, HostClient, HostCLIError, strict_json
from frag_api.schemas.cli import EMPTY_COMMANDS, RUN_COMMANDS, HostCLIRequest, source_payload
from frag_api.schemas.harness import HarnessContextRun, HarnessPreview, HarnessRun, HarnessRunRequest
from frag_api.schemas.rag import InferencePreview, InferenceRunRequest, RagContextRun, RagPreview, RagRun, RagRunRequest
from frag_api.schemas.runtime import RecoveryPreview


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise HostCLIError("INVALID_ARGUMENTS", "Invalid CLI arguments; use --help for the supported command contract.")


def parser():
    result = Parser(description="Operate the running FRAG FastAPI host over loopback HTTP.")
    result.add_argument("--base-url", default=DEFAULT_BASE_URL)
    commands = result.add_subparsers(dest="command", required=True, parser_class=Parser)
    names = ["health", "capabilities", "sources", "source-inspect", "sessions", "session-create",
             "runs", "report", "preview", "recovery-preview", "reopen", "review", "revision", "tool-execute",
             "research-preview", "execute-context", "execute-inference", "execute-research", "json"]
    for name in names:
        command = commands.add_parser(name)
        if name not in EMPTY_COMMANDS:
            command.add_argument("--input", help="Explicit JSON request file; otherwise read bounded JSON from stdin.")
        if name in RUN_COMMANDS or name == "execute-inference":
            command.add_argument("--run-id", required=True)
        elif name in {"execute-context", "research-preview", "execute-research"}:
            command.add_argument("--run-id", help="Resume this Run instead of preparing a new Run.")
        if name in {"preview", "research-preview", "execute-context", "execute-inference", "execute-research"}:
            command.add_argument("--kind", choices=["harness", "rag"], required=True)
        if name == "runs":
            command.add_argument("--session-id")
        if name == "report":
            command.add_argument("--format", choices=["json", "markdown"], default="json")
        if name.startswith("execute-"):
            command.add_argument("--approve", action="store_true", help="Enable an interactive exact-fingerprint approval prompt.")
    return result


def read_input(filename=None):
    try:
        if filename:
            path = Path(filename).resolve()
            # This entry accepts request JSON, never credential or database files.
            if (path.suffix.lower() != ".json" or path.name.lower().startswith(".env")
                    or not path.is_file() or path.stat().st_size > MAX_REQUEST_BYTES):
                raise HostCLIError("INVALID_INPUT", "Select one existing JSON request file within 16 KiB.")
            with path.open("rb") as stream:
                value = stream.read(MAX_REQUEST_BYTES + 1)
        else:
            value = sys.stdin.read(MAX_REQUEST_BYTES + 1).encode("utf-8")
        if len(value) > MAX_REQUEST_BYTES:
            raise HostCLIError("INPUT_TOO_LARGE", "Input exceeds the 16 KiB host request limit.")
        parsed = strict_json(value)
        if not isinstance(parsed, dict):
            raise ValueError()
        return parsed
    except HostCLIError:
        raise
    except (OSError, ValueError, UnicodeError, RecursionError) as error:
        raise HostCLIError("INVALID_INPUT", "Provide one valid structured JSON request object.") from error


def confirm(prepared):
    print("Exact outbound PreparedCall:", file=sys.stderr)
    print(json.dumps(prepared.model_dump(by_alias=True), ensure_ascii=False, indent=2), file=sys.stderr)
    expected = f"APPROVE {prepared.fingerprint}"
    print(f"Type {expected} to execute only this model stage: ", file=sys.stderr, end="", flush=True)
    if sys.stdin.readline().strip() != expected:
        raise HostCLIError("APPROVAL_CANCELLED", "Approval was cancelled; no model request was sent.")


def without_tokens(value):
    if isinstance(value, dict):
        return {key: "[REDACTED]" if key == "approvalToken" else without_tokens(item) for key, item in value.items()}
    if isinstance(value, list):
        return [without_tokens(item) for item in value]
    return value


def execute_stage(client, args, payload):
    """A fresh server preview, exact interactive approval and one dispatch only."""
    if not args.approve or not sys.stdin.isatty() or not sys.stderr.isatty():
        raise HostCLIError("INTERACTIVE_APPROVAL_REQUIRED", "Model execution requires --approve, a terminal and exact interactive confirmation.")
    source = source_payload(payload, args.kind)
    stage = "context" if args.command == "execute-context" else "inference"
    if args.run_id:
        operation = HostCLIRequest(command="recovery-preview", runId=args.run_id,
                                   kind=args.kind, payload={"sourceRequest":source})
        recovery = RecoveryPreview.model_validate(client.operate(operation).result)
        if recovery.kind != args.kind or recovery.stage != stage:
            raise HostCLIError("WRONG_RECOVERY_STAGE", "The saved Run requires a different stage; no model request was sent.")
        preview_data, context_fingerprint = recovery.preview, recovery.context_fingerprint
        source = operation.payload["sourceRequest"]
    else:
        operation = HostCLIRequest(command="preview", kind=args.kind, payload=source)
        preview_data = client.operate(operation).result
        context_fingerprint = preview_data.get("contextFingerprint")
    if stage == "context":
        model = HarnessPreview if args.kind == "harness" else RagPreview
        preview = model.model_validate(preview_data)
        if not preview.can_approve:
            raise HostCLIError("PREVIEW_BLOCKED", "The host preview is blocked; resolve its source or checklist conditions.")
        execution_model = HarnessRunRequest if args.kind == "harness" else RagRunRequest
        body = execution_model.model_validate({**source, "contextFingerprint":context_fingerprint,
                                               "approvalToken":preview.approval_token, "approved":True})
        fingerprint = preview.context_fingerprint
        path = f"/api/{args.kind}/run"
    else:
        preview = InferencePreview.model_validate(preview_data)
        body = InferenceRunRequest(contextFingerprint=context_fingerprint,
                                   inferenceFingerprint=preview.inference_fingerprint,
                                   approvalToken=preview.approval_token, approved=True)
        fingerprint = preview.inference_fingerprint
        path = f"/api/{args.kind}/inference/run"
    if preview.prepared_call.purpose != stage or preview.prepared_call.fingerprint != fingerprint:
        raise HostCLIError("INVALID_HOST_PREVIEW", "The host preview does not match its exact request fingerprint.")
    confirm(preview.prepared_call)
    # The next stage's token is unused and omitted from this execution output.
    result = client.request("POST", path, body.model_dump(by_alias=True), timeout=125)
    result_model = (HarnessContextRun if args.kind == "harness" else RagContextRun) if stage == "context" else (
        HarnessRun if args.kind == "harness" else RagRun)
    result_model.model_validate(result)
    return without_tokens(result)


def execute_research(client, args, payload):
    """Approve one Research/Context/Inference checkpoint, never a whole loop."""
    from frag_api.schemas.research import ResearchPreview
    from frag_api.schemas.runtime import RunReport
    if not args.approve or not sys.stdin.isatty() or not sys.stderr.isatty():
        raise HostCLIError("INTERACTIVE_APPROVAL_REQUIRED", "Model execution requires --approve, a terminal and exact interactive confirmation.")
    operation = HostCLIRequest(command="research-preview", kind=args.kind, runId=args.run_id,
                               payload=source_payload(payload, args.kind))
    preview = ResearchPreview.model_validate(client.operate(operation).result)
    if not preview.can_approve or not preview.approval_token:
        raise HostCLIError("PREVIEW_BLOCKED", "The host preview is blocked; resolve its source or checklist conditions.")
    if (preview.prepared_call.purpose != preview.stage or preview.prepared_call.fingerprint != preview.fingerprint
            or (args.run_id and preview.run_id != args.run_id)):
        raise HostCLIError("INVALID_HOST_PREVIEW", "The host preview does not match the selected Run and exact request.")
    HostCLIRequest(command="report", runId=preview.run_id)
    confirm(preview.prepared_call)
    result = client.request("POST", f"/api/runtime/runs/{preview.run_id}/research/execute", {
        "sourceRequest": operation.payload, "fingerprint": preview.fingerprint,
        "approvalToken": preview.approval_token, "approved": True,
    }, timeout=185 if preview.stage == "research" else 125)
    report = RunReport.model_validate(result)
    if report.run.id != preview.run_id or report.run.kind != args.kind or report.research is None:
        raise HostCLIError("INVALID_HOST_RESPONSE", "The host returned a different Run after execution.")
    return without_tokens(result)


def main(argv=None):
    try:
        args = parser().parse_args(argv)
        client = HostClient(args.base_url)
        if args.command.startswith("execute-") and (not args.approve or not sys.stdin.isatty() or not sys.stderr.isatty()):
            raise HostCLIError("INTERACTIVE_APPROVAL_REQUIRED", "Model execution requires --approve, a terminal and exact interactive confirmation.")
        payload = {} if args.command in EMPTY_COMMANDS else read_input(args.input)
        if args.command == "json":
            response = client.operate(HostCLIRequest.model_validate(payload))
            result = response.model_dump(by_alias=True)
        elif args.command == "execute-research":
            result = execute_research(client, args, payload)
        elif args.command.startswith("execute-"):
            result = execute_stage(client, args, payload)
        else:
            request = HostCLIRequest(command=args.command, kind=getattr(args, "kind", None),
                                     runId=getattr(args, "run_id", None), sessionId=getattr(args, "session_id", None),
                                     format=getattr(args, "format", "json"), payload=payload)
            result = client.operate(request).result
        print(result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
        return 0
    except HostCLIError as error:
        print(json.dumps({"error":{"code":error.code, "message":error.message}}), file=sys.stderr)
        return 2
    except (ValidationError, ValueError, TypeError, AttributeError, KeyError):
        print(json.dumps({"error":{"code":"INVALID_CONTRACT", "message":"Input or host output does not match the declared CLI contract."}}), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print(json.dumps({"error":{"code":"INTERRUPTED", "message":"The operation was interrupted; inspect Run history before any new model execution."}}), file=sys.stderr)
        return 130
    except Exception:
        print(json.dumps({"error":{"code":"HOST_CLI_ERROR", "message":"The host operation could not be completed; inspect safe diagnostics."}}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
