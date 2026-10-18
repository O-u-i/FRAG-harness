import { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

import { MemoryPanel, type Memory } from './memory';
type Source = {id:string;kind:'local'|'fc';root:string|null;excludedPaths:string[];enabled:boolean;approved:true;revision:number;selectedMemory:{memoryId:string;version:number}[];confirmedPlans?:{relativePath:string;revision:string}[]};
import { RunSummary, RunDetails, formatLocalTime, type Run } from './runs';
import { WorkflowReceipts, type WorkflowReceipt } from './workflows';
type Overview = {version:string;sources:Source[];runs:Run[];memory:Memory[];fcState:string;workflowReceipts:WorkflowReceipt[]};
type Page = 'settings'|'runs'|'memory';
import { request } from './client';
import { Help } from './help';
const blank:Source = {id:'kb',kind:'local',root:'',excludedPaths:[],enabled:true,approved:true,revision:0,selectedMemory:[]};
function App() {
  const [page,setPage] = useState<Page>((window as Window & {FRAG_INITIAL_PAGE?:Page}).FRAG_INITIAL_PAGE || 'settings');
  const [data,setData] = useState<Overview>();
  const [source,setSource] = useState<Source>(blank);
  const [approved,setApproved] = useState(false);
  const [result,setResult] = useState<unknown>();
  const [error,setError] = useState('');
  const [notice,setNotice] = useState('');
  const [busy,setBusy] = useState(false);
  const [refreshedAt,setRefreshedAt] = useState('');
  const refreshSequence = useRef(0);
  async function refresh() {
    const sequence = ++refreshSequence.current;
    try {
      const value = await request('overview');
      if (sequence === refreshSequence.current) { setData(value); setRefreshedAt(new Date().toISOString()); }
    } catch (e) { if (sequence === refreshSequence.current) throw e; }
  }
  function showPage(value:Page) { setPage(value); void refresh().catch(e=>setError(e.message)); }
  async function perform(action:string, body:unknown) {
    setBusy(true); setError(''); setNotice('');
    try { const value = action==='overview' ? undefined : await request(action,body); setResult(value); if(action==='source-save') setSource(value); await refresh();
      if(action==='plan-confirm') setNotice('Plan revision confirmed. Run a new Search, then Read with requireCompletePlan: true. Index refresh alone never reconfirms a changed plan.'); }
    catch (e) { setError(e instanceof Error ? e.message : 'LOCAL_OPERATION_FAILED'); }
    finally { setBusy(false); }
  }
  useEffect(() => { refresh().catch(e=>setError(e.message));
    const listener = ({data}:MessageEvent) => {
      if (!data) return;
      if (['settings','runs','memory'].includes(data.page)) showPage(data.page);
      else if (data.type === 'runsChanged') void refresh().catch(e=>setError(e.message));
    };
    window.addEventListener('message',listener); return ()=>{ window.removeEventListener('message',listener); refreshSequence.current++; };
  },[]);
  function chooseSource(value:Source) { setSource(value); setApproved(false); }
  const sourceDirty = JSON.stringify(source) !== JSON.stringify(data?.sources.find(value=>value.id===source.id));
  return <main>
    <header><div><small>EVIDENCE TOOLS</small><h1>FRAG <span>1.13.3</span></h1></div>
      <button disabled={busy} onClick={()=>perform('overview',{})}>Refresh</button></header>
    <nav aria-label="Management pages">{(['settings','runs','memory'] as Page[]).map(item=><button key={item} aria-current={page===item?'page':undefined} onClick={()=>showPage(item)}>{item[0].toUpperCase()+item.slice(1)}</button>)}</nav>
    <p>Evidence-only tools.<Help label="Native Agent ownership" text="The native VS Code Local Agent owns chat, model requests, research and the final answer. FRAG returns evidence only when a tool is invoked."/></p>
    {error && <p role="alert" className="error">{error}. Review Settings, refresh stale sources or reconfirm Memory versions; failed calls are not retried.</p>}
    {notice && <p role="status">{notice}</p>}
    {busy && <p role="status">Working locally…</p>}
    {page==='settings' && <section><h2>Authorized sources</h2>
      <p>Approval allows indexing these local files and returning their bounded, redacted text to your native Agent/model. No automatic indexing or source expansion.</p>
      <div className="row"><button onClick={()=>chooseSource(blank)}>New local source</button><button onClick={()=>chooseSource({...blank,id:'finance-core',kind:'fc',root:null})}>Finance Core whitelist</button></div>
      <ul>{data?.sources.map(value=><li key={value.id}><button onClick={()=>chooseSource(value)}>{value.id} · r{value.revision} · {value.enabled?'enabled':'disabled'}</button></li>)}</ul>
      <form onSubmit={e=>{e.preventDefault(); void perform('source-save',source); setApproved(false);}}>
        <label>Source ID <input required pattern="[a-z][a-z0-9-]{0,62}" value={source.id} disabled={source.revision>0 || source.kind==='fc'} onChange={e=>chooseSource({...source,id:e.target.value})}/></label>
        {source.kind==='local' ? <><label>Approved directory (absolute path)<input required value={source.root||''} onChange={e=>chooseSource({...source,root:e.target.value,confirmedPlans:[]})}/></label>
          <label>Excluded relative paths (one per line)<textarea value={source.excludedPaths.join('\n')} onChange={e=>chooseSource({...source,excludedPaths:e.target.value.split('\n').filter(Boolean)})}/></label></> : <p>Reader: {data?.fcState} · GET-only.<Help label="Finance Core reader" text="Only the byte-pinned official FC 1.9.0 / API 3.9.0 reader and backend-configured Workspace/record IDs are available. Exact monthly-review, month-to-date and economic-evidence summaries remain whole required evidence. Month-to-date is provisional posted Journal activity, not a full month, balance sheet or proof that unrecorded days had zero activity. Other personal reports and debt recording are not reader capabilities. Dashboard and all writes belong to the standalone FC UI."/></p>}
        <label className="check"><input type="checkbox" checked={source.enabled} onChange={e=>chooseSource({...source,enabled:e.target.checked})}/>Enable this source</label>
        {source.kind==='local' && <fieldset><legend>Human-confirmed plans<Help label="Complete plan confirmation" text="Confirm an explicitly selected Markdown/text document from a completed Search in Runs, after reviewing its whole file. A search hit, file name or index refresh is not confirmation. Overflow refuses the complete plan; it never trims constraints."/></legend>
          <p>Changed plans require human reconfirmation. Required evidence is never truncated.</p>
          {source.confirmedPlans?.length ? <ul>{source.confirmedPlans.map(plan=><li key={plan.relativePath}>{plan.relativePath} · <code>{plan.revision}</code></li>)}</ul> : <p>No confirmed plans selected.</p>}
          <button type="button" onClick={()=>chooseSource({...source,confirmedPlans:[]})}>Clear confirmed plans</button>
        </fieldset>}
        <fieldset><legend>Human-selected Memory (maximum 3, exact audit revisions)</legend>
          <p>Background only. Inapplicable, stale or conflicted selections block delivery rather than silently disappearing.</p>
          {data?.memory.filter(m=>m.status==='active' && !m.conflicts.length && !m.legacyReadOnly).map(m=><label className="check" key={m.id}><input type="checkbox" checked={source.selectedMemory.some(s=>s.memoryId===m.id && s.version===m.version)} onChange={e=>chooseSource({...source,selectedMemory:e.target.checked ? [...source.selectedMemory.filter(s=>s.memoryId!==m.id),{memoryId:m.id,version:m.version}] : source.selectedMemory.filter(s=>s.memoryId!==m.id)})}/>{m.text.slice(0,110)} · v{m.contentVersion} · r{m.version} · {m.general?'general':'source-scoped'}</label>)}
          <button type="button" onClick={()=>setSource({...source,selectedMemory:[]})}>Clear selections</button>
        </fieldset>
        <label className="check"><input type="checkbox" checked={approved} onChange={e=>setApproved(e.target.checked)}/>I approve this exact source configuration, confirmed plans and Memory selection.</label>
        <button disabled={!approved || busy || source.selectedMemory.length>3}>Save authorization</button>
      </form>
      {source.kind==='local' && source.revision>0 && <div className="row"><button disabled={busy || sourceDirty} onClick={()=>perform('source-status',{sourceId:source.id})}>Check index</button><button disabled={busy || sourceDirty} onClick={()=>perform('source-build',{sourceId:source.id})}>Build / Refresh index</button></div>}
      {sourceDirty && source.revision>0 && <p>Save changed authorization before checking or refreshing the index.</p>}
    </section>}
    {page==='runs' && <section><h2>Tool Runs<Help label="What Runs capture" text="FRAG input, exact bounded result, revisions, budget and errors only. No native chat history, final answer or citation acceptance is captured."/></h2>
      <p role="status">{data ? `${data.runs.length} latest Runs (up to 200). Updated ${formatLocalTime(refreshedAt)}. Newest first; refreshes after tool completion.` : 'Loading Runs…'}</p>
      {data && !data.runs.length && <p>No tool Runs in this project's private state.</p>}
      {data?.runs.map(run=><details key={run.id}><RunSummary run={run} runs={data.runs}/><RunDetails run={run} busy={busy}
        onConfirmPlan={data.sources.some(profile=>profile.id===run.sourceId && profile.kind==='local' && profile.enabled && profile.revision===run.sourceRevision) ? evidenceId=>void perform('plan-confirm',{runId:run.id,evidenceId,confirmed:true}) : undefined}/></details>)}
    </section>}
    {page==='runs' && <WorkflowReceipts receipts={data?.workflowReceipts ?? []}/>}
    {page==='memory' && <MemoryPanel runs={data?.runs ?? []} records={data?.memory ?? []} busy={busy} perform={perform}/>}
    {result!==undefined && <details className="advanced"><summary>Advanced · last local operation JSON</summary><pre>{JSON.stringify(result,null,2)}</pre></details>}
  </main>;
}
createRoot(document.getElementById('root')!).render(<App/>);
