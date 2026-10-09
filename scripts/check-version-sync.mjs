import { readFileSync } from 'node:fs';
const read=p=>readFileSync(p,'utf8');
const manifest=JSON.parse(read('package.json')), lock=JSON.parse(read('package-lock.json'));
const version=manifest.version;
const checks={
 'package locks':lock.version===version&&lock.packages[''].version===version,
 'backend version':read('backend/pyproject.toml').includes(`version = "${version}"`) && read('backend/uv.lock').includes(`name = "frag-harness-backend"\nversion = "${version}"`),
 'health version':read('backend/frag_api/main.py').includes(`VERSION = "${version}"`),
 'source contract':read('backend/frag_api/schemas/governance.py').includes(`HOST_VERSION = "${version}"`),
 'Webview title':read('index.html').includes(`<title>FRAG ${version}</title>`)&&read('src/management/main.tsx').includes(`<span>${version}</span>`),
 'VSIX manifest':JSON.parse(read('integrations/vscode/bridge/package.json')).version===version,
 'launcher':read('integrations/vscode/bridge/host-launcher.cjs').includes(`VERSION = '${version}'`),
 'installer':read('integrations/vscode/install-host.ps1').includes(`FRAG\u005c\u005chost\u005c\u005c${version}`)||read('integrations/vscode/install-host.ps1').includes(`FRAG\\host\\${version}`),
 'README':read('README.md').startsWith(`# FRAG-harness ${version}`),
 'diagram':JSON.parse(read('docs/architecture/native-tools/workflow.json')).meta.title.includes(version),
};
for(const path of ['README.md','integrations/vscode/README.md','integrations/vscode/bridge/README.md']) {
 const refs=[...read(path).matchAll(/frag-(?:host|bridge)-(\d+\.\d+\.\d+)\.(?:zip|vsix)/g)];
 checks[path+' examples']=refs.every(m=>m[1]===version);
}
const bad=Object.entries(checks).filter(([,ok])=>!ok).map(([label])=>label);
if(bad.length) throw new Error('Version mismatch: '+bad.join(', '));
console.log(`Version surfaces synchronized: ${version}.`);
