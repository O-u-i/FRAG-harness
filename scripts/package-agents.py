"""Build private local Host/VSIX packages from explicit application file allowlists."""
from hashlib import sha256
from pathlib import Path
import json
import zipfile

ROOT = Path(__file__).resolve().parent.parent
VERSION = json.loads((ROOT / "package.json").read_text())["version"]
OUT = ROOT / ".tmp/packages"
REVIEW = ROOT / ".tmp/agents-dist"


def put(archive, source, destination):
    if not source.is_file() or source.is_symlink():
        raise ValueError(f"Missing or linked package input: {source.relative_to(ROOT)}")
    archive.writestr(destination, source.read_bytes())


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    if not (REVIEW / "agents.html").is_file():
        raise ValueError("Build the review frontend before packaging.")
    host = OUT / f"frag-host-{VERSION}.zip"
    with zipfile.ZipFile(host, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted((ROOT / "backend/frag_api").rglob("*.py")):
            put(archive, file, file.relative_to(ROOT).as_posix())
        for name in ("pyproject.toml", "uv.lock"):
            put(archive, ROOT / "backend" / name, "backend/" + name)
        for file in sorted(REVIEW.rglob("*")):
            if file.is_file():
                # Vite production output only; source maps and arbitrary public inputs are excluded.
                relative = file.relative_to(REVIEW)
                if relative.as_posix() == "agents.html":
                    put(archive, file, "resources/dist/index.html")
                elif relative.parts[0] in {"assets", "agents"}:
                    if file.suffix != ".map":
                        if "PublicSans" in file.name or "LibreBodoni" in file.name:
                            raise ValueError("Standalone fonts must not enter the review package.")
                        put(archive, file, "resources/dist/" + relative.as_posix())
        for name in ("synthetic-risk-review.md", "eval-cases.json"):
            put(archive, ROOT / "shared/demo/rag" / name, "resources/demo/rag/" + name)
        put(archive, ROOT / "src/agents/README.md", "resources/review.md")
        put(archive, ROOT / "integrations/vscode/install-host.ps1", "install-host.ps1")
        notices = []
        for name in ("react", "react-dom", "scheduler", "zod"):
            package = ROOT / "node_modules" / name
            version = json.loads((package / "package.json").read_text())["version"]
            put(archive, package / "LICENSE", f"resources/licenses/{name}-LICENSE.txt")
            notices.append(f"{name} {version}: MIT; original license in {name}-LICENSE.txt")
        notices.extend(["Archivo Variable 5.3.0: OFL-1.1; resources/dist/agents/fonts/ARCHIVO-OFL.txt",
                        "User-supplied React Bits references: resources/dist/agents/REACT-BITS-LICENSE.md",
                        "Backend wheels and Python/uv are not bundled. Install locked dependencies separately."])
        archive.writestr("resources/licenses/THIRD_PARTY_NOTICES.txt", "\n".join(notices) + "\n")
    bridge = ROOT / "integrations/vscode/bridge"
    manifest = json.loads((bridge / "package.json").read_text())
    if manifest["version"] != VERSION:
        raise ValueError("VSIX version must match Host version.")
    vsix = OUT / f"frag-bridge-{VERSION}.vsix"
    with zipfile.ZipFile(vsix, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("package.json", "extension.cjs", "host-launcher.cjs", "model-bridge.cjs", "README.md"):
            put(archive, bridge / name, "extension/" + name)
        archive.writestr("[Content_Types].xml", '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="json" ContentType="application/json"/><Default Extension="cjs" ContentType="application/javascript"/><Default Extension="md" ContentType="text/markdown"/><Default Extension="vsixmanifest" ContentType="text/xml"/></Types>''')
        archive.writestr("extension.vsixmanifest", f'''<?xml version="1.0" encoding="UTF-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011"><Metadata><Identity Language="en-US" Id="frag-bridge" Version="{VERSION}" Publisher="frag-local"/><DisplayName>FRAG Local Host</DisplayName><Description xml:space="preserve">Governed project conversation and VS Code model bridge.</Description><Properties><Property Id="Microsoft.VisualStudio.Code.Engine" Value="^1.140.0"/><Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="ui"/></Properties></Metadata><Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation><Dependencies/><Assets><Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/><Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/README.md" Addressable="true"/></Assets></PackageManifest>''')
    receipt = [{"file": file.name, "bytes": file.stat().st_size, "sha256": sha256(file.read_bytes()).hexdigest()}
               for file in (host, vsix)]
    (OUT / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    build()
