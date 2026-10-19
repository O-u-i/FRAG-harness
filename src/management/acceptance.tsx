import { useEffect, useState } from 'react';
import { request } from './client';
import { Icon } from './icons';
type Workspace = {root:string;sourceRoot:string;planPath:string;prepared:boolean};
export const acceptancePrompt = [
  'Use only FRAG tools for the synthetic acceptance source (sourceId: acceptance).',
  'Search for "Synthetic acceptance plan" with #frag_search. Use that new searchRunId and only the synthetic-plan.md evidenceIds with #frag_read and requireCompletePlan=true.',
  'Before human confirmation, refusal is expected. Do not confirm plans, refresh indexes, change sources, use filesystem/terminal fallbacks or downgrade to excerpt reads. Stop on any failure and report its error code.',
  'On success, report runId, evidenceId, role, planRevision, windowed and requiredEvidenceIds. Verify the entire document, including BEGIN-PLAN-AB and END-PLAN-AB. No financial or life-action advice. Do not read FC or other sources.',
].join('\n');
export function AcceptancePanel({open,onToggle,onUseSource,onLocationChange}:{open:boolean;onToggle:(value:boolean)=>void;onUseSource:(path:string)=>void;onLocationChange?:()=>void}) {
  const [workspace,setWorkspace]=useState<Workspace>();
  const [working,setWorking]=useState(false);
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');
  const [step,setStep]=useState<'a'|'b'>('b');
  async function action(name:string,body:unknown={}) {setWorking(true);setError('');setMessage('');try {const value=await request(name,body);setWorkspace(value);if(name==='workspace-pick'&&value.root!==workspace?.root)onLocationChange?.();if(name==='workspace-prepare') setMessage('Synthetic files ready. Source authorization and indexing are still manual.');}catch(e){setError(e instanceof Error?e.message:'WORKSPACE_ACTION_FAILED');}finally{setWorking(false);}}
  useEffect(()=>{if(open&&!workspace) void action('workspace-info');},[open]);
  async function copyPrompt() {try {await navigator.clipboard.writeText(acceptancePrompt);setMessage('Prompt copied. Paste it into native Chat when ready.');}catch{setMessage('Select and copy the prompt below. Clipboard access is unavailable.');}}
  return <details className="panel acceptance-panel" open={open} onToggle={e=>onToggle(e.currentTarget.open)}><summary><span>A/B acceptance workspace</span><span className="pill">Synthetic only</span></summary>
    {open&&<><p className="source-disclosure">This guide does not run tests, approve evidence or enable recommendations. Keep real plans, credentials and financial data out of this folder.</p>
      <div className="toolbar acceptance-tabs"><button type="button" aria-pressed={step==='b'} onClick={()=>setStep('b')}>B · Complete evidence</button><button type="button" aria-pressed={step==='a'} onClick={()=>setStep('a')}>A · Safety foundation</button></div>
      {error&&<p role="alert" className="error">{error}</p>}{message&&<p role="status" className="success">{message}</p>}
      {step==='b'?<><div className="workspace-block"><div className="section-heading"><h3>A clear place for your test files</h3><span className="pill">{workspace?.prepared?'Ready':'Not prepared'}</span></div>
        {workspace?<dl className="path-list"><dt>Workspace</dt><dd><code>{workspace.root}</code></dd><dt>Source folder</dt><dd><code>{workspace.sourceRoot}</code></dd><dt>Virtual plan</dt><dd><code>{workspace.planPath}</code></dd></dl>:<p className="muted">Loading this project's local paths…</p>}
        <div className="toolbar"><button className="primary" disabled={working||!workspace} onClick={()=>void action('workspace-prepare')}>{workspace?.prepared?'Check existing files':'Prepare virtual files'}</button><button disabled={working||!workspace?.prepared} onClick={()=>void action('workspace-open')}><Icon name="folder"/>Open folder</button><button disabled={working} onClick={()=>void action('workspace-pick')}>Choose location…</button></div><p className="muted">Custom locations are per machine and project. Changing location never moves or deletes existing files.</p>
      </div>
      <ol className="acceptance-steps"><li><strong>Prepare and authorize</strong><p>Create the virtual files, then select the source folder. Review the exact authorization, save it and explicitly build the index.</p><button disabled={!workspace?.prepared||working} onClick={()=>workspace&&onUseSource(workspace.sourceRoot)}>Use this test source</button></li>
        <li><strong>Verify refusal, then human confirmation</strong><p>Run the prompt before confirmation: the whole-plan read must refuse. Review the entire virtual file, then use Runs → Confirm entire document as a plan. Search again and repeat the same read.</p><button disabled={!workspace?.prepared||working} onClick={()=>void action('workspace-open',{target:'plan'})}>Open virtual plan</button></li>
        <li><strong>Inspect complete delivery</strong><p>In Runs, inspect Full returned text and audit JSON: confirmed_plan, windowed=false, matching revision and server-required ID. Verify every constraint, not just the markers.</p></li>
        <li><strong>Change and revoke</strong><p>Edit only the virtual plan. Refresh without reconfirming: expect refusal. Reconfirm the new revision and repeat. Clear confirmed plans and save: whole-plan access stops; files and completed Runs remain.</p></li>
      </ol><details className="disclosure prompt-block"><summary>Native Chat prompt</summary><div className="toolbar"><button type="button" onClick={()=>void copyPrompt()}><Icon name="copy"/>Copy acceptance prompt</button></div><textarea aria-label="Acceptance prompt" readOnly value={acceptancePrompt} rows={9}/></details>
      <p className="notice">B also requires an explicitly authorized official FC economic report, a positive complete-evidence synthetic case and missing-fact refusal. Account items or a monthly flow report alone do not satisfy it. Capacity / Memory overflow cases belong in isolated synthetic checks, not real data.</p>
      </>:<><h3>Review the safety evidence, not real advice</h3><p>The gate has no production launch button. An empty synthetic receipt list is normal. Native Chat is not filtered by this component.</p><ul className="checklist"><li>Private sentinel absent from visible APIs, Runs, logs, exports and Memory.</li><li>Missing/stale evidence, unknown checks, cancellation, timeout and persistence failure refuse.</li><li>Only the exact checked synthetic bytes return to the internal caller.</li><li>Shared reservations, unknown liability and bounded remediation retain their limits.</li><li>Interrupted work is not resent; feature disable preserves completed evidence.</li></ul><p className="notice">Review isolated test results and safe receipts with the developer. Checked is not correct, adopted or executed. Synthetic budget math is not a provider billing guarantee.</p></>}
      <p className="muted acceptance-boundary">No automatic pass is recorded here. Human A/B acceptance, real factual review and Slice C remain separate.</p>
    </>}
  </details>;
}
