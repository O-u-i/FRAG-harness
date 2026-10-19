'use strict';
const test = require('node:test'), assert = require('node:assert/strict'), vm = require('node:vm');
const { readFileSync } = require('node:fs'), { join } = require('node:path');

test('presentation preferences are strictly bounded, local and durable; native Settings opens without backend routes', async () => {
  const commands = new Map(), replies = [], saved = [], native = [], requests = [];
  let handler, stored = { theme:'bogus', runLimit:999, secret:'must-not-leak' }, saveFails = false;
  const owned = { child:{exitCode:null,signalCode:null}, installation:'synthetic', async request(route){requests.push(route);return {};} };
  const vscode = { workspace:{isTrusted:true,workspaceFolders:[{uri:{scheme:'file',fsPath:'synthetic'}}],getConfiguration:()=>({get:()=> 'synthetic'})},env:{},
    Uri:{file:fsPath=>({fsPath})},ViewColumn:{Beside:2},lm:{registerTool:()=>({dispose(){}})},
    commands:{registerCommand(name,fn){commands.set(name,fn);return {dispose(){}};},async executeCommand(...args){native.push(args);}},
    window:{createWebviewPanel:()=>({onDidDispose(){},reveal(){},webview:{cspSource:'synthetic',asWebviewUri:()=>({toString:()=> 'synthetic'}),onDidReceiveMessage(fn){handler=fn;},async postMessage(reply){replies.push(reply);}}})} };
  const module={exports:{}};
  vm.runInNewContext(readFileSync(join(__dirname,'../extension.cjs'),'utf8'),{module,process,URL,AbortController,require(name){
    if(name==='vscode')return vscode;if(name==='./host-launcher.cjs')return {launchHost:async()=>owned};
    if(name==='./tool-result.cjs')return require('../tool-result.cjs');if(name==='./acceptance-workspace.cjs')return require('../acceptance-workspace.cjs');
    if(name==='node:fs')return {readFileSync:()=>'<head></head>'};return require(name);
  }});
  module.exports.activate({subscriptions:[],globalStorageUri:{fsPath:'synthetic'},globalState:{get:()=>stored,async update(key,value){if(saveFails)throw Error('synthetic private persistence failure');saved.push({key,value});stored=value;}}});
  await commands.get('frag.settings')();
  async function action(id,action,body={}){await handler({id,action,body});return JSON.parse(JSON.stringify(replies.find(reply=>reply.id===id)));}
  const defaults={theme:'system',density:'compact',motion:true,runLimit:50,advanced:false};
  assert.deepEqual((await action(1,'ui-preferences-read')).value,defaults);
  const preferences={theme:'dracula',density:'comfortable',motion:false,runLimit:100,advanced:true};
  assert.deepEqual((await action(2,'ui-preferences-save',preferences)).value,preferences);
  assert.deepEqual((await action(3,'ui-preferences-read')).value,preferences);
  for(const invalid of [{...preferences,secret:'synthetic'}, {...preferences,theme:'custom'}, {...preferences,runLimit:1}, {...preferences,motion:'false'}, {theme:'living'}, null, []]) {
    assert.equal((await action(10+replies.length,'ui-preferences-save',invalid)).error,'UI_PREFERENCES_INVALID');
  }
  assert.equal(saved.length,1);assert.equal(saved[0].key,'frag.presentation.v1');
  assert.deepEqual(Object.keys(saved[0].value).sort(),Object.keys(defaults).sort());
  saveFails=true;assert.equal((await action(50,'ui-preferences-save',preferences)).error,'UI_PREFERENCES_SAVE_FAILED');
  assert.deepEqual((await action(51,'settings-open')).value,{opened:true});
  assert.deepEqual(native,[['workbench.action.openSettings','frag']]);assert.deepEqual(requests,[]);
  assert.equal(JSON.stringify(replies).includes('must-not-leak'),false);
  assert.equal(JSON.stringify(replies).includes('synthetic private persistence failure'),false);
});
