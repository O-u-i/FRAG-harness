"""Build the original KB plugin's deterministic three-file archive."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / "plugins/kb"
manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
manifest["files"] = {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in ("adapter.py", "ui.js")}
(source / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
output = ROOT / f"docs/release/kb-frag-plugin-v{manifest['version']}.zip"
with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for name in ("manifest.json", "adapter.py", "ui.js"):
        entry = zipfile.ZipInfo(name, date_time=(2026, 10, 5, 0, 0, 0))
        entry.compress_type = zipfile.ZIP_DEFLATED
        entry.external_attr = 0o100644 << 16
        archive.writestr(entry, (source / name).read_bytes())
print(f"{output.name}: {hashlib.sha256(output.read_bytes()).hexdigest()}")
