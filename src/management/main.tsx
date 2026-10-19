import { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';
import { MemoryPanel, type Memory } from './memory';
import { FinanceCoreFields, validateFcSelection, type FcCatalog, type FcSelection } from './finance-core';
import { RunSummary, RunDetails, formatLocalTime, type Run } from './runs';
import { WorkflowReceipts, type WorkflowReceipt } from './workflows';
import { request, viewState } from './client';
import { Help } from './help';
import { Icon } from './icons';
import { defaultPreferences, normalizePreferences, type Preferences } from './preferences';
import { AcceptancePanel } from './acceptance';
import { LocationsPanel } from './locations';
import { OperationResult } from './operation-result';

type Source = {id:string;kind:'local'|'fc';root:string|null;excludedPaths:string[];enabled:boolean;approved:true;revision:number;selectedMemory:{memoryId:string;version:number}[];confirmedPlans?:{relativePath:string;revision:string}[];fcSelection?:FcSelection|null};
type Overview = {version:string;sources:Source[];runs:Run[];memory:Memory[];fcState:string;workflowReceipts:WorkflowReceipt[]};
type Page = 'settings'|'runs'|'memory';
const blank:Source = {id:'kb',kind:'local',root:'',excludedPaths:[],enabled:true,approved:true,revision:0,selectedMemory:[]};
const blankFC:Source = {...blank,id:'finance-core',kind:'fc',root:null};
function savedPreferences() {try {return normalizePreferences((viewState.read() as {preferences?:unknown})?.preferences);} catch {return defaultPreferences;}}
function App() {
  const [preferences,setPreferences] = useState<Preferences>(savedPreferences);
  const [page,setPage] = useState<Page>((window as Window & {FRAG_INITIAL_PAGE?:Page}).FRAG_INITIAL_PAGE || 'settings');
  const [appearance,setAppearance] = useState(false);
  const [acceptanceOpen,setAcceptanceOpen] = useState((window as Window & {FRAG_INITIAL_ACCEPTANCE?:boolean}).FRAG_INITIAL_ACCEPTANCE===true);
  const [locationRevision,setLocationRevision] = useState(0);
  const [data,setData] = useState<Overview>();
  const initialFC = useRef((window as Window & {FRAG_INITIAL_SOURCE_ID?:string}).FRAG_INITIAL_SOURCE_ID==='finance-core');
  const [source,setSource] = useState<Source>(initialFC.current ? blankFC : blank);
  const [fcCatalog,setFcCatalog] = useState<FcCatalog>();
  const [approved,setApproved] = useState(false);
  const [result,setResult] = useState<unknown>();
  const [operationResult,setOperationResult] = useState<{action:string;value:any;label?:string}>();
  const [error,setError] = useState('');
  const [notice,setNotice] = useState('');
  const [busy,setBusy] = useState(false);
  const [refreshedAt,setRefreshedAt] = useState('');
  const [runQuery,setRunQuery] = useState('');
  const [runSearch,setRunSearch] = useState(false);
  const [runStatus,setRunStatus] = useState('all');
  const refreshSequence = useRef(0);
  const runSearchButton = useRef<HTMLButtonElement>(null);
  const preferenceRevision = useRef(0);
  const preferenceWrites = useRef<Promise<unknown>>(Promise.resolve());
  async function refresh() {
    const sequence = ++refreshSequence.current;
    try {
      const value = await request('overview');
      if (sequence === refreshSequence.current) {setData(value);setRefreshedAt(new Date().toISOString());
        if(initialFC.current) {setSource(value.sources.find((item:Source)=>item.id==='finance-core') || blankFC);initialFC.current=false;}}
      return value as Overview;
    } catch (e) {if(sequence===refreshSequence.current) throw e;}
  }
  function showPage(value:Page) {setPage(value);void refresh().catch(e=>setError(e.message));}
  async function perform(action:string,body:unknown) {
    setBusy(true);setError('');setNotice('');setOperationResult(undefined);
    if(action.startsWith('fc-connection-')) {setFcCatalog(undefined);setApproved(false);}
    try {
      const value=action==='overview'?undefined:await request(action,body);setResult(value);
      if(['source-status','source-build','memory-recommend','memory-versions'].includes(action)) setOperationResult({action,value,label:(body as {sourceId?:string}).sourceId});
      if(action==='source-save') {setSource(value);setNotice('Authorization saved.');}
      const fresh=await refresh();
      if(action==='fc-connection-check') {setFcCatalog(value);setSource({...fresh!.sources.find(item=>item.id==='finance-core') || blankFC,enabled:true,fcSelection:{workspaceId:value.workspace.id,recordIds:[]}});}
      if(action==='plan-confirm') setNotice('Plan revision confirmed. Search again, then Read with requireCompletePlan: true.');
      return value;
    } catch(e) {setError(e instanceof Error?e.message:'LOCAL_OPERATION_FAILED');
      if(action==='fc-connection-check') {const fresh=await refresh().catch(()=>undefined);setSource(fresh?.sources.find(item=>item.id==='finance-core') || blankFC);}}
    finally {setBusy(false);}
  }
  useEffect(()=>{document.documentElement.dataset.theme=preferences.theme;document.documentElement.dataset.density=preferences.density;
    document.documentElement.dataset.motion=preferences.motion?'on':'off';viewState.write(preferences);},[preferences]);
  useEffect(()=>{const revision=preferenceRevision.current;void request('ui-preferences-read').then(value=>{if(revision===preferenceRevision.current)setPreferences(normalizePreferences(value));}).catch(()=>{});void refresh().catch(e=>setError(e.message));
    const listener=({data:message}:MessageEvent)=>{
      if(!message) return;
      if(['settings','runs','memory'].includes(message.page)) {showPage(message.page);
        if(message.focusAcceptance) setAcceptanceOpen(true);
        if(message.sourceId==='finance-core') void refresh().then(value=>chooseSource(value?.sources.find(item=>item.id==='finance-core') || blankFC)).catch(e=>setError(e.message));}
      else if(message.type==='runsChanged') void refresh().catch(e=>setError(e.message));
    };
    window.addEventListener('message',listener);return ()=>{window.removeEventListener('message',listener);refreshSequence.current++;};
  },[]);
  function chooseSource(value:Source) {setSource(value);setApproved(false);}
  function savePreferences(value:Preferences) {preferenceRevision.current++;setPreferences(value);preferenceWrites.current=preferenceWrites.current.catch(()=>{}).then(()=>request('ui-preferences-save',value)).catch(e=>setError(e.message));}
  function changePreference<K extends keyof Preferences>(key:K,value:Preferences[K]) {savePreferences({...preferences,[key]:value});}
  function useAcceptanceSource(path:string) {
    const existing=data?.sources.find(value=>value.id==='acceptance');
    if(existing&&(existing.kind!=='local'||existing.root?.replace(/\\/g,'/').toLowerCase()!==path.replace(/\\/g,'/').toLowerCase())) {chooseSource(existing);setError('The acceptance source already uses another folder. Review its saved folder and explicitly edit it if you want to change locations. Existing authorization was not replaced.');return;}
    chooseSource(existing||{...blank,id:'acceptance',root:path});setNotice('Test folder selected. Review and save authorization, then explicitly build its index.');
  }
  const fcValidation=source.kind==='fc'&&source.enabled?(!fcCatalog?'Check the connection before saving financial authorization.':validateFcSelection(source.fcSelection,fcCatalog)):undefined;
  const sourceDirty=JSON.stringify(source)!==JSON.stringify(data?.sources.find(value=>value.id===source.id));
  const filteredRuns=data?.runs.filter(run=>(runStatus==='all'||run.status===runStatus) && [run.id,run.tool,run.sourceId??''].some(text=>text.toLowerCase().includes(runQuery.toLowerCase())))??[];
  return <main className="app-shell">
    <header className="app-header"><div className="brand"><span className="brand-mark" aria-hidden="true">f</span><div><h1>FRAG <span>1.14.0</span></h1><p className="muted">Local evidence, on your terms</p></div></div>
      <div className="toolbar header-actions">
        <button className="icon-button" title="Toggle dark / light theme" aria-label="Toggle dark / light theme" onClick={()=>changePreference('theme',(preferences.theme==='living'||preferences.theme==='system'&&matchMedia('(prefers-color-scheme:light)').matches)?'dracula':'living')}><Icon name={preferences.theme==='living'?'moon':'sun'}/></button>
        <button className="icon-button" aria-label="Appearance and preferences" title="Appearance and preferences" aria-expanded={appearance} aria-controls="appearance-panel" onClick={()=>setAppearance(!appearance)}><Icon name="sliders"/></button>
        <button className="icon-button" disabled={busy} title="Refresh" aria-label="Refresh" onClick={()=>void perform('overview',{})}><Icon name="refresh"/></button>
      </div>
    </header>
    <div className="navigation-bar"><nav aria-label="Management pages">{(['settings','runs','memory'] as Page[]).map(item=><button key={item} aria-current={page===item?'page':undefined} onClick={()=>showPage(item)}><Icon name={item}/>{item[0].toUpperCase()+item.slice(1)}{item==='runs'&&data&&<span className="nav-count">{data.runs.length}</span>}</button>)}</nav><span className="boundary-label">Read only<Help label="Native Agent ownership" text="FRAG returns authorized evidence. The native VS Code Local Agent owns chat, model requests and final answers. Production recommendations are unavailable; FRAG does not filter native chat."/></span></div>
    {appearance&&<section id="appearance-panel" className="panel preferences-panel" aria-label="Appearance and preferences"><div className="section-heading"><h2>Make it yours</h2><button className="text-button" onClick={()=>savePreferences(defaultPreferences)}>Reset appearance</button></div><div className="field-grid">
      <label>Theme<select value={preferences.theme} onChange={e=>changePreference('theme',e.target.value as Preferences['theme'])}><option value="system">Follow system</option><option value="dracula">Dracula dark</option><option value="living">Living light</option></select></label>
      <label>Density<select value={preferences.density} onChange={e=>changePreference('density',e.target.value as Preferences['density'])}><option value="compact">Compact</option><option value="comfortable">Comfortable</option></select></label>
      <label>Visible Runs<select value={preferences.runLimit} onChange={e=>changePreference('runLimit',Number(e.target.value) as Preferences['runLimit'])}>{[25,50,100,200].map(n=><option key={n} value={n}>{n}</option>)}</select></label>
    </div><div className="toolbar"><label className="check"><input type="checkbox" checked={preferences.motion} onChange={e=>changePreference('motion',e.target.checked)}/>Interface motion</label><label className="check"><input type="checkbox" checked={preferences.advanced} onChange={e=>changePreference('advanced',e.target.checked)}/>Show developer JSON</label></div><p className="muted">Presentation only. Permissions, evidence limits and financial rules never change here.</p></section>}
    {error&&<div role="alert" className="error feedback"><strong>{error}</strong><p>Review authorization or stale evidence. Failed calls are not retried.</p></div>}
    {notice&&<p role="status" className="success feedback"><Icon name="check"/>{notice}</p>}
    {busy&&<p role="status" className="busy-indicator">Working locally…</p>}
    {page==='settings'&&<>
      <div className="section-heading page-heading"><div><h2>Sources</h2><p className="muted">Choose what the Agent may read.</p></div><button className="secondary" onClick={()=>setAcceptanceOpen(!acceptanceOpen)} aria-expanded={acceptanceOpen}>A/B acceptance</button></div>
      <AcceptancePanel open={acceptanceOpen} onToggle={setAcceptanceOpen} onUseSource={useAcceptanceSource} onLocationChange={()=>setLocationRevision(value=>value+1)}/>
      <LocationsPanel refreshKey={locationRevision}/>
      <div className="settings-grid"><aside className="source-sidebar" aria-label="Configured sources">
        <button className="add-source" disabled={busy} onClick={()=>chooseSource({...blank,id:'',selectedMemory:[]})}>+ Local source</button>
        <button className={'source-button '+(source.kind==='fc'?'selected':'')} disabled={busy} onClick={()=>chooseSource(data?.sources.find(item=>item.id==='finance-core')||blankFC)}><span>Finance Core</span><small>{data?.fcState||'Optional connection'}</small></button>
        {data?.sources.filter(value=>value.kind==='local').map(value=><button className={'source-button '+(source.id===value.id?'selected':'')} key={value.id} disabled={busy} onClick={()=>chooseSource(value)}><span>{value.id}<i className={'state-dot '+(value.enabled?'enabled':'')} aria-label={value.enabled?'enabled':'disabled'}/></span><small>Revision {value.revision}</small></button>)}
        {!data?.sources.some(value=>value.kind==='local')&&<p className="muted sidebar-hint">Add a folder, approve it, then build an index.</p>}
      </aside><section className="panel source-editor" aria-label="Source authorization"><div className="section-heading"><h3>{source.kind==='fc'?'Finance Core':source.id||'New local source'}</h3><span className="pill">{source.revision?'r'+source.revision:'Not saved'}</span></div>
        <p className="source-disclosure">Approval lets selected evidence reach your native Agent/model. No automatic indexing or scope expansion.</p>
        <form onSubmit={e=>{e.preventDefault();if(fcValidation){setError(fcValidation);return;}void perform('source-save',source);setApproved(false);}}>
          {source.kind==='local'?<><div className="field-grid"><label>Source ID<input required pattern="[a-z][a-z0-9-]{0,62}" value={source.id} disabled={source.revision>0||busy} onChange={e=>chooseSource({...source,id:e.target.value})}/></label><label className="check source-enabled"><input type="checkbox" disabled={busy} checked={source.enabled} onChange={e=>chooseSource({...source,enabled:e.target.checked})}/>Enabled</label></div>
            <label>Approved folder<input required placeholder="Absolute local folder path" disabled={busy} value={source.root||''} onChange={e=>chooseSource({...source,root:e.target.value,confirmedPlans:[]})}/></label>
            <details className="disclosure"><summary>Excluded paths <span className="muted">{source.excludedPaths.length||'None'}</span></summary><label>Relative paths, one per line<textarea value={source.excludedPaths.join('\n')} disabled={busy} onChange={e=>chooseSource({...source,excludedPaths:e.target.value.split('\n').filter(Boolean)})}/></label></details>
          </>:<><FinanceCoreFields catalog={fcCatalog} selection={source.fcSelection} busy={busy} perform={perform} onChange={value=>chooseSource({...source,fcSelection:value})}/><label className="check"><input type="checkbox" disabled={busy} checked={source.enabled} onChange={e=>chooseSource({...source,enabled:e.target.checked,...(!e.target.checked?{fcSelection:null}:{})})}/>Enable this source</label></>}
          {source.kind==='local'&&<details className="disclosure"><summary>Confirmed plans <span className="pill">{source.confirmedPlans?.length||0}</span><Help label="Complete plan confirmation" text="Review the entire Markdown/text file, then confirm it from a completed Search in Runs. Confirmation pins its revision. Changed files require human reconfirmation; refresh alone is not confirmation. Required evidence is never truncated."/></summary>
            {source.confirmedPlans?.length?<ul className="plan-list">{source.confirmedPlans.map(plan=><li key={plan.relativePath}><strong>{plan.relativePath}</strong><code>{plan.revision}</code></li>)}</ul>:<p className="muted">Review a Search result in Runs to confirm its whole document.</p>}
            <button type="button" disabled={busy||!source.confirmedPlans?.length} onClick={()=>chooseSource({...source,confirmedPlans:[]})}>Clear confirmed plans</button>
          </details>}
          <details className="disclosure"><summary>Selected Memory <span className="pill">{source.selectedMemory.length} / 3</span><Help label="Memory selection" text="Exact reviewed background versions only. Inapplicable, stale or conflicted selections block delivery instead of silently disappearing. Memory is not financial evidence or permission."/></summary>
            {data?.memory.filter(m=>m.status==='active'&&!m.conflicts.length&&!m.legacyReadOnly).map(m=><label className="check" key={m.id}><input type="checkbox" disabled={busy||(!source.selectedMemory.some(s=>s.memoryId===m.id)&&source.selectedMemory.length>=3)} checked={source.selectedMemory.some(s=>s.memoryId===m.id&&s.version===m.version)} onChange={e=>chooseSource({...source,selectedMemory:e.target.checked?[...source.selectedMemory.filter(s=>s.memoryId!==m.id),{memoryId:m.id,version:m.version}]:source.selectedMemory.filter(s=>s.memoryId!==m.id)})}/><span>{m.text.slice(0,110)}<small className="muted"> v{m.contentVersion} / r{m.version} · {m.general?'General':'Source-scoped'}</small></span></label>)}
            {source.selectedMemory.filter(s=>{const current=data?.memory.find(m=>m.id===s.memoryId);return !current||current.version!==s.version||current.status!=='active'||!!current.conflicts.length||current.legacyReadOnly;}).map(s=><p className="notice" key={s.memoryId}>Selected Memory <code>{s.memoryId}</code> r{s.version} is unavailable, stale, conflicted or read-only. Delivery remains blocked.<button type="button" disabled={busy} onClick={()=>chooseSource({...source,selectedMemory:source.selectedMemory.filter(item=>item.memoryId!==s.memoryId)})}>Remove selection</button></p>)}
            {!data?.memory.some(m=>m.status==='active'&&!m.conflicts.length&&!m.legacyReadOnly)&&<p className="muted">No applicable reviewed Memory. Create and review it on the Memory page.</p>}<button type="button" disabled={busy||!source.selectedMemory.length} onClick={()=>chooseSource({...source,selectedMemory:[]})}>Clear selections</button>
          </details>
          <div className="authorization-footer">{fcValidation&&<p role="status" className="notice">{fcValidation}</p>}<label className="check"><input type="checkbox" disabled={busy} checked={approved} onChange={e=>setApproved(e.target.checked)}/>I approve this exact source, plan and Memory selection.</label><div className="toolbar"><button className="primary" disabled={!approved||busy||source.selectedMemory.length>3||!!fcValidation}>Save authorization</button>{sourceDirty&&source.revision>0&&<span className="unsaved">Unsaved changes</span>}</div></div>
        </form>
        {source.kind==='local'&&source.revision>0&&<div className="toolbar index-actions"><button disabled={busy||sourceDirty} onClick={()=>void perform('source-status',{sourceId:source.id})}>Check index</button><button disabled={busy||sourceDirty} onClick={()=>void perform('source-build',{sourceId:source.id})}>Build / Refresh index</button></div>}
      </section></div>
    </>}
    {page==='runs'&&<><section className="panel"><div className="section-heading"><div><h2>Tool Runs<Help label="What Runs capture" text="FRAG tool inputs, finalized results, revisions and errors only. No native chat history, final answer or citation acceptance is captured."/></h2><p className="muted" role="status">{data?data.runs.length+' recorded; updated '+formatLocalTime(refreshedAt):'Loading Runs…'}</p></div><div className="toolbar"><select aria-label="Filter Run status" value={runStatus} onChange={e=>setRunStatus(e.target.value)}>{['all','completed','failed','cancelled','interrupted','prepared'].map(status=><option key={status} value={status}>{status==='all'?'All statuses':status}</option>)}</select><button ref={runSearchButton} className="icon-button" aria-label="Search Runs" aria-expanded={runSearch} onClick={()=>{setRunSearch(!runSearch);setRunQuery('');}}><Icon name="search"/></button></div></div>
      {runSearch&&<label className="compact-search">Find by Run, tool or source<input type="search" autoFocus value={runQuery} onChange={e=>setRunQuery(e.target.value)} onKeyDown={e=>{if(e.key==='Escape'){setRunSearch(false);setRunQuery('');runSearchButton.current?.focus();}}}/></label>}
      {!filteredRuns.length&&<div className="empty-state"><Icon name="runs"/><h3>{data?.runs.length?'No matching Runs':'Your evidence trail starts here'}</h3><p>Invoke an enabled FRAG tool in native Chat, then inspect its returned evidence here.</p></div>}
      {filteredRuns.slice(0,preferences.runLimit).map(run=><details className="run-card" key={run.id}><RunSummary run={run} runs={data!.runs}/><RunDetails run={run} busy={busy} onConfirmPlan={data!.sources.some(profile=>profile.id===run.sourceId&&profile.kind==='local'&&profile.enabled&&profile.revision===run.sourceRevision)?evidenceId=>void perform('plan-confirm',{runId:run.id,evidenceId,confirmed:true}):undefined}/></details>)}
      {filteredRuns.length>preferences.runLimit&&<p className="muted">Showing {preferences.runLimit} of {filteredRuns.length}. Change Visible Runs in preferences.</p>}</section><details className="panel workflow-disclosure"><summary>Synthetic safety receipts <span className="pill">{data?.workflowReceipts.length||0}</span></summary><WorkflowReceipts receipts={data?.workflowReceipts??[]}/></details></>}
    {page==='memory'&&<section className="panel memory-page"><MemoryPanel runs={data?.runs??[]} records={data?.memory??[]} busy={busy} perform={perform}/></section>}
    <OperationResult result={operationResult}/>
    {preferences.advanced&&result!==undefined&&<details className="advanced"><summary>Developer · last local operation JSON</summary><pre>{JSON.stringify(result,null,2)}</pre></details>}
    <footer className="app-footer"><span>Evidence tools only</span><span>Production advice off</span></footer>
  </main>;
}
createRoot(document.getElementById('root')!).render(<App/>);
