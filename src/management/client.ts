declare function acquireVsCodeApi(): {postMessage(message:unknown):void;getState():unknown;setState(state:unknown):void};
const api = acquireVsCodeApi();
// Persist presentation only, never source data, credentials, Runs or drafts.
export const viewState = {read:()=>api.getState(),write:(preferences:unknown)=>api.setState({preferences})};
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
