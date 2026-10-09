const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm');
const {readFileSync}=require('node:fs'),{join}=require('node:path');
test('all native tools invalidate Runs after success, failure and cancellation; UI failures cannot fail a tool',async()=>{
 const tools=new Map(),commands=new Map(),messages=[],events=[];
 let mode='success',disposePanel,notificationFailure;
 const cancellation={isCancellationRequested:false,onCancellationRequested:()=>({dispose(){}})};
 const owned={child:{exitCode:null,signalCode:null},installation:'synthetic',async request(route,body){
  events.push(route);
  if(route.endsWith('/complete'))return {runId:body.runId};
  if(mode==='cancel')cancellation.isCancellationRequested=true;
  return {runId:'synthetic-run'};
 }};
 const vscode={workspace:{isTrusted:true,workspaceFolders:[{uri:{scheme:'file',fsPath:'synthetic'}}],getConfiguration:()=>({get:()=> 'synthetic'})},env:{},
  Uri:{file:path=>({fsPath:path})},ViewColumn:{Beside:2},
  lm:{registerTool:(name,tool)=>{tools.set(name,tool);return {dispose(){}};}},
  commands:{registerCommand:(name,fn)=>{commands.set(name,fn);return {dispose(){}};}},
  LanguageModelTextPart:class{constructor(value){this.value=value;}},LanguageModelToolResult:class{constructor(content){this.content=content;}},CancellationError:class extends Error{},
  window:{createWebviewPanel:()=>({webview:{cspSource:'synthetic',asWebviewUri:()=>({toString:()=> 'synthetic'}),onDidReceiveMessage(){},
   postMessage(message){messages.push(message);events.push('notification');if(notificationFailure==='throw')throw Error('closed');return notificationFailure==='reject'?Promise.reject(Error('closed')):Promise.resolve(true);}},
   onDidDispose(fn){disposePanel=fn;},reveal(){}})}};
 const module={exports:{}};
 vm.runInNewContext(readFileSync(join(__dirname,'../extension.cjs'),'utf8'),{module,process,URL,AbortController,
  require(name){if(name==='vscode')return vscode;if(name==='./host-launcher.cjs')return {launchHost:async()=>owned};
   if(name==='./tool-result.cjs')return {canonical:JSON.stringify,fitPack:async()=>{if(mode==='failure')throw Error('TOKEN_BUDGET');return {omitted:[],tokens:1};}};
   if(name==='node:fs')return {readFileSync:()=>'<head></head>'};return require(name);}});
 module.exports.activate({subscriptions:[],globalStorageUri:{fsPath:'synthetic'}});
 await commands.get('frag.runs')();messages.length=0;events.length=0;
 for(const tool of tools.values()){
  const result=await tool.invoke({input:{}},cancellation);
  assert.equal(result.content[0].value,'{"runId":"synthetic-run"}');
  assert.deepEqual(events.slice(-2),['/api/tools/complete','notification']);
 }
 assert.equal(messages.length,3);assert.ok(messages.every(message=>message.type==='runsChanged'&&Object.keys(message).length===1));
 mode='failure';await assert.rejects(tools.get('frag_search').invoke({input:{}},cancellation),/TOKEN_BUDGET/);
 assert.deepEqual(events.slice(-2),['/api/tools/complete','notification']);
 mode='cancel';await assert.rejects(tools.get('frag_read').invoke({input:{}},cancellation),vscode.CancellationError);
 assert.deepEqual(events.slice(-2),['/api/tools/complete','notification']);
 mode='success';cancellation.isCancellationRequested=false;
 for(notificationFailure of ['throw','reject'])await tools.get('frag_search').invoke({input:{}},cancellation);
 await new Promise(resolve=>setImmediate(resolve));
 disposePanel();const count=messages.length;await tools.get('frag_search').invoke({input:{}},cancellation);assert.equal(messages.length,count);
});
