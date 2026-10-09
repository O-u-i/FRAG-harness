import { beforeEach, expect, test, vi } from 'vitest';
let listener:(event:{data:unknown})=>void;
const sent:unknown[]=[];
beforeEach(()=>{
 vi.resetModules();sent.length=0;
 vi.stubGlobal('window',{addEventListener:(_name:string,fn:typeof listener)=>{listener=fn;}});
 vi.stubGlobal('acquireVsCodeApi',()=>({postMessage:(message:unknown)=>sent.push(message)}));
});
test('management requests correlate out-of-order replies and expose backend rejection',async()=>{
 const {request}=await import('./client');
 const first=request('overview'),second=request('source-build',{sourceId:'kb'});
 expect(sent).toEqual([{id:1,action:'overview',body:{}},{id:2,action:'source-build',body:{sourceId:'kb'}}]);
 listener({data:{id:2,value:{state:'ready'}}});
 expect(await second).toEqual({state:'ready'});
 const rejected=expect(first).rejects.toThrow('POLICY_REJECTED');
 listener({data:{id:1,error:'POLICY_REJECTED'}});await rejected;
 listener({data:{id:2,value:{state:'stale'}}}); // Duplicate/unknown replies cannot alter a settled request.
});
