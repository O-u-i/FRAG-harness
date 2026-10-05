from __future__ import annotations

import hashlib
import json
import io
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path

from frag_api.plugin_host import PLUGIN_ID, VERSION_PATTERN, _is_reparse_point, valid_plugin_id

PROJECT_ROOT = Path(__file__).resolve().parents[3]
INSTALLER = PROJECT_ROOT / "scripts" / "install-plugin.ps1"
MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
SHA256_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")


class PluginManagementError(Exception):
    def __init__(self, code: str, message: str, status: int = 422):
        self.code = code
        self.message = message
        self.status = status


def package_state(root: Path, plugin_id: str = PLUGIN_ID) -> tuple[str | None, bool | None]:
    if not valid_plugin_id(plugin_id):
        return None, None
    current = root / plugin_id / "current.json"
    try:
        if (any(_is_reparse_point(path) for path in (root, root / plugin_id, current))
                or not current.is_file() or current.stat().st_size > 16 * 1024):
            return None, None
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


def install_archive(root: Path, archive: bytes, expected_sha256: str) -> str:
    if not SHA256_PATTERN.fullmatch(expected_sha256):
        raise PluginManagementError("INVALID_SHA256", "Enter a 64-character SHA-256 value.")
    if not archive or len(archive) > MAX_ARCHIVE_BYTES:
        raise PluginManagementError("ARCHIVE_SIZE_INVALID", "Archive must be at most 20 MiB.")
    if hashlib.sha256(archive).hexdigest() != expected_sha256.lower():
        raise PluginManagementError("ARCHIVE_HASH_MISMATCH", "Archive SHA-256 does not match the pinned value.")
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as package:
            if len(package.namelist()) != 3 or set(package.namelist()) != {"manifest.json", "adapter.py", "ui.js"}:
                raise ValueError()
            if package.getinfo("manifest.json").file_size > 64 * 1024:
                raise ValueError()
            manifest = json.loads(package.read("manifest.json").decode("utf-8-sig"))
            plugin_id = manifest.get("id")
            if not valid_plugin_id(plugin_id):
                raise ValueError()
    except (ValueError, AttributeError, OSError, zipfile.BadZipFile, KeyError) as error:
        raise PluginManagementError("PLUGIN_PACKAGE_REJECTED", "Plugin package failed validation or installation.") from error
    temporary_root = PROJECT_ROOT / ".tmp" / "plugin-uploads"
    for candidate in (temporary_root.parent, temporary_root):
        if candidate.is_symlink() or candidate.is_junction():
            raise PluginManagementError("PLUGIN_MANAGEMENT_FAILED", "Plugin upload path is unavailable.", 503)
    temporary_root.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=temporary_root, suffix=".zip", delete=False) as temporary:
        archive_path = Path(temporary.name)
        temporary.write(archive)
    try:
        _run_installer("-ArchivePath", str(archive_path), "-ExpectedSha256", expected_sha256, "-PluginId", plugin_id, root=root)
    finally:
        archive_path.unlink(missing_ok=True)
    return plugin_id


def uninstall_plugin(root: Path, plugin_id: str = PLUGIN_ID) -> None:
    if package_state(root, plugin_id)[0] is None:
        raise PluginManagementError("PLUGIN_NOT_INSTALLED", "Plugin is not installed.", 409)
    raise PluginManagementError("PLUGIN_MANUAL_REMOVAL_REQUIRED",
        f"Disable the plugin, stop FRAG, and manually remove .local-plugins/{plugin_id} under the configured plugin root. No files were deleted.", 409)


def set_plugin_enabled(root: Path, enabled: bool, plugin_id: str = PLUGIN_ID) -> None:
    if package_state(root, plugin_id)[0] is None:
        raise PluginManagementError("PLUGIN_NOT_INSTALLED", "Plugin is not installed.", 409)
    _run_installer("-Enable" if enabled else "-Disable", "-PluginId", plugin_id, root=root)
