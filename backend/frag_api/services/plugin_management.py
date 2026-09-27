from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

from frag_api.plugin_host import PLUGIN_ID, VERSION_PATTERN

PROJECT_ROOT = Path(__file__).resolve().parents[3]
INSTALLER = PROJECT_ROOT / "scripts" / "install-plugin.ps1"
MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
SHA256_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")


class PluginManagementError(Exception):
    def __init__(self, code: str, message: str, status: int = 422):
        self.code = code
        self.message = message
        self.status = status


def package_state(root: Path) -> tuple[str | None, bool | None]:
    current = root / PLUGIN_ID / "current.json"
    if not current.is_file() or current.is_symlink() or current.stat().st_size > 16 * 1024:
        return None, None
    try:
        value = json.loads(current.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None, None
    version = value.get("version") if isinstance(value, dict) else None
    if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
        return None, None
    enabled = value.get("enabled")
    return version, enabled if isinstance(enabled, bool) else None


def _run_installer(*args: str, root: Path) -> None:
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(INSTALLER),
             *args, "-InstallRoot", str(root)],
            cwd=PROJECT_ROOT, capture_output=True, timeout=90, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PluginManagementError("PLUGIN_MANAGEMENT_FAILED", "Plugin operation could not complete.", 503) from error
    if result.returncode:
        raise PluginManagementError("PLUGIN_PACKAGE_REJECTED", "Plugin package failed validation or installation.")


def install_archive(root: Path, archive: bytes, expected_sha256: str) -> None:
    if not SHA256_PATTERN.fullmatch(expected_sha256):
        raise PluginManagementError("INVALID_SHA256", "Enter a 64-character SHA-256 value.")
    if not archive or len(archive) > MAX_ARCHIVE_BYTES:
        raise PluginManagementError("ARCHIVE_SIZE_INVALID", "Archive must be at most 20 MiB.")
    if hashlib.sha256(archive).hexdigest() != expected_sha256.lower():
        raise PluginManagementError("ARCHIVE_HASH_MISMATCH", "Archive SHA-256 does not match the pinned value.")
    temporary_root = PROJECT_ROOT / ".tmp" / "plugin-uploads"
    for candidate in (temporary_root.parent, temporary_root):
        if candidate.is_symlink() or candidate.is_junction():
            raise PluginManagementError("PLUGIN_MANAGEMENT_FAILED", "Plugin upload path is unavailable.", 503)
    temporary_root.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=temporary_root, suffix=".zip", delete=False) as temporary:
        archive_path = Path(temporary.name)
        temporary.write(archive)
    try:
        _run_installer("-ArchivePath", str(archive_path), "-ExpectedSha256", expected_sha256, root=root)
    finally:
        archive_path.unlink(missing_ok=True)


def uninstall_plugin(root: Path) -> None:
    if package_state(root)[0] is None:
        raise PluginManagementError("PLUGIN_NOT_INSTALLED", "Finance Core plugin is not installed.", 409)
    _run_installer("-Uninstall", root=root)


def set_plugin_enabled(root: Path, enabled: bool) -> None:
    if package_state(root)[0] is None:
        raise PluginManagementError("PLUGIN_NOT_INSTALLED", "Finance Core plugin is not installed.", 409)
    _run_installer("-Enable" if enabled else "-Disable", root=root)
