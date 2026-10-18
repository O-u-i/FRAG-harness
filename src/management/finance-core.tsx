import { useState } from 'react';
import { Help } from './help';

export type FcSelection = {workspaceId:string;recordIds:string[]};
export type FcCatalog = {schemaVersion:1;workspace:{id:string;label:string;kind:'personal'|'sandbox'};
  readGrant:{mode:'all'|'living'|'investment'|'selected';itemIds:string[]};
  items:{id:string;label:string;kind:string;segment:'living'|'investment'|null}[];selectedRecordIds:string[]};
const ranges = {all:'All financial data in this Vault, including future items',living:'Living, including future items',
  investment:'Investment, including future items',selected:'Specific accounts or data items'};

export function FinanceCoreFields({catalog,selection,busy,perform,onChange}:{catalog?:FcCatalog;selection?:FcSelection|null;busy:boolean;
  perform:(action:string,body:unknown)=>Promise<unknown>;onChange:(value:FcSelection)=>void}) {
  const [query,setQuery] = useState('');
  const records = selection?.workspaceId===catalog?.workspace.id ? selection?.recordIds ?? [] : [];
  const setRecords = (values:string[]) => onChange({workspaceId:catalog!.workspace.id,recordIds:values});
  const reportRecord = (id:string) => records.find(record=>record.startsWith(id+':'));
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
    <h3>Connect Finance Core<Help label="Private connection" text="The matching Host prepares the byte-pinned official reader 1.10.0 / API 3.10.0 automatically. The token stays in the backend-only fc.env, opened in Notepad, not in this Webview or a native chat editor. No separate reader command or JSON editing is needed. FC sets the authorization ceiling; FRAG only narrows it."/></h3>
    <ol className="connect-steps">
      <li>In FC: <strong>Settings → Connect FRAG → Copy FRAG configuration</strong>.</li>
      <li><button type="button" disabled={busy} onClick={()=>void perform('fc-connection-open',{})}>Open connection file</button> Paste in Notepad with <kbd>Ctrl+A</kbd>, <kbd>Ctrl+V</kbd>, then <kbd>Ctrl+S</kbd>.</li>
      <li><button type="button" disabled={busy} onClick={()=>void perform('fc-connection-check',{})}>Check connection</button></li>
    </ol>
    <p className="notice">Checking pauses FC access until you save authorization again. No financial records are read.</p>
    {catalog ? <>
      <p><strong>{catalog.workspace.label}</strong> · {catalog.workspace.kind} · read only</p>
      <p>FC maximum: {ranges[catalog.readGrant.mode]}.</p>
      <fieldset><legend>FRAG subset · {records.length} / 10 selected<Help label="FRAG financial selection" text="Only checked records may be listed or read by the native Agent. New FC items remain unselected here, even when the FC token covers future items. Each checked account or data item is whole required evidence, not a complete balance sheet. Oversized evidence refuses instead of truncating. Full-scope reports explicitly include their named aggregate scope."/></legend>
        <label>Find an account or item<input type="search" value={query} onChange={e=>setQuery(e.target.value)}/></label>
        {catalog.items.filter(item=>item.label.toLocaleLowerCase().includes(query.toLocaleLowerCase())).map(item=>{
          const report=item.kind==='report', key=item.id.replace('report:','');
          const current=report ? reportRecord(key) : records.find(record=>record==='finance-item:'+item.id);
          const checked=current!==undefined;
          return <div className="fc-item" key={item.id}>
            <label className="check"><input type="checkbox" disabled={busy || (!checked && records.length>=10)} checked={checked} onChange={e=>toggle(item.id,e.target.checked,report)}/><span>{item.label}<small className="fc-item-kind">{item.segment || 'whole Vault'} · {item.kind}</small></span></label>
            {report && checked && <div className="fc-report-dates">
              {key==='monthly-review' ? <label>Final completed month<input required type="month" value={current!.split(':')[1] || ''} disabled={busy} onChange={e=>date(key,1,e.target.value)}/></label>
                : <label>{key==='month-to-date' ? 'Cutoff date' : 'Balances as of'}<input required type="date" value={current!.split(':')[1] || ''} disabled={busy} onChange={e=>date(key,1,e.target.value)}/></label>}
              {key==='economic-evidence' && <label>Obligations through<input required type="date" min={current!.split(':')[1] || undefined} value={current!.split(':')[2] || ''} disabled={busy} onChange={e=>date(key,2,e.target.value)}/></label>}
              {key==='month-to-date' && <p className="notice">Posted Journal activity only; partial month. Unrecorded days remain unknown.</p>}
            </div>}
          </div>;
        })}
        {!catalog.items.length && <p>No items in this grant. Review the selected Vault in FC.</p>}
      </fieldset>
    </> : <p>Check the saved connection to see its Vault and allowed item names.</p>}
  </section>;
}
