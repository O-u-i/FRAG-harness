"""Bind a preview to the exact reviewed package and local adapter implementation."""
from __future__ import annotations

import hashlib
from pathlib import Path

from frag_api.errors import RagNotReadyError
from frag_api.request_spec import fingerprint

PI_ADAPTER = {"name": "pi-openai-responses", "version": "1.0.0",
              "piCommit": "a13d35a742c6ef8462812a28fbe1d8c8b7431c32", "protocolVersion": 1, "wireVersion": 1}
MANIFEST_HASH = "378bb2d79b440bbba3a77c9c24de0a4de4335419bbce9f4edd68ca4e348c88dd"
WORKER_FILES = ("worker.mjs", "wire.mjs", "verify-package.mjs")
HOST_FILES = ("pi.py", "pi_process.py", "pi_integrity.py", "llm.py", "prepared.py", "research_native.py", "response_items.py")


def adapter_binding() -> dict:
    provider_root = Path(__file__).resolve().parent
    worker_root = provider_root.parents[1] / "pi-worker"
    def digest(path):
        if path.is_symlink() or not path.is_file():
            raise RagNotReadyError()
        return hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        manifest_hash = digest(worker_root / "vendor/pi-ai/selection-manifest.json")
        if manifest_hash != MANIFEST_HASH:
            raise RagNotReadyError()
        worker_files = {name: digest(worker_root / name) for name in WORKER_FILES}
        host_files = {name: digest(provider_root / name) for name in HOST_FILES}
        packages = {name: digest(worker_root / name) for name in ("package.json", "package-lock.json")}
    except OSError:
        raise RagNotReadyError() from None
    return {**PI_ADAPTER, "selectionManifestHash": manifest_hash, "workerFiles": worker_files,
            "hostAdapterHash": fingerprint({"providers": host_files, "packages": packages})}
