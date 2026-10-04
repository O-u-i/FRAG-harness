"""A bounded, backend-only Node carrier; model credentials travel only on stdin."""
from __future__ import annotations

import os
import queue
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from frag_api.errors import RagNotReadyError, RagOutcomeUnknownError, RagProviderError
from frag_api.providers.prepared import strict_json
from frag_api.request_spec import canonical_json

WORKER_ROOT = Path(__file__).resolve().parents[2] / "pi-worker"
STDOUT_LIMIT = 256 * 1024
STDERR_LIMIT = 8 * 1024
INPUT_LIMIT = 1024 * 1024
ENVIRONMENT_NAMES = ("SystemRoot", "WINDIR", "TEMP", "TMP")


def supported_model(model: str) -> bool:
    return model == "gpt-6.1-sol" or bool(re.fullmatch(r"gpt-4\.1(?:-mini|-nano)?(?:-2025-04-14)?", model))


def configured_endpoint(base_url: str | None) -> str:
    """A configured route is explicit authority; reject ambiguous URL normalization."""
    base = base_url or "https://api.openai.com/v1/"
    if not isinstance(base, str) or not base.isascii() or any(char.isspace() for char in base):
        raise RagNotReadyError()
    try:
        parts = urlsplit(base)
        labels = (parts.hostname or "").split(".")
        if (parts.scheme != "https" or not parts.hostname or len(parts.hostname) > 253
                or parts.netloc != parts.hostname or parts.path not in {"/v1", "/v1/"}
                or parts.query or parts.fragment or "?" in base or "#" in base
                or base != f"https://{parts.hostname}{parts.path}"
                or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels)):
            raise RagNotReadyError()
    except ValueError:
        raise RagNotReadyError() from None
    return base.rstrip("/") + "/responses"


def worker_ready(model: str, base_url: str | None) -> bool:
    try:
        configured_endpoint(base_url)
    except RagNotReadyError:
        return False
    return (supported_model(model)
            and bool(shutil.which("node")) and all((WORKER_ROOT / name).is_file() for name in (
                "worker.mjs", "verify-package.mjs", "package-lock.json",
                "vendor/pi-ai/selection-manifest.json", "node_modules/openai/package.json",
                "node_modules/partial-json/package.json")))


def execute_worker(call, api_key: str) -> dict:
    executable = shutil.which("node")
    if not executable or not api_key or not worker_ready(call.model, call.endpoint.removesuffix("responses")):
        raise RagNotReadyError()
    envelope = {"protocolVersion": 1, "preparedCall": call.model_dump(by_alias=True), "apiKey": api_key}
    payload = (canonical_json(envelope) + "\n").encode("utf-8")
    if len(payload) > INPUT_LIMIT:
        raise RagProviderError()
    return run_worker_process([str(Path(executable).resolve()), str(WORKER_ROOT / "worker.mjs")],
                              payload, call.fingerprint, call.timeout_seconds, WORKER_ROOT)


def run_worker_process(command: list[str], payload: bytes, expected_fingerprint: str,
                       timeout: float, cwd: Path) -> dict:
    """Fixed callers choose command/cwd; never expose this carrier as a model tool."""
    if not 0 < timeout <= 120 or len(payload) > INPUT_LIMIT:
        raise RagProviderError()
    environment = {name: os.environ[name] for name in ENVIRONMENT_NAMES if name in os.environ}
    try:
        process = subprocess.Popen(command, cwd=cwd, env=environment, shell=False,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except (OSError, ValueError):
        raise RagNotReadyError() from None
    events: queue.Queue = queue.Queue(maxsize=128)
    stopped, overflow = threading.Event(), threading.Event()

    def read_pipe(pipe, name, limit):
        total = 0
        try:
            while not stopped.is_set():
                block = os.read(pipe.fileno(), 4096)
                if not block:
                    break
                total += len(block)
                if total > limit:
                    overflow.set()
                    break
                while not stopped.is_set():
                    try:
                        events.put((name, block), timeout=0.05)
                        break
                    except queue.Full:
                        continue
        except (OSError, ValueError):
            pass
        finally:
            while not stopped.is_set():
                try:
                    events.put((name, None), timeout=0.05)
                    break
                except queue.Full:
                    continue

    def write_input():
        try:
            process.stdin.write(payload)
            process.stdin.close()
        except (OSError, ValueError):
            pass

    threads = [threading.Thread(target=read_pipe, args=(process.stdout, "stdout", STDOUT_LIMIT), daemon=True),
               threading.Thread(target=read_pipe, args=(process.stderr, "stderr", STDERR_LIMIT), daemon=True),
               threading.Thread(target=write_input, daemon=True)]
    for thread in threads:
        thread.start()
    deadline, closed = time.monotonic() + timeout, set()
    output = bytearray()
    try:
        while len(closed) < 2:
            if overflow.is_set() or time.monotonic() >= deadline:
                raise RagOutcomeUnknownError()
            try:
                name, data = events.get(timeout=min(0.05, max(0.001, deadline - time.monotonic())))
            except queue.Empty:
                continue
            if data is None:
                closed.add(name)
            elif name == "stdout":
                output.extend(data)
        process.wait(timeout=max(0.001, deadline - time.monotonic()))
        if overflow.is_set():
            raise RagOutcomeUnknownError()
        try:
            frames = [strict_json(line) for line in output.decode("utf-8", errors="strict").splitlines() if line]
            if (not frames or len(frames) > 2 or any(not isinstance(frame, dict) for frame in frames)
                    or any(frame.get("protocolVersion") != 1 or frame.get("fingerprint") != expected_fingerprint for frame in frames)):
                raise ValueError()
            dispatch = len(frames) == 2 and frames[0].get("event") == "dispatch"
            final = frames[-1]
            if final.get("event") != "result" or not isinstance(final.get("ok"), bool):
                raise ValueError()
            if final["ok"]:
                if not dispatch or process.returncode != 0 or set(final) != {"protocolVersion", "event", "fingerprint", "ok", "response"}:
                    raise ValueError()
            elif (set(final) != {"protocolVersion", "event", "fingerprint", "ok", "errorCode", "dispatched"}
                  or final.get("dispatched") is not dispatch):
                raise ValueError()
            return final
        except (ValueError, TypeError, UnicodeError):
            raise RagOutcomeUnknownError() from None
    except subprocess.TimeoutExpired:
        raise RagOutcomeUnknownError() from None
    finally:
        stopped.set()
        if process.poll() is None:
            process.kill()
        process.wait()
        for thread in threads:
            thread.join(timeout=0.5)
        for pipe in (process.stdin, process.stdout, process.stderr):
            if pipe is not None and not pipe.closed:
                pipe.close()
