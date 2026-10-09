import { useEffect, useRef, useState } from 'react';
import { request } from './client';
import { formatLocalTime, isEvidenceRun, recentEvidenceRuns, type Run } from './runs';

export type Memory = {id:string;version:number;contentVersion:number;status:string;text:string;general:boolean;conflicts:string[];provenanceRunId:string;legacyReadOnly:boolean};
type Perform = (action:string,body:unknown)=>Promise<void>;

export function MemoryPanel({runs,records,busy,perform}:{runs:Run[];records:Memory[];busy:boolean;perform:Perform}) {
  const [selected,setSelected] = useState<Run>();
  const [runQuery,setRunQuery] = useState(''), [searching,setSearching] = useState(false), [searchError,setSearchError] = useState('');
  const [text,setText] = useState(''), [memoryQuery,setMemoryQuery] = useState('');
  const searchSequence = useRef(0);
  const recent = recentEvidenceRuns(runs);
  useEffect(()=>()=>{searchSequence.current++;},[]);
  async function findRun() {
    const sequence = ++searchSequence.current;
    setSearching(true); setSearchError(''); setSelected(undefined);
    try {
      const run:Run = await request('run-get',{runId:runQuery.trim()});
      if (sequence!==searchSequence.current) return;
      if (!isEvidenceRun(run)) { setSearchError('This Run has no completed evidence. Choose a completed Search, Read or FC record Read.'); return; }
      setSelected(run);
    } catch (error) { if(sequence===searchSequence.current) setSearchError(error instanceof Error ? error.message : 'RUN_LOOKUP_FAILED'); }
    finally { if(sequence===searchSequence.current) setSearching(false); }
  }
  return <section><h2>Reviewed background</h2><p>Write a candidate yourself from a completed tool Run, then edit and explicitly promote it. FRAG cannot read the native Agent's answer.</p>
    <form onSubmit={e=>{e.preventDefault(); void findRun();}}>
      <label>Search by exact Run ID<input maxLength={64} required value={runQuery} onChange={e=>{searchSequence.current++; setSearching(false); setSearchError(''); setSelected(undefined); setRunQuery(e.target.value);}}/></label>
      <button disabled={busy || searching || !runQuery.trim()}>Find Run</button>
    </form>
    {searching && <p role="status">Finding Run…</p>}
    {searchError && <p role="alert" className="error">{searchError}</p>}
    <form onSubmit={e=>{e.preventDefault(); if(selected) void perform('memory-candidate',{runId:selected.id,text,general:false});}}>
      <label>Completed evidence Run · latest 4<select required={!selected} value={recent.some(run=>run.id===selected?.id)?selected!.id:''} onChange={e=>{searchSequence.current++; setSearching(false); setSearchError(''); setRunQuery(''); setSelected(recent.find(run=>run.id===e.target.value));}}>
        <option value="">Choose a recent Run, or search above</option>{recent.map(run=><option key={run.id} value={run.id}>{formatLocalTime(run.createdAt)} · {run.tool} · {run.id}</option>)}
      </select></label>
      <p>Only the latest four completed Runs with evidence appear here. Search the full Run ID for older records in this project's state.</p>
      {selected && <p className="selected-run" role="status">Selected Run: <code>{selected.id}</code><br/>{selected.tool} · Source: {selected.sourceId ?? '—'} · Query: {selected.pack?.query ?? '—'}</p>}
      <label>Candidate text<textarea required maxLength={4000} value={text} onChange={e=>setText(e.target.value)}/></label><button disabled={busy || searching || !selected || !text.trim()}>Create scoped candidate</button>
    </form>
    <label>Find reviewed background for the selected Run<input maxLength={500} value={memoryQuery} onChange={e=>setMemoryQuery(e.target.value)}/></label>
    <button disabled={busy || searching || !selected || !memoryQuery.trim()} onClick={()=>selected && perform('memory-recommend',{runId:selected.id,query:memoryQuery})}>Find up to 3 applicable records</button>
    <p>Suggestions never select or promote Memory. Content version changes only when text or scope changes; audit revision also records review/status changes. Settings pins the exact audit revision.</p>
    {records.map(record=><MemoryEditor key={record.id+':'+record.version} record={record} busy={busy} perform={perform}/>)}
  </section>;
}

export function MemoryEditor({record:m,busy,perform}:{record:Memory;busy:boolean;perform:Perform}) {
  const legacy = m.legacyReadOnly;
  const [text,setText] = useState(m.text), [note,setNote] = useState(''), [reviewed,setReviewed] = useState(false), [general,setGeneral] = useState(m.general);
  const [other,setOther] = useState(''), [otherVersion,setOtherVersion] = useState(1);
  return <details><summary>{m.status} · v{m.contentVersion} · Revision {m.version} · {legacy?'historical read-only':m.id} {m.conflicts.length?'· conflicted':''}</summary>
    <label>Text<textarea readOnly={legacy} maxLength={4000} value={text} onChange={e=>setText(e.target.value)}/></label>
    <button disabled={busy} onClick={()=>perform('memory-versions',{memoryId:m.id})}>View audit history</button>
    {!legacy && <><label className="check"><input type="checkbox" checked={general} onChange={e=>setGeneral(e.target.checked)}/>General background (explicitly remove source isolation on revision)</label>
      <button disabled={busy || !text.trim() || (text.trim()===m.text && general===m.general)} onClick={()=>perform('memory-revise',{memoryId:m.id,version:m.version,text,general})}>Save candidate revision</button>
      <label>Human review note<input value={note} onChange={e=>setNote(e.target.value)}/></label>
      <label className="check"><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/>I reviewed content, provenance, scope and conflicts.</label>
      <div className="row"><button disabled={busy || m.status!=='candidate' || !!m.conflicts.length || !reviewed || !note.trim() || text.trim()!==m.text || general!==m.general} onClick={()=>perform('memory-promote',{memoryId:m.id,version:m.version,reviewed:true,note})}>Promote</button>
        <button disabled={busy || m.status==='retired'} onClick={()=>perform('memory-retire',{memoryId:m.id,version:m.version})}>Retire</button></div>
      <p>Save changed text or scope before reviewing and promoting that candidate.</p>
      <label>Conflicting Memory ID<input value={other} onChange={e=>setOther(e.target.value)}/></label>
      <button disabled={busy || !other} onClick={()=>perform('memory-conflict',{memoryIds:[m.id,other]})}>Mark conflict</button>
      <label>Other reviewed audit revision<input type="number" min={1} value={otherVersion} onChange={e=>setOtherVersion(Number(e.target.value))}/></label>
      <button disabled={busy || !reviewed || !note.trim() || !m.conflicts.includes(other)} onClick={()=>perform('memory-resolve',{memoryIds:[m.id,other],versions:[{memoryId:m.id,version:m.version},{memoryId:other,version:otherVersion}],reviewed:true,note})}>Resolve reviewed conflict</button>
    </>}
  </details>;
}
