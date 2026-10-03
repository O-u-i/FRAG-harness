"""Real subprocess failures verify bounded I/O and fixed selected-snapshot reads."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from frag_api.schemas.governance import CLIDefinition
from frag_api.services.cli_executor import ControlledCLI, INPUT_BYTES, ToolExecutionError

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "backend" / "frag_api" / "tool_worker.py"


def definition(directory, subcommand, **changes):
    values = {"name": "selected-read", "version": "1.0.0", "executable": str(Path(sys.executable).resolve()),
              "subcommand": subcommand, "workingDirectory": str(directory.resolve()),
              "environmentNames": ("SYSTEMROOT", "WINDIR"), "inputSchema": "{}", "outputSchema": "{}"}
    return CLIDefinition(**{**values, **changes})


def program(tmp_path, text, *, timeout=2, output_bytes=16 * 1024, **changes):
    item = definition(tmp_path, ("-I", "-c", text), **changes)
    return ControlledCLI(item, ROOT, timeout_seconds=timeout, output_bytes=output_bytes)


def payload():
    return {"callId": "call-selected-1", "arguments": {"identity": {"kind": "local_file", "namespace": "synthetic-test",
            "resourceId": "explicit-selection.md", "workspaceId": None}, "revision": "fixed-synthetic-revision",
            "locatorIds": ["heading:1"], "evidenceIds": ["ev-1"]},
            "evidence": [{"evidenceId": "ev-1", "documentId": "document-1", "sourceId": "source-1",
                          "locatorId": "heading:1", "locatorLabel": "Selected paragraph", "text": "Synthetic finding 合成证据"}]}


def test_real_worker_reads_only_selected_snapshot_and_preserves_call_id(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "credential-must-not-be-inherited")
    command = definition(tmp_path, ("-I", str(WORKER), "read"))
    runner = ControlledCLI(command, ROOT)
    request = payload()
    request["evidence"].append({**request["evidence"][0], "evidenceId": "unrequested", "locatorId": "heading:2"})
    result = runner.execute(request)
    assert result == {"callId": "call-selected-1", "evidence": request["evidence"][:1], "missingInformation": []}
    assert "credential-must-not-be-inherited" not in json.dumps(result)


def test_fixed_argv_shell_false_and_environment_exclude_credentials(tmp_path, monkeypatch):
    for name in ("OPENAI_API_KEY", "AUTH_TOKEN", "HTTP_PROXY", "HTTPS_PROXY", "PYTHONPATH", "LD_PRELOAD"):
        monkeypatch.setenv(name, "credential-never-inherited")
    command = program(tmp_path, "import json,os,sys; json.load(sys.stdin); print(json.dumps({'names':sorted(os.environ)}))")
    observed = []
    original = subprocess.Popen

    def spy(argv, **kwargs):
        observed.append((argv, kwargs))
        return original(argv, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", spy)
    result = command.execute({"injection": "&& echo credential-never-inherited"})
    assert not {"OPENAI_API_KEY", "AUTH_TOKEN", "HTTP_PROXY", "HTTPS_PROXY", "PYTHONPATH", "LD_PRELOAD"} & set(result["names"])
    argv, options = observed[0]
    assert options["shell"] is False and options["cwd"] == str(tmp_path.resolve())
    assert "&& echo credential-never-inherited" not in argv
    assert options["creationflags"] == (subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)


@pytest.mark.parametrize("output", ["not JSON", "[]", '{} {}', '{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '{"a":1e999}'])
def test_invalid_process_json_is_rejected_without_echoing_output(tmp_path, output):
    runner = program(tmp_path, "import sys; sys.stdin.read(); print(" + repr(output) + ")")
    with pytest.raises(ToolExecutionError) as error:
        runner.execute({"selected": "private-input"})
    assert error.value.code == "TOOL_JSON"
    assert str(error.value) == "TOOL_JSON" and output not in str(error.value)


def test_nonzero_exit_has_no_raw_stderr_or_input(tmp_path):
    runner = program(tmp_path, "import sys; sys.stdin.read(); sys.stderr.write('credential-private-output'); sys.exit(7)")
    with pytest.raises(ToolExecutionError, match="^TOOL_EXIT$"):
        runner.execute({"secret": "private-input"})


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_output_and_stderr_are_stream_bounded(tmp_path, stream):
    runner = program(tmp_path, "import sys; sys.stdin.read(); sys." + stream + ".write('X'*10000000); sys." + stream + ".flush()")
    started = time.monotonic()
    with pytest.raises(ToolExecutionError, match="^TOOL_OUTPUT_LIMIT$"):
        runner.execute({})
    assert time.monotonic() - started < 4


def test_stdout_and_stderr_share_one_result_budget(tmp_path):
    runner = program(tmp_path, "import sys; sys.stdin.read(); sys.stdout.write('{\"text\":\"'+'X'*3000+'\"}'); sys.stdout.flush(); sys.stderr.write('Y'*3000)", output_bytes=4096)
    with pytest.raises(ToolExecutionError, match="^TOOL_OUTPUT_LIMIT$"):
        runner.execute({})


@pytest.mark.parametrize("input_payload", [{}, {"data": "X" * 100000}])
def test_timeout_covers_output_wait_and_blocked_stdin(tmp_path, input_payload):
    runner = program(tmp_path, "import time; time.sleep(10)", timeout=0.2)
    started = time.monotonic()
    with pytest.raises(ToolExecutionError, match="^TOOL_TIMEOUT$"):
        runner.execute(input_payload)
    assert time.monotonic() - started < 2


@pytest.mark.parametrize("input_payload", [{"oversized": "X" * INPUT_BYTES}, {"nan": float("nan")}, ["not-object"]])
def test_invalid_input_never_starts_a_process(tmp_path, input_payload, monkeypatch):
    runner = program(tmp_path, "print('{}')")
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: pytest.fail("A process must not start"))
    with pytest.raises(ToolExecutionError, match="^TOOL_INPUT$"):
        runner.execute(input_payload)


@pytest.mark.parametrize("changes", [{"workingDirectory": ".."}, {"workingDirectory": str(Path(sys.executable).parent)},
                                     {"executable": "python.exe"}, {"environmentNames": ("OPENAI_API_KEY",)},
                                     {"environmentNames": ("PYTHONPATH",)}, {"environmentNames": ("HTTPS_PROXY",)}])
def test_paths_and_environment_cannot_escape_pinned_configuration(tmp_path, changes):
    item = definition(tmp_path, ("-I", "-c", "print('{}')"), **changes)
    with pytest.raises(ToolExecutionError, match="^TOOL_CONFIGURATION$"):
        ControlledCLI(item, tmp_path)


def test_fixed_worker_script_change_rejected_before_execution(tmp_path, monkeypatch):
    script = tmp_path / "worker.py"
    script.write_text("print('{}')", encoding="utf-8")
    runner = ControlledCLI(definition(tmp_path, ("-I", str(script))), ROOT)
    script.write_text("print('{\"changed\":true}')", encoding="utf-8")
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: pytest.fail("Changed worker cannot execute"))
    with pytest.raises(ToolExecutionError, match="^TOOL_CONFIGURATION$"):
        runner.execute({})


def test_definition_replacement_cannot_change_fixed_arguments(tmp_path, monkeypatch):
    runner = program(tmp_path, "print('{}')")
    runner.definition = runner.definition.model_copy(update={"subcommand": ("-I", "-c", "print('changed')")})
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: pytest.fail("Changed arguments cannot execute"))
    with pytest.raises(ToolExecutionError, match="^TOOL_CONFIGURATION$"):
        runner.execute({})


def test_larger_host_output_requires_explicit_host_role(tmp_path):
    item = definition(tmp_path, ("-I", "-c", "import sys; sys.stdin.read(); print('{\"result\":\"'+'x'*32768+'\"}')"))
    with pytest.raises(ToolExecutionError, match="^TOOL_CONFIGURATION$"):
        ControlledCLI(item, ROOT, output_bytes=65536)
    result = ControlledCLI(item, ROOT, output_bytes=65536, role="host").execute({})
    assert len(result["result"]) == 32768
    with pytest.raises(ToolExecutionError, match="^TOOL_CONFIGURATION$"):
        ControlledCLI(item, ROOT, output_bytes=1024 * 1024 + 1, role="host")


@pytest.mark.parametrize("change", ["unknown_evidence", "unknown_locator", "duplicate_evidence", "fc", "extra_field", "malformed_row"])
def test_worker_rejects_invalid_scope_and_envelopes(tmp_path, change):
    request = payload()
    if change == "unknown_evidence":
        request["arguments"]["evidenceIds"] = ["not-selected"]
    elif change == "unknown_locator":
        request["arguments"]["locatorIds"] = ["not-selected"]
    elif change == "duplicate_evidence":
        request["evidence"].append(request["evidence"][0].copy())
    elif change == "fc":
        request["arguments"]["identity"].update(kind="fc_record", workspaceId="ws-private")
    elif change == "extra_field":
        request["shell"] = "whoami"
    else:
        request["evidence"][0]["text"] = 123
    runner = ControlledCLI(definition(tmp_path, ("-I", str(WORKER), "read")), ROOT)
    with pytest.raises(ToolExecutionError, match="^TOOL_EXIT$"):
        runner.execute(request)


@pytest.mark.parametrize("raw", [b'{"callId":"a","callId":"b"}', b'{"callId":NaN}', b'{"bad":'])
def test_worker_raw_duplicate_nonfinite_and_incomplete_json_fail(raw, tmp_path):
    completed = subprocess.run([sys.executable, "-I", str(WORKER), "read"], input=raw, capture_output=True,
                               env={}, cwd=tmp_path, timeout=2, shell=False,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    assert completed.returncode == 2 and completed.stdout == b""
    assert completed.stderr == b"Selected read request rejected.\r\n" if os.name == "nt" else completed.stderr == b"Selected read request rejected.\n"
