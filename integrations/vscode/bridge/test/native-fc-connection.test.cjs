const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm');
const {readFileSync}=require('node:fs'),{join}=require('node:path'),{EventEmitter}=require('node:events');

test('Connect Finance Core prepares the owned private file and opens Notepad, never a Webview secret editor',async()=>{
 const commands=new Map(),requests=[],opened=[],messages=[],folders=[],launches=[];
 let webviewHandler,customRoot='synthetic-custom-state';
 const owned={child:{exitCode:null,signalCode:null},installation:'synthetic-installation',state:'synthetic-private-state',async stop(){},
  async request(route,body){requests.push({route,body});return {created:true,readyToEdit:true};}};
 const vscode={workspace:{isTrusted:true,workspaceFolders:[{uri:{scheme:'file',fsPath:'synthetic-project'}}],getConfiguration:()=>({get:key=>key==='privateStateRoot'?customRoot:'synthetic-installation'})},env:{openExternal:async uri=>{folders.push(uri.fsPath);return true;}},
  Uri:{file:path=>({fsPath:path})},ViewColumn:{Beside:2},lm:{registerTool:()=>({dispose(){}})},
  commands:{registerCommand:(name,fn)=>{commands.set(name,fn);return {dispose(){}};}},
  window:{showInformationMessage:async()=>{},createWebviewPanel:()=>({webview:{cspSource:'synthetic',asWebviewUri:()=>({toString:()=> 'synthetic'}),
   onDidReceiveMessage(fn){webviewHandler=fn;},async postMessage(value){messages.push(value);}},onDidDispose(){},reveal(){}})}};
 const module={exports:{}};
 vm.runInNewContext(readFileSync(join(__dirname,'../extension.cjs'),'utf8'),{module,process,URL,AbortController,
  require(name){if(name==='vscode')return vscode;if(name==='./host-launcher.cjs')return {launchHost:async(...args)=>{launches.push(args);return owned;}};
   if(name==='./tool-result.cjs')return require('../tool-result.cjs');
   if(name==='./acceptance-workspace.cjs')return require('../acceptance-workspace.cjs');
   if(name==='node:fs')return {readFileSync:()=>'<head></head>'};
   if(name==='node:child_process')return {spawn(executable,args,options){opened.push({executable,args,options});const child=new EventEmitter();child.unref=()=>{};queueMicrotask(()=>child.emit('spawn'));return child;}};
   return require(name);}});
 module.exports.activate({subscriptions:[],globalStorageUri:{fsPath:'synthetic'}});
 assert.equal(typeof commands.get('frag.connectFC'),'function');
 await commands.get('frag.connectFC')();
 await commands.get('frag.openState')();
 assert.deepEqual(folders,[owned.state]);
 assert.equal(launches[0][2],'synthetic-custom-state');
 customRoot='';
 await commands.get('frag.stop')();
 await commands.get('frag.start')();
 assert.equal(launches[1][2],'synthetic');
 vscode.env.openExternal=async()=>false;
 await assert.rejects(commands.get('frag.openState')(),/FRAG_PRIVATE_STATE_FOLDER_OPEN_FAILED/);
 await webviewHandler({id:1,action:'fc-connection-open',body:{}});
 assert.equal(opened.length,2);
 for(const item of opened){assert.match(item.executable,/System32[\\/]notepad\.exe$/i);assert.deepEqual(Array.from(item.args),[join(owned.state,'fc.env')]);assert.equal(item.options.shell,undefined);}
 assert.ok(requests.every(item=>item.route==='/api/manage/fc-connection-prepare'&&Object.keys(item.body).length===0));
 assert.equal(JSON.stringify(messages).includes('fc.env'),false);
 assert.equal(JSON.stringify(messages).includes('synthetic-private-state'),false);
 assert.ok(messages.some(value=>value.id===1&&value.value.opened===true));
});
