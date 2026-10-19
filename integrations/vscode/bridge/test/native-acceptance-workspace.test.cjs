'use strict';
const test = require('node:test'), assert = require('node:assert/strict'), vm = require('node:vm');
const fs = require('node:fs'), path = require('node:path'), { execFileSync } = require('node:child_process');
const { workspaceInfo, prepareWorkspace } = require('../acceptance-workspace.cjs');
const projectRoot = path.resolve(__dirname, '../../../..');
const allocator = path.join(projectRoot, 'scripts', 'maintain-tmp.ps1');
const run = execFileSync('pwsh', ['-NoProfile','-File',allocator,'-NewRun','bridge-acceptance','-Disposable','-OwnerProcessId',String(process.pid)], { encoding: 'utf8' }).trim();
test.after(() => execFileSync('pwsh', ['-NoProfile','-File',allocator,'-CloseRun',run], { encoding: 'utf8' }));
function owned(name) {
  const base = path.join(run, name), id = 'a'.repeat(64);
  return { id, project: path.join(base, 'project'), installation: path.join(base, 'host'), state: path.join(base, 'private', 'projects', id) };
}

test('workspace info is read-only and exact; preparation is per project and preserves edits', () => {
  const host = owned('normal'), initial = workspaceInfo(host);
  assert.deepEqual(initial, { root: path.join(host.state, 'acceptance'), sourceRoot: path.join(host.state, 'acceptance', 'sources'), planPath: path.join(host.state, 'acceptance', 'sources', 'synthetic-plan.md'), prepared: false });
  assert.equal(fs.existsSync(host.state), false);
  const prepared = prepareWorkspace(host);
  assert.equal(prepared.prepared, true);
  assert.match(fs.readFileSync(prepared.planPath,'utf8'), /BEGIN-PLAN-AB[\s\S]*END-PLAN-AB/);
  const edited = '# Synthetic edited plan\nPreserve this test revision.\n';
  fs.writeFileSync(prepared.planPath, edited);
  assert.deepEqual(prepareWorkspace(host), prepared);
  assert.equal(fs.readFileSync(prepared.planPath,'utf8'), edited);
  const custom = path.join(run, 'custom');
  const selected = workspaceInfo(host, custom);
  assert.equal(selected.root, path.join(custom, 'projects', host.id, 'acceptance'));
  assert.notEqual(selected.root, workspaceInfo({ ...host, id: 'b'.repeat(64) }, custom).root);
  assert.equal(fs.existsSync(custom), false);
});

test('unsafe roots and project/Host/state overlaps fail before creation', () => {
  const host = owned('invalid');
  for (const root of ['relative/path', ' padded ', path.parse(run).root, '//server/share', '\\\\server\\share', host.project, path.join(host.project,'child'), host.installation, path.join(host.state,'child'), path.dirname(host.project)]) {
    assert.throws(() => prepareWorkspace(host, root), /ACCEPTANCE_ROOT_/);
  }
  assert.throws(() => workspaceInfo({...host,id:'not-a-project'}), /ACCEPTANCE_PROJECT_INVALID/);
  assert.equal(fs.existsSync(path.dirname(host.project)), false);
});

test('foreign files and linked target files never get overwritten', () => {
  const foreign = owned('foreign'), info = workspaceInfo(foreign);
  fs.mkdirSync(info.root, { recursive: true });
  const unrelated = path.join(info.root, 'existing.txt'); fs.writeFileSync(unrelated, 'synthetic existing content');
  assert.throws(() => prepareWorkspace(foreign), /ACCEPTANCE_WORKSPACE_NOT_EMPTY/);
  assert.equal(fs.readFileSync(unrelated,'utf8'),'synthetic existing content');
  assert.equal(fs.existsSync(path.join(info.root,'README.md')),false);
  const hard = owned('hardlink'), prepared = prepareWorkspace(hard);
  const alias = path.join(run,'hardlink-alias.txt'); fs.linkSync(prepared.planPath, alias);
  assert.throws(() => workspaceInfo(hard), /ACCEPTANCE_PATH_UNSAFE/);
  assert.throws(() => prepareWorkspace(hard), /ACCEPTANCE_PATH_UNSAFE/);
});

test('directory links and non-directory ancestors are rejected without writing through them', () => {
  const host = owned('linked'), target = path.join(run,'linked-target'); fs.mkdirSync(target);
  fs.mkdirSync(path.dirname(host.state), { recursive: true });
  fs.symlinkSync(target, host.state, process.platform === 'win32' ? 'junction' : 'dir');
  try {
    assert.throws(() => prepareWorkspace(host), /ACCEPTANCE_PATH_UNSAFE/);
    assert.deepEqual(fs.readdirSync(target),[]);
  } finally { if (fs.lstatSync(host.state).isSymbolicLink()) fs.unlinkSync(host.state); }
  const blocked = owned('blocked'); fs.mkdirSync(path.dirname(blocked.state), { recursive:true }); fs.writeFileSync(blocked.state,'synthetic blocker');
  assert.throws(() => workspaceInfo(blocked), /ACCEPTANCE_PATH_UNSAFE|ACCEPTANCE_PATH_UNAVAILABLE/);
});

test('native acceptance actions stay local and picker persists only validated machine selection', async () => {
  const commands = new Map(), replies = [], requests = [], updates = [], editors = [], opened = [];
  const host = { ...owned('extension'), child: { exitCode:null, signalCode:null }, async stop(){}, async request(route){ requests.push(route); return {}; } };
  let handler, selection, configured = '';
  const config = { get: key => key === 'acceptanceRoot' ? configured : '', async update(key,value,target){ updates.push({key,value,target}); configured=value; } };
  const vscode = { workspace: { isTrusted:true, workspaceFolders:[{uri:{scheme:'file',fsPath:host.project}}], getConfiguration:()=>config, async openTextDocument(uri){editors.push(uri.fsPath); return {uri};} },
    env:{ async openExternal(uri){opened.push(uri.fsPath);return true;} }, ConfigurationTarget:{Global:1}, Uri:{file:fsPath=>({scheme:'file',fsPath})}, ViewColumn:{Beside:2}, lm:{registerTool:()=>({dispose(){}})},
    commands:{registerCommand(name,fn){commands.set(name,fn);return {dispose(){}};}},
    window:{async showOpenDialog(){return selection;},async showTextDocument(document){return document;},createWebviewPanel:()=>({onDidDispose(){},reveal(){},webview:{cspSource:'synthetic',asWebviewUri:()=>({toString:()=> 'synthetic'}),onDidReceiveMessage(fn){handler=fn;},async postMessage(reply){replies.push(reply);}}})} };
  const module = {exports:{}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../extension.cjs'),'utf8'), { module, process, URL, AbortController, require(name){
    if(name==='vscode')return vscode;
    if(name==='./host-launcher.cjs')return {launchHost:async()=>host};
    if(name==='./tool-result.cjs')return require('../tool-result.cjs');
    if(name==='./acceptance-workspace.cjs')return require('../acceptance-workspace.cjs');
    if(name==='node:fs')return {readFileSync:()=>'<head></head>'};
    return require(name);
  } });
  module.exports.activate({subscriptions:[],globalStorageUri:{fsPath:'synthetic'}});
  await commands.get('frag.acceptance')();
  assert.ok(replies.some(reply=>reply.page==='settings'&&reply.focusAcceptance===true));
  async function action(id,action,body={}){await handler({id,action,body});return replies.find(reply=>reply.id===id);}
  assert.equal((await action(1,'workspace-info')).value.prepared,false);
  assert.equal((await action(2,'workspace-open')).error,'ACCEPTANCE_NOT_PREPARED');
  assert.equal((await action(3,'workspace-prepare')).value.prepared,true);
  await action(4,'workspace-open',{target:'plan'}); assert.equal(editors.length,1);
  await action(5,'workspace-open'); assert.equal(opened.length,1);
  assert.equal((await action(6,'workspace-prepare',{path:'not-allowed'})).error,'ACCEPTANCE_REQUEST_INVALID');
  selection=[{scheme:'file',fsPath:host.project}];
  assert.equal((await action(7,'workspace-pick')).error,'ACCEPTANCE_ROOT_OVERLAP'); assert.equal(updates.length,0);
  selection=[{scheme:'file',fsPath:path.join(run,'native-custom')}];
  const chosen=await action(8,'workspace-pick'); assert.equal(chosen.value.prepared,false);
  assert.deepEqual(updates,[{key:'acceptanceRoot',value:selection[0].fsPath,target:1}]);
  assert.equal(fs.existsSync(selection[0].fsPath),false);
  selection=undefined; assert.equal((await action(9,'workspace-pick')).value.root,chosen.value.root);
  const locations=await action(10,'locations-info');
  assert.deepEqual(JSON.parse(JSON.stringify(locations.value)),{stateRoot:host.state,hostRoot:host.installation,acceptanceRoot:chosen.value.root,sourceRoot:chosen.value.sourceRoot,planPath:chosen.value.planPath});
  assert.equal((await action(11,'state-open')).value.opened,true);assert.equal(opened.at(-1),host.state);
  assert.deepEqual(requests,[]);
  assert.ok(replies.filter(reply=>reply.value&&reply.id<10).every(reply=>Object.keys(reply.value).sort().join(',')==='planPath,prepared,root,sourceRoot'));
});
