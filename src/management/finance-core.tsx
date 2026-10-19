import { useEffect, useId, useRef, useState } from 'react';
import { Help } from './help';

export type FcSelection = {workspaceId:string;recordIds:string[]};
export type FcCatalog = {schemaVersion:1;workspace:{id:string;label:string;kind:'personal'|'sandbox'};
  readGrant:{mode:'all'|'living'|'investment'|'selected';itemIds:string[]};
  items:{id:string;label:string;kind:string;segment:'living'|'investment'|null}[];selectedRecordIds:string[]};
const ranges = {all:'All financial data in this Vault, including future items',living:'Living, including future items',
  investment:'Investment, including future items',selected:'Specific accounts or data items'};
const kindLabels:Record<string,string> = {account:'Accounts',plan:'Plans',report:'Reports',arrangement:'Arrangements'};
const segmentLabels = {living:'Living',investment:'Investment',vault:'Whole Vault'};

/** Validate the complete draft, including report fields hidden by UI filters. Backend policy remains authoritative. */
export function validateFcSelection(selection?:FcSelection|null,catalog?:FcCatalog,today=new Date().toLocaleDateString('sv-SE',{timeZone:'Asia/Shanghai'})):string|undefined {
  if(!selection || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(selection.workspaceId)) return 'Check the connection and select its Vault.';
  if(catalog && selection.workspaceId!==catalog.workspace.id) return 'The selection belongs to another Vault. Select items for this Vault.';
  if(!selection.recordIds.length) return 'Select at least one financial item.';
  if(selection.recordIds.length>10 || new Set(selection.recordIds).size!==selection.recordIds.length) return 'Select up to 10 distinct financial items.';
  const day=(value:string)=>/^\d{4}-\d{2}-\d{2}$/.test(value) && !value.startsWith('0000') && Number.isFinite(Date.parse(value+'T00:00:00Z')) && new Date(value+'T00:00:00Z').toISOString().slice(0,10)===value;
  for(const record of selection.recordIds) {
    const [kind,first,second,...extra]=record.split(':');
    const catalogId=kind==='finance-item' ? record.slice('finance-item:'.length) : 'report:'+kind;
    if(catalog && !catalog.items.some(item=>item.id===catalogId)) return 'A selected item is outside this connection grant. Review the full selection.';
    if(kind==='monthly-review') {
      if(second!==undefined || extra.length || !/^\d{4}-(0[1-9]|1[0-2])$/.test(first ?? '') || first.startsWith('0000') || first>=today.slice(0,7)) return 'Choose a valid final completed month for every selected monthly review.';
    } else if(kind==='month-to-date') {
      if(second!==undefined || extra.length || !day(first ?? '') || first>today) return 'Choose a valid nonfuture cutoff date for every selected month-to-date report.';
    } else if(kind==='economic-evidence') {
      if(extra.length || !day(first ?? '') || !day(second ?? '')) return 'Complete valid Balances as of and Obligations through dates for every selected economic report.';
      const days=(Date.parse(second+'T00:00:00Z')-Date.parse(first+'T00:00:00Z'))/86400000;
      if(days<=0 || days>366) return 'Obligations through must be 1–366 days after Balances as of.';
    } else if(!/^finance-item:(account|asset|plan|arrangement|transfer):[a-f0-9]{32}$/.test(record)) return 'A selected financial item is invalid. Review the full selection.';
  }
}

export function FinanceCoreFields({catalog,selection,busy,perform,onChange}:{catalog?:FcCatalog;selection?:FcSelection|null;busy:boolean;
  perform:(action:string,body:unknown)=>Promise<unknown>;onChange:(value:FcSelection)=>void}) {
  const [query,setQuery] = useState('');
  const [searchOpen,setSearchOpen] = useState(false), [kind,setKind] = useState('all'), [selectedOnly,setSelectedOnly] = useState(false);
  const searchId = useId(), searchInput = useRef<HTMLInputElement>(null), searchButton = useRef<HTMLButtonElement>(null);
  useEffect(()=>{if(searchOpen) searchInput.current?.focus();},[searchOpen]);
  const records = selection?.workspaceId===catalog?.workspace.id ? selection?.recordIds ?? [] : [];
  const kinds = [...new Set(catalog?.items.map(item=>item.kind) ?? [])];
  const activeKind = kinds.includes(kind) ? kind : 'all';
  const setRecords = (values:string[]) => onChange({workspaceId:catalog!.workspace.id,recordIds:values});
  const reportRecord = (id:string) => records.find(record=>record.startsWith(id+':'));
  const selectedRecord = (item:FcCatalog['items'][number]) => item.kind==='report' ? reportRecord(item.id.replace('report:','')) : records.find(record=>record==='finance-item:'+item.id);
  const matchingItems = catalog?.items.filter(item=>(activeKind==='all' || item.kind===activeKind) && (!selectedOnly || selectedRecord(item)!==undefined) && `${item.label} ${item.kind} ${item.segment ?? ''}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())) ?? [];
  function closeSearch() {setQuery('');setSearchOpen(false);searchButton.current?.focus();}
  function toggle(id:string,checked:boolean,report:boolean) {
    const key = report ? id.replace('report:','') : 'finance-item:'+id;
    const next = records.filter(record=>report ? !record.startsWith(key+':') : record!==key);
    setRecords(checked ? [...next,report ? key+(key==='economic-evidence' ? '::' : ':') : key] : next);
  }
  function date(id:string,index:number,value:string) {
    const previous = reportRecord(id)!;
    const parts=previous.split(':');parts[index]=value;
    setRecords(records.map(record=>record===previous?parts.join(':'):record));
  }
  return <section className="fc-connection" aria-label="Finance Core connection">
    <details className="fc-setup" open={!catalog}>
      <summary>Connection setup<Help label="Private connection" text="The matching Host prepares the byte-pinned official reader 1.10.0 / API 3.10.0 automatically. The token stays in the backend-only fc.env, opened in Notepad, not in this Webview or a native chat editor. No separate reader command or JSON editing is needed. FC sets the authorization ceiling; FRAG only narrows it."/></summary>
      <ol className="connect-steps">
        <li>In FC: <strong>Settings → Connect FRAG → Copy FRAG configuration</strong>.</li>
        <li><button type="button" disabled={busy} onClick={()=>void perform('fc-connection-open',{})}>Open connection file</button> Paste in Notepad: <kbd>Ctrl+A</kbd>, <kbd>Ctrl+V</kbd>, <kbd>Ctrl+S</kbd>.</li>
        <li><button type="button" disabled={busy} onClick={()=>void perform('fc-connection-check',{})}>Check connection</button></li>
      </ol>
    </details>
    <p className="notice fc-access-notice">Checking pauses FC access until you save authorization again. No financial records are read.</p>
    {catalog ? <>
      <div className="fc-vault toolbar"><strong>{catalog.workspace.label}</strong><span className="pill">{catalog.workspace.kind}</span><span className="muted">Read only</span></div>
      <p className="muted fc-grant">FC maximum: {ranges[catalog.readGrant.mode]}.</p>
      {selection && selection.workspaceId!==catalog.workspace.id && <p className="notice" role="alert">The saved selection belongs to another Vault. Select items for this Vault before saving authorization.</p>}
      <fieldset className="fc-subset"><legend>FRAG subset<Help label="FRAG financial selection" text="Only checked records may be listed or read by the native Agent. New FC items remain unselected here, even when the FC token covers future items. Each checked account or data item is whole required evidence, not a complete balance sheet. Oversized evidence refuses instead of truncating. Full-scope reports explicitly include their named aggregate scope."/></legend>
        <div className="toolbar fc-selection-toolbar">
          <span className="pill">{records.length} / 10 selected</span>
          <button type="button" className="filter-chip" aria-pressed={selectedOnly} onClick={()=>setSelectedOnly(!selectedOnly)}>Selected only</button>
          <button type="button" className="icon-button" ref={searchButton} aria-label={searchOpen ? 'Close item search' : 'Search items'} title={searchOpen ? 'Close item search (Escape)' : 'Search items'} aria-expanded={searchOpen} aria-controls={searchId} onClick={()=>searchOpen ? closeSearch() : setSearchOpen(true)}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/></svg>
          </button>
          <span className="muted fc-result-count" role="status">{matchingItems.length} shown</span>
        </div>
        {searchOpen && <div className="compact-search" id={searchId}><input ref={searchInput} type="search" aria-label="Find an account or item" placeholder="Find an account or item…" value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>{if(e.key==='Escape'){e.preventDefault();closeSearch();}}}/></div>}
        {kinds.length>1 && <div className="toolbar fc-kind-filters" role="group" aria-label="Item type">
          {['all',...kinds].map(value=><button type="button" className="filter-chip" key={value} aria-pressed={activeKind===value} onClick={()=>setKind(value)}>{value==='all' ? 'All' : kindLabels[value] ?? value}</button>)}
        </div>}
        <p className="muted fc-selection-policy">Only checked items may be read; new items stay unselected. Whole evidence only; oversized reads refuse. A subset is not a complete balance sheet.</p>
        {catalog.items.some(item=>item.kind==='report') && <p className="notice fc-report-scope">Reports include their named aggregate scope, not just checked accounts.</p>}
        {(['living','investment','vault'] as const).map(segment=>{
          const items=matchingItems.filter(item=>(item.segment ?? 'vault')===segment);
          return items.length>0 && <section className="fc-item-group" aria-label={segmentLabels[segment]} key={segment}>
            <h4 className="fc-group-title">{segmentLabels[segment]} <span className="muted">{items.length}</span></h4>
            <div className="fc-items">{items.map(item=>{
          const report=item.kind==='report', key=item.id.replace('report:','');
          const current=selectedRecord(item);
          const checked=current!==undefined;
          return <div className={`fc-item${checked ? ' is-selected' : ''}`} key={item.id}>
            <label className="check"><input type="checkbox" disabled={busy || (!checked && records.length>=10)} checked={checked} onChange={e=>toggle(item.id,e.target.checked,report)}/><span>{item.label}<small className="fc-item-kind">{item.kind}{report ? ' · named aggregate scope' : ''}</small></span></label>
            {report && checked && <div className="fc-report-dates">
              {key==='monthly-review' ? <label>Final completed month<input required type="month" value={current!.split(':')[1] || ''} disabled={busy} onChange={e=>date(key,1,e.target.value)}/></label>
                : <label>{key==='month-to-date' ? 'Cutoff date' : 'Balances as of'}<input required type="date" value={current!.split(':')[1] || ''} disabled={busy} onChange={e=>date(key,1,e.target.value)}/></label>}
              {key==='economic-evidence' && <label>Obligations through<input required type="date" min={current!.split(':')[1] || undefined} value={current!.split(':')[2] || ''} disabled={busy} onChange={e=>date(key,2,e.target.value)}/></label>}
              {key==='month-to-date' && <p className="notice">Posted Journal activity only; partial month. Unrecorded days remain unknown.</p>}
            </div>}
          </div>;
            })}</div>
          </section>;
        })}
        {!catalog.items.length && <p>No items in this grant. Review the selected Vault in FC.</p>}
        {catalog.items.length>0 && !matchingItems.length && <div className="fc-empty" role="status"><p>No items match these filters.</p><button type="button" onClick={()=>{setQuery('');setKind('all');setSelectedOnly(false);}}>Reset filters</button></div>}
        {records.length>=10 && <p className="notice">Selection limit reached. Uncheck an item to choose another.</p>}
      </fieldset>
    </> : <p>Check the saved connection to see its Vault and allowed item names.</p>}
  </section>;
}
