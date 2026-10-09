import { readFileSync, existsSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
const files = directory => readdirSync(directory,{withFileTypes:true}).flatMap(entry => entry.isDirectory() ? files(join(directory,entry.name)) : [join(directory,entry.name)]);
const violations=[];
for(const file of files('backend/frag_api').filter(p=>p.endsWith('.py'))) {
 const text=readFileSync(file,'utf8');
 if(/^(?:from|import)\s+(?:openai|langgraph|langchain|frag_api\.(?:providers|routers|schemas\.(?:harness|research|runtime|agents)|services\.(?:research|agent_host|harness|governed)))(?:\b|\.)/m.test(text)) violations.push(file+': retired runtime import');
 if(/^(?:from|import)\s+(?:finance_core|sfos_api)\b/m.test(text)) violations.push(file+': financial ownership violation');
}
const extension=readFileSync('integrations/vscode/bridge/extension.cjs','utf8');
if(/sendRequest|registerChatParticipant|modelConfigFile|chat\.remoteAgentHosts|workbench\.action\.chat\.open|chat\/turnComplete|toolInvocationToken/.test(extension)) violations.push('Extension contains retired chat/model ownership');
for(const file of files('src').filter(p=>/\.(tsx?|jsx?)$/.test(p))) {
 if(!file.includes('management')&&!file.endsWith('vite-env.d.ts')) violations.push(file+': obsolete frontend');
 if(/\bfetch\(|XMLHttpRequest|FRAG_EXTENSION_TOKEN|FINANCE_CORE_PLUGIN_READ_TOKEN|sendRequest|chat\.open/.test(readFileSync(file,'utf8'))) violations.push(file+': Webview crosses extension/credential boundary');
}
for(const name of ['langgraph','openai']) if(readFileSync('backend/pyproject.toml','utf8').includes('"'+name)) violations.push('Retired dependency: '+name);
const manifest=JSON.parse(readFileSync('integrations/vscode/bridge/package.json','utf8'));
if(JSON.stringify(manifest.contributes.languageModelTools.map(t=>t.name).sort()) !== JSON.stringify(['frag_fc_read','frag_read','frag_search'])) violations.push('Native tool surface drift');
for(const path of ['backend/frag_api/plugin_host.py','integrations/vscode/bridge/model-bridge.cjs','agents.html','plugins/kb/adapter.py']) if(existsSync(path)) violations.push('Retired executable still exists: '+path);
if(violations.length) throw new Error(violations.join('\n'));
console.log('Native ownership, source authority, no credential Webview and retired-path boundaries passed.');
