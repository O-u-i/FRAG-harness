"""Project notices must survive the Host and VSIX packaging paths."""
import json
from pathlib import Path
import runpy
import tomllib
import xml.etree.ElementTree as ET
import zipfile
from hashlib import sha256


ROOT = Path(__file__).resolve().parents[2]


def test_mit_metadata_and_package_notices(tmp_path):
    license_text = (ROOT / 'LICENSE').read_bytes()
    assert license_text == (ROOT / 'backend/LICENSE').read_bytes()
    for name in ['package.json', 'integrations/vscode/bridge/package.json']:
        assert json.loads((ROOT / name).read_text())['license'] == 'MIT'
    assert json.loads((ROOT / 'package-lock.json').read_text())['packages']['']['license'] == 'MIT'
    metadata = tomllib.loads((ROOT / 'backend/pyproject.toml').read_text())
    assert metadata['project']['license'] == 'MIT'
    assert metadata['project']['license-files'] == ['LICENSE']

    # Exercise the real packager with synthetic inputs, never a live FC service.
    package = runpy.run_path(str(ROOT / 'scripts/package-agents.py'))
    build = package['build']
    state = build.__globals__
    root = tmp_path / 'source'
    view = tmp_path / 'view'
    out = tmp_path / 'output'
    state.update(ROOT=root, VIEW=view, OUT=out, BACKEND=[])

    def write(name, value):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value if isinstance(value, bytes) else value.encode())

    for name in ['LICENSE', 'backend/LICENSE', 'backend/pyproject.toml',
                 'backend/uv.lock', 'integrations/vscode/README.md',
                 'integrations/finance-core-LICENSE.txt',
                 'integrations/vscode/install-host.ps1',
                 'integrations/vscode/bridge/package.json',
                 'integrations/vscode/bridge/extension.cjs',
                 'integrations/vscode/bridge/host-launcher.cjs',
                 'integrations/vscode/bridge/tool-result.cjs',
                 'integrations/vscode/bridge/README.md']:
        write(name, (ROOT / name).read_bytes())
    reader = tmp_path / 'synthetic-reader.zip'
    reader.write_bytes(b'synthetic reader fixture; no financial records')
    write('backend/frag_api/fc_reader.py',
          f'FC_ARCHIVE_SHA256 = "{sha256(reader.read_bytes()).hexdigest()}"\n')
    locked = {'packages': {}}
    for name in ['react', 'react-dom', 'scheduler']:
        locked['packages']['node_modules/' + name] = {'version': '0.0.0'}
        write(f'node_modules/{name}/package.json', json.dumps({'version': '0.0.0'}))
        write(f'node_modules/{name}/LICENSE', f'Synthetic {name} license fixture\n')
    write('package-lock.json', json.dumps(locked))
    (view / 'assets').mkdir(parents=True)
    (view / 'index.html').write_text(
        '<script src="./assets/main.js"></script><link href="./assets/main.css">')
    (view / 'assets/main.js').write_text('// synthetic bundle')
    (view / 'assets/main.css').write_text('/* synthetic stylesheet */')
    build(reader)

    with zipfile.ZipFile(out / f'frag-host-{state["VERSION"]}.zip') as host:
        assert host.read('backend/LICENSE') == license_text
        assert host.read('resources/licenses/FRAG-harness-LICENSE.txt') == license_text
        assert host.read('resources/licenses/Finance-Core-LICENSE.txt') == (
            ROOT / 'integrations/finance-core-LICENSE.txt').read_bytes()
        assert 'Finance Core official reader 1.10.0: MIT' in host.read(
            'resources/licenses/THIRD_PARTY_NOTICES.txt').decode()
        assert host.read('resources/finance-core/finance-core-frag-plugin-v1.10.0.zip') == reader.read_bytes()
        for name in ['react', 'react-dom', 'scheduler']:
            assert host.read(f'resources/licenses/{name}-LICENSE.txt') == (
                root / f'node_modules/{name}/LICENSE').read_bytes()
        assert "'backend\\LICENSE'" in host.read('install-host.ps1').decode()
    with zipfile.ZipFile(out / f'frag-bridge-{state["VERSION"]}.vsix') as vsix:
        assert vsix.read('extension/LICENSE.txt') == license_text
        manifest = ET.fromstring(vsix.read('extension.vsixmanifest'))
        ns = {'v': 'http://schemas.microsoft.com/developer/vsx-schema/2011'}
        asset = manifest.find(
            "v:Assets/v:Asset[@Type='Microsoft.VisualStudio.Services.Content.License']", ns)
        assert asset is not None and asset.attrib['Path'] == 'extension/LICENSE.txt'
        types = ET.fromstring(vsix.read('[Content_Types].xml'))
        ns = {'c': 'http://schemas.openxmlformats.org/package/2006/content-types'}
        assert types.find("c:Default[@Extension='txt']", ns).attrib['ContentType'] == 'text/plain'
