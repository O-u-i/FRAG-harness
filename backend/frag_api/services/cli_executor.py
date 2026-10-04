"""Bounded JSON I/O for a host-pinned executable; payloads never become argv."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import time

from frag_api.request_spec import strict_json
from frag_api.schemas.governance import CLIDefinition

INPUT_BYTES = 128 * 1024
_ENVIRONMENT_NAMES = frozenset({"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL", "LC_CTYPE"})


class ToolExecutionError(Exception):
    """The code is safe to report; process text, input and paths are not reported."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ControlledCLI:
    """A trusted registration is fixed at construction and rechecked for every call.

    Schemas are validated by the host registry's input/output models. This carrier
    validates JSON framing, executable/path pins, environment and resource limits.
    The selected worker itself never opens evidence files or launches descendants.
    """

    def __init__(self, definition: CLIDefinition, allowed_working_root: Path | str,
                 timeout_seconds: float = 10, output_bytes: int = 16 * 1024, *, role: str = "tool"):
        self.definition = definition
        self.timeout_seconds = timeout_seconds
        self.output_bytes = output_bytes
        try:
            if (role not in {"tool", "host"} or not isinstance(definition, CLIDefinition)
                    or isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
                    or not 0 < timeout_seconds <= 10
                    or isinstance(output_bytes, bool) or not isinstance(output_bytes, int)
                    or not 0 < output_bytes <= (16 * 1024 if role == "tool" else 1024 * 1024)):
                raise ValueError("Invalid limits")
            self._definition_json = definition.model_dump_json()
            self._subcommand = tuple(definition.subcommand)
            self._root = Path(allowed_working_root).resolve(strict=True)
            executable, directory = Path(definition.executable), Path(definition.working_directory)
            if (not executable.is_absolute() or not directory.is_absolute()
                    or not self._root.is_dir() or not definition.subcommand
                    or any("\0" in value for value in definition.subcommand)):
                raise ValueError("Invalid fixed paths")
            self._executable = executable.resolve(strict=True)
            self._directory = directory.resolve(strict=True)
            if not self._executable.is_file() or not self._directory.is_dir() or not self._directory.is_relative_to(self._root):
                raise ValueError("Outside working scope")
            names = [name.upper() for name in definition.environment_names]
            if len(set(names)) != len(names) or not set(names).issubset(_ENVIRONMENT_NAMES):
                raise ValueError("Invalid environment whitelist")
            self._environment_names = frozenset(names)
            for schema in (definition.input_schema, definition.output_schema):
                if not isinstance(json.loads(schema), dict):
                    raise ValueError("Invalid schema")
            self._directory_identity = self._identity(self._directory)
            self._root_identity = self._identity(self._root)
            self._executable_digest = _file_digest(self._executable)
            self._file_arguments: list[tuple[Path, Path, str]] = []
            for argument in definition.subcommand:
                path = Path(argument)
                if path.is_absolute() and path.is_file():
                    resolved = path.resolve(strict=True)
                    if not resolved.is_relative_to(self._root):
                        raise ValueError("Script outside working scope")
                    self._file_arguments.append((path, resolved, _file_digest(resolved)))
        except (OSError, ValueError, TypeError, OverflowError):
            raise ToolExecutionError("TOOL_CONFIGURATION") from None

    @staticmethod
    def _identity(path: Path) -> tuple[int, int]:
        info = path.stat()
        return info.st_dev, info.st_ino

    def _verify(self) -> None:
        try:
            if (self.definition.model_dump_json() != self._definition_json
                    or Path(self.definition.executable).resolve(strict=True) != self._executable
                    or Path(self.definition.working_directory).resolve(strict=True) != self._directory
                    or self._identity(self._root) != self._root_identity
                    or self._identity(self._directory) != self._directory_identity
                    or not self._directory.is_relative_to(self._root)
                    or _file_digest(self._executable) != self._executable_digest):
                raise ValueError("Pin changed")
            for path, resolved, digest in self._file_arguments:
                if path.resolve(strict=True) != resolved or _file_digest(resolved) != digest:
                    raise ValueError("Script pin changed")
        except (OSError, ValueError):
            raise ToolExecutionError("TOOL_CONFIGURATION") from None

    def _environment(self) -> dict[str, str]:
        return {name: value for name, value in os.environ.items() if name.upper() in self._environment_names}

    def execute(self, payload: dict) -> dict:
        self._verify()
        try:
            if not isinstance(payload, dict):
                raise ValueError("Object required")
            encoded = json.dumps(payload, allow_nan=False, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if len(encoded) > INPUT_BYTES:
                raise ValueError("Input limit")
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise ToolExecutionError("TOOL_INPUT") from None
        deadline = time.monotonic() + self.timeout_seconds
        try:
            process = subprocess.Popen(
                [str(self._executable), *self._subcommand], cwd=str(self._directory),
                env=self._environment(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, shell=False, bufsize=0,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except (OSError, ValueError):
            raise ToolExecutionError("TOOL_START") from None
        stdout = bytearray()
        counter = [0]
        lock = threading.Lock()
        overflow = threading.Event()
        io_error = threading.Event()
        finished = [threading.Event() for _ in range(3)]

        def read(stream, keep: bool, done: threading.Event):
            try:
                while chunk := stream.read(4096):
                    with lock:
                        counter[0] += len(chunk)
                        if counter[0] > self.output_bytes:
                            overflow.set()
                            break
                        if keep:
                            stdout.extend(chunk)
            except (OSError, ValueError):
                io_error.set()
            finally:
                stream.close()
                done.set()

        def write():
            try:
                offset = 0
                while offset < len(encoded):
                    written = process.stdin.write(encoded[offset:offset + 4096])
                    if not written:
                        raise OSError("Closed input")
                    offset += written
            except (OSError, ValueError):
                io_error.set()
            finally:
                process.stdin.close()
                finished[0].set()

        threads = [threading.Thread(target=write, daemon=True),
                   threading.Thread(target=read, args=(process.stdout, True, finished[1]), daemon=True),
                   threading.Thread(target=read, args=(process.stderr, False, finished[2]), daemon=True)]
        for thread in threads:
            thread.start()
        failure = None
        try:
            while True:
                if overflow.is_set():
                    failure = "TOOL_OUTPUT_LIMIT"
                    break
                if time.monotonic() >= deadline:
                    failure = "TOOL_TIMEOUT"
                    break
                if all(event.is_set() for event in finished) and process.poll() is not None:
                    break
                overflow.wait(min(0.01, max(0, deadline - time.monotonic())))
        finally:
            if process.poll() is None:
                try:
                    process.terminate()
                    try:
                        process.wait(timeout=0.25)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=1)
                except (OSError, subprocess.TimeoutExpired):
                    failure = failure or "TOOL_IO"
            for thread in threads:
                thread.join(timeout=0.25)
        if failure:
            raise ToolExecutionError(failure) from None
        if process.returncode != 0:
            raise ToolExecutionError("TOOL_EXIT") from None
        if io_error.is_set():
            raise ToolExecutionError("TOOL_IO") from None
        try:
            result = strict_json(stdout.decode("utf-8"))
            if not isinstance(result, dict):
                raise ValueError("Object required")
            return result
        except (ValueError, UnicodeError, RecursionError):
            raise ToolExecutionError("TOOL_JSON") from None
