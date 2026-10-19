"""Build private matching native evidence backend/VSIX packages, no legacy assets."""
from hashlib import sha256
from datetime import datetime, timezone
from pathlib import Path
import json
import re
import zipfile
ROOT=Path(__file__).resolve().parent.parent
VERSION=json.loads((ROOT/'package.json').read_text())['version']
DELIVERY=ROOT/'packages'/f'v{VERSION}'
OUT=DELIVERY
VIEW=ROOT/'.tmp/agents-dist'
BACKEND=['__init__.py','__main__.py','host.py','main.py','fc_reader.py','fc_connection.py','errors.py','request_spec.py','schemas/__init__.py','schemas/context_source.py','schemas/governance.py','schemas/memory.py','schemas/plugin.py','schemas/native.py','services/__init__.py','services/context_source_service.py','services/rag_markdown.py','services/memory_service.py','services/runtime_policy.py','services/source_index.py','services/evidence_tools.py','repositories/__init__.py','repositories/rag_index_repository.py','repositories/tool_store.py']
BACKEND += ['schemas/workflow.py', 'repositories/workflow_store.py',
    'services/workflow_budget.py', 'services/recommendation_workflow.py']

def put(archive,source,destination):
    if not source.is_file() or source.is_symlink():
        raise ValueError('Missing or linked package input: '+str(source.relative_to(ROOT)))
    archive.writestr(destination,source.read_bytes())

def build(fc_archive):
    pin=re.search(r'^FC_ARCHIVE_SHA256 = "([a-f0-9]{64})"$',(ROOT/'backend/frag_api/fc_reader.py').read_text(),re.M).group(1)
    if not fc_archive.is_file() or fc_archive.is_symlink() or sha256(fc_archive.read_bytes()).hexdigest()!=pin:
        raise ValueError('Supply the exact byte-pinned official Finance Core reader archive.')
    OUT.mkdir(parents=True,exist_ok=True)
    if not (VIEW/'index.html').is_file():raise ValueError('Build the management Webview first.')
    manifest=json.loads((ROOT/'integrations/vscode/bridge/package.json').read_text())
    if manifest['version']!=VERSION:raise ValueError('Backend and VSIX must match exactly.')
    host=OUT/f'frag-host-{VERSION}.zip'
    with zipfile.ZipFile(host,'w',zipfile.ZIP_DEFLATED) as archive:
        for name in BACKEND:put(archive,ROOT/'backend/frag_api'/name,'backend/frag_api/'+name)
        for name in ['pyproject.toml','uv.lock']:put(archive,ROOT/'backend'/name,'backend/'+name)
        put(archive,ROOT/'backend/LICENSE','backend/LICENSE')
        put(archive,ROOT/'LICENSE','resources/licenses/FRAG-harness-LICENSE.txt')
        # Only assets referenced by this build's entrypoint; stale fixed-cache output is never bundled.
        html=(VIEW/'index.html').read_text()
        assets=re.findall(r'(?:src|href)="\./(assets/[^"?#]+)"',html)
        if len(assets)!=2 or any('..' in Path(name).parts for name in assets):raise ValueError('Unexpected Webview entry assets.')
        put(archive,VIEW/'index.html','resources/dist/index.html')
        for name in assets:put(archive,VIEW/name,'resources/dist/'+name)
        put(archive,ROOT/'integrations/vscode/README.md','resources/install.md')
        put(archive,ROOT/'integrations/vscode/install-host.ps1','install-host.ps1')
        put(archive,fc_archive,'resources/finance-core/finance-core-frag-plugin-v1.10.0.zip')
        put(archive,ROOT/'integrations/finance-core-LICENSE.txt','resources/licenses/Finance-Core-LICENSE.txt')
        put(archive,ROOT/'integrations/dracula-LICENSE.txt','resources/licenses/Dracula-LICENSE.txt')
        notices=['Finance Core official reader 1.10.0: MIT; original license in Finance-Core-LICENSE.txt. The byte-pinned reader archive is unchanged.']
        notices.append('Dracula palette: MIT, Copyright (c) 2023 Dracula Theme; original license in Dracula-LICENSE.txt. Colors adapted for accessible muted text; no theme code copied. Source commit e22ebcc048b8aff586f9bc94db30ff5347070b42.')
        locked=json.loads((ROOT/'package-lock.json').read_text())['packages']
        for name in ['react','react-dom','scheduler']:
            package=ROOT/'node_modules'/name
            version=json.loads((package/'package.json').read_text())['version']
            if locked['node_modules/'+name]['version']!=version:raise ValueError('Installed dependency differs from lock.')
            put(archive,package/'LICENSE',f'resources/licenses/{name}-LICENSE.txt')
            notices.append(f'{name} {version}: MIT; original license in {name}-LICENSE.txt')
        notices.append('Backend wheels and Python/uv are not bundled; install locked dependencies separately.')
        archive.writestr('resources/licenses/THIRD_PARTY_NOTICES.txt','\n'.join(notices)+'\n')
    bridge=ROOT/'integrations/vscode/bridge'
    vsix=OUT/f'frag-bridge-{VERSION}.vsix'
    with zipfile.ZipFile(vsix,'w',zipfile.ZIP_DEFLATED) as archive:
        for name in ['package.json','extension.cjs','host-launcher.cjs','tool-result.cjs','acceptance-workspace.cjs','README.md']:put(archive,bridge/name,'extension/'+name)
        put(archive,ROOT/'LICENSE','extension/LICENSE.txt')
        archive.writestr('[Content_Types].xml','''<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="json" ContentType="application/json"/><Default Extension="cjs" ContentType="application/javascript"/><Default Extension="md" ContentType="text/markdown"/><Default Extension="txt" ContentType="text/plain"/><Default Extension="vsixmanifest" ContentType="text/xml"/></Types>''')
        archive.writestr('extension.vsixmanifest',f'''<?xml version="1.0" encoding="UTF-8"?><PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011"><Metadata><Identity Language="en-US" Id="frag-bridge" Version="{VERSION}" Publisher="frag-local"/><DisplayName>FRAG Evidence Tools</DisplayName><Description xml:space="preserve">Read-only evidence tools for the native Local Agent.</Description><Properties><Property Id="Microsoft.VisualStudio.Code.Engine" Value="^1.140.0"/><Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="ui"/></Properties></Metadata><Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation><Dependencies/><Assets><Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/><Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/README.md" Addressable="true"/><Asset Type="Microsoft.VisualStudio.Services.Content.License" Path="extension/LICENSE.txt" Addressable="true"/></Assets></PackageManifest>''')
    receipt=[{'file':p.name,'bytes':p.stat().st_size,'sha256':sha256(p.read_bytes()).hexdigest(),'artifactWrittenAt':datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat()} for p in [host,vsix]]
    (OUT/f'receipt-{VERSION}.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,default=OUT);parser.add_argument('--fc-archive',type=Path,required=True);args=parser.parse_args();OUT=args.output_dir.resolve()
    if OUT!=DELIVERY and not OUT.is_relative_to((ROOT/'.tmp').resolve()):raise ValueError('Packages must use the current versioned delivery directory or ignored .tmp.')
    build(args.fc_archive.resolve())
