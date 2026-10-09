declare function acquireVsCodeApi(): {postMessage(message:unknown):void};
const api = acquireVsCodeApi();
let serial = 0;
const pending = new Map<number,{resolve:(value:any)=>void;reject:(error:Error)=>void}>();
window.addEventListener('message', ({data}) => {
  const waiter = pending.get(data.id);
  if (waiter) { pending.delete(data.id); data.error ? waiter.reject(new Error(data.error)) : waiter.resolve(data.value); }
});
export function request(action:string, body:unknown = {}):Promise<any> {
  const id = ++serial;
  return new Promise((resolve,reject) => { pending.set(id,{resolve,reject}); api.postMessage({id,action,body}); });
}
