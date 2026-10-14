import { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

import { MemoryPanel, type Memory } from './memory';
type Source = {id:string;kind:'local'|'fc';root:string|null;excludedPaths:string[];enabled:boolean;approved:true;revision:number;selectedMemory:{memoryId:string;version:number}[]};
import { RunSummary, RunDetails, formatLocalTime, type Run } from './runs';
import { WorkflowReceipts, type WorkflowReceipt } from './workflows';
type Overview = {version:string;sources:Source[];runs:Run[];memory:Memory[];fcState:string;workflowReceipts:WorkflowReceipt[]};
type Page = 'settings'|'runs'|'memory';
import { request } from './client';
const blank:Source = {id:'kb',kind:'local',root:'',excludedPaths:[],enabled:true,approved:true,revision:0,selectedMemory:[]};
function App() {
  const [page,setPage] = useState<Page>((window as Window & {FRAG_INITIAL_PAGE?:Page}).FRAG_INITIAL_PAGE || 'settings');
  const [data,setData] = useState<Overview>();
  const [source,setSource] = useState<Source>(blank);
  const [approved,setApproved] = useState(false);
  const [result,setResult] = useState<unknown>();
  const [error,setError] = useState('');
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
    setBusy(true); setError('');
    try { const value = action==='overview' ? undefined : await request(action,body); setResult(value); if(action==='source-save') setSource(value); await refresh(); }
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
    <header><div><small>EVIDENCE TOOLS</small><h1>FRAG <span>1.13.0</span></h1></div>
      <button disabled={busy} onClick={()=>perform('overview',{})}>Refresh</button></header>
    <nav aria-label="Management pages">{(['settings','runs','memory'] as Page[]).map(item=><button key={item} aria-current={page===item?'page':undefined} onClick={()=>showPage(item)}>{item[0].toUpperCase()+item.slice(1)}</button>)}</nav>
    <p className="notice">The native VS Code Local Agent owns chat, model requests, research and the final answer. FRAG returns evidence only when a tool is invoked.</p>
    {error && <p role="alert" className="error">{error}. Review Settings, refresh stale sources or reconfirm Memory versions; failed calls are not retried.</p>}
    {busy && <p role="status">Working locally…</p>}
    {page==='settings' && <section><h2>Authorized sources</h2>
      <p>Approval allows indexing these local files and returning their bounded, redacted text to your native Agent/model. No automatic indexing or source expansion.</p>
      <div className="row"><button onClick={()=>chooseSource(blank)}>New local source</button><button onClick={()=>chooseSource({...blank,id:'finance-core',kind:'fc',root:null})}>Finance Core whitelist</button></div>
      <ul>{data?.sources.map(value=><li key={value.id}><button onClick={()=>chooseSource(value)}>{value.id} · r{value.revision} · {value.enabled?'enabled':'disabled'}</button></li>)}</ul>
      <form onSubmit={e=>{e.preventDefault(); void perform('source-save',source); setApproved(false);}}>
        <label>Source ID <input required pattern="[a-z][a-z0-9-]{0,62}" value={source.id} disabled={source.revision>0 || source.kind==='fc'} onChange={e=>chooseSource({...source,id:e.target.value})}/></label>
        {source.kind==='local' ? <><label>Approved directory (absolute path)<input required value={source.root||''} onChange={e=>chooseSource({...source,root:e.target.value})}/></label>
          <label>Excluded relative paths (one per line)<textarea value={source.excludedPaths.join('\n')} onChange={e=>chooseSource({...source,excludedPaths:e.target.value.split('\n').filter(Boolean)})}/></label></> : <p>Reader: {data?.fcState}. Only the installed official FC 1.3.0 artifact and backend-configured Workspace/record IDs are available. Dashboard and writes open the standalone FC UI.</p>}
        <label className="check"><input type="checkbox" checked={source.enabled} onChange={e=>chooseSource({...source,enabled:e.target.checked})}/>Enable this source</label>
        <fieldset><legend>Human-selected Memory (maximum 3, exact audit revisions)</legend>
          <p>Background only. Inapplicable, stale or conflicted selections block delivery rather than silently disappearing.</p>
          {data?.memory.filter(m=>m.status==='active' && !m.conflicts.length && !m.legacyReadOnly).map(m=><label className="check" key={m.id}><input type="checkbox" checked={source.selectedMemory.some(s=>s.memoryId===m.id && s.version===m.version)} onChange={e=>chooseSource({...source,selectedMemory:e.target.checked ? [...source.selectedMemory.filter(s=>s.memoryId!==m.id),{memoryId:m.id,version:m.version}] : source.selectedMemory.filter(s=>s.memoryId!==m.id)})}/>{m.text.slice(0,110)} · v{m.contentVersion} · r{m.version} · {m.general?'general':'source-scoped'}</label>)}
          <button type="button" onClick={()=>setSource({...source,selectedMemory:[]})}>Clear selections</button>
        </fieldset>
        <label className="check"><input type="checkbox" checked={approved} onChange={e=>setApproved(e.target.checked)}/>I approve this exact source configuration and Memory selection.</label>
        <button disabled={!approved || busy || source.selectedMemory.length>3}>Save authorization</button>
      </form>
      {source.kind==='local' && source.revision>0 && <div className="row"><button disabled={busy || sourceDirty} onClick={()=>perform('source-status',{sourceId:source.id})}>Check index</button><button disabled={busy || sourceDirty} onClick={()=>perform('source-build',{sourceId:source.id})}>Build / Refresh index</button></div>}
      {sourceDirty && source.revision>0 && <p>Save changed authorization before checking or refreshing the index.</p>}
    </section>}
    {page==='runs' && <section><h2>Tool Runs</h2><p>FRAG input, exact bounded result, revisions, budget and errors only. No native chat history, final answer or citation acceptance is captured.</p>
      <p role="status">{data ? `${data.runs.length} latest Runs (up to 200). Updated ${formatLocalTime(refreshedAt)}. Newest first; refreshes after tool completion.` : 'Loading Runs…'}</p>
      {data && !data.runs.length && <p>No tool Runs in this project's private state.</p>}
      {data?.runs.map(run=><details key={run.id}><RunSummary run={run} runs={data.runs}/><RunDetails run={run}/></details>)}
    </section>}
    {page==='runs' && <WorkflowReceipts receipts={data?.workflowReceipts ?? []}/>}
    {page==='memory' && <MemoryPanel runs={data?.runs ?? []} records={data?.memory ?? []} busy={busy} perform={perform}/>}
    {result!==undefined && <details className="advanced"><summary>Advanced · last local operation JSON</summary><pre>{JSON.stringify(result,null,2)}</pre></details>}
  </main>;
}
createRoot(document.getElementById('root')!).render(<App/>);
