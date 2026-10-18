const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm');
const {readFileSync}=require('node:fs'),{join}=require('node:path'),{EventEmitter}=require('node:events');

test('Connect Finance Core prepares the owned private file and opens Notepad, never a Webview secret editor',async()=>{
 const commands=new Map(),requests=[],opened=[],messages=[];
 let webviewHandler;
 const owned={child:{exitCode:null,signalCode:null},installation:'synthetic-installation',state:'synthetic-private-state',
  async request(route,body){requests.push({route,body});return {created:true,readyToEdit:true};}};
 const vscode={workspace:{isTrusted:true,workspaceFolders:[{uri:{scheme:'file',fsPath:'synthetic-project'}}],getConfiguration:()=>({get:()=> 'synthetic-installation'})},env:{},
  Uri:{file:path=>({fsPath:path})},ViewColumn:{Beside:2},lm:{registerTool:()=>({dispose(){}})},
  commands:{registerCommand:(name,fn)=>{commands.set(name,fn);return {dispose(){}};}},
  window:{showInformationMessage:async()=>{},createWebviewPanel:()=>({webview:{cspSource:'synthetic',asWebviewUri:()=>({toString:()=> 'synthetic'}),
   onDidReceiveMessage(fn){webviewHandler=fn;},async postMessage(value){messages.push(value);}},onDidDispose(){},reveal(){}})}};
 const module={exports:{}};
 vm.runInNewContext(readFileSync(join(__dirname,'../extension.cjs'),'utf8'),{module,process,URL,AbortController,
  require(name){if(name==='vscode')return vscode;if(name==='./host-launcher.cjs')return {launchHost:async()=>owned};
   if(name==='./tool-result.cjs')return require('../tool-result.cjs');
   if(name==='node:fs')return {readFileSync:()=>'<head></head>'};
   if(name==='node:child_process')return {spawn(executable,args,options){opened.push({executable,args,options});const child=new EventEmitter();child.unref=()=>{};queueMicrotask(()=>child.emit('spawn'));return child;}};
   return require(name);}});
 module.exports.activate({subscriptions:[],globalStorageUri:{fsPath:'synthetic'}});
 assert.equal(typeof commands.get('frag.connectFC'),'function');
 await commands.get('frag.connectFC')();
 await webviewHandler({id:1,action:'fc-connection-open',body:{}});
 assert.equal(opened.length,2);
 for(const item of opened){assert.match(item.executable,/System32[\\/]notepad\.exe$/i);assert.deepEqual(Array.from(item.args),[join(owned.state,'fc.env')]);assert.equal(item.options.shell,undefined);}
 assert.ok(requests.every(item=>item.route==='/api/manage/fc-connection-prepare'&&Object.keys(item.body).length===0));
 assert.equal(JSON.stringify(messages).includes('fc.env'),false);
 assert.equal(JSON.stringify(messages).includes('synthetic-private-state'),false);
 assert.ok(messages.some(value=>value.id===1&&value.value.opened===true));
});
