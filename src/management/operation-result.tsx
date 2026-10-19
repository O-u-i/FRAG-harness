import type { Memory } from './memory';
type Result = {action:string;value:any;label?:string};
export function OperationResult({result}:{result?:Result}) {
  if(!result) return null;
  const {action,value,label}=result;
  if(action==='source-status'||action==='source-build') return <section className="panel operation-result" aria-label="Index result" role="status"><h3>{label} · Index {value.state}</h3><p>{value.documentCount} documents · {value.chunkCount} chunks</p><p className="muted">{value.state==='ready'?'Ready for explicit Search.':value.state==='not_built'?'Build the index after saving authorization.':'Review source changes, then explicitly refresh the index.'}</p></section>;
  if(action==='memory-recommend'||action==='memory-versions') return <section className="panel operation-result" aria-label="Memory result"><h3>{action==='memory-recommend'?'Applicable Memory suggestions':'Memory audit history'}</h3><p className="muted">{action==='memory-recommend'?'Suggestions never select or promote Memory.':'Read-only history; current selections do not change.'}</p>{!value.length&&<p>No records found.</p>}{value.map((m:Memory & {reviewNote?:string})=><details key={m.id+':'+m.version}><summary>{m.id} · v{m.contentVersion} / r{m.version} · {m.status} · {m.general?'General':'Source-scoped'}</summary><p className="evidence-preview">{m.text}</p><p className="muted">Evidence Run: <code>{m.provenanceRunId}</code></p>{m.reviewNote&&<p>Review note: {m.reviewNote}</p>}</details>)}</section>;
  return null;
}
