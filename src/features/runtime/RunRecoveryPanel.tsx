import { useState } from 'react';
import type { RecoveryPreview, RunReport } from '../../../shared/contracts/runtime';
import { PreparedCallPreview } from '../../components/common/PreparedCallPreview';

type Props = {
  report: RunReport; busy: boolean;
  continuation?: RecoveryContinuation;
  onInvalidate: () => void;
  onPrepare: (input: unknown, reopen: boolean) => Promise<RecoveryPreview>;
  onDispatch: (preview: RecoveryPreview, input: unknown) => Promise<RecoveryPreview | null>;
};
export type RecoveryContinuation = { runId: string; preview: RecoveryPreview; sourceRequest: unknown };

export function RunRecoveryPanel({ report, busy, continuation, onInvalidate, onPrepare, onDispatch }: Props) {
  const carried = continuation?.runId === report.run.id && continuation.preview.runId === report.run.id
    && continuation.preview.kind === report.run.kind ? continuation : undefined;
  const [sourceText, setSourceText] = useState(JSON.stringify(carried?.sourceRequest ?? report.selection.input, null, 2));
  const [prepared, setPrepared] = useState<RecoveryPreview | undefined>(carried?.preview);
  const [sourceRequest, setSourceRequest] = useState<unknown>(carried?.sourceRequest);
  const [inputError, setInputError] = useState('');
  const unknown = report.run.status === 'outcome_unknown';
  const cannotResume = unknown || ['accepted', 'rejected'].includes(report.run.status) || Boolean(report.modelOutput);
  const prepare = async (reopen: boolean) => {
    setPrepared(undefined); onInvalidate(); setInputError('');
    let input: unknown;
    try { input = JSON.parse(sourceText) as unknown; }
    catch { setInputError('Enter a valid JSON source selection.'); return; }
    try { const value = await onPrepare(input, reopen); setSourceRequest(input); setPrepared(value); }
    catch { /* The parent displays the sanitized request error. */ }
  };
  const dispatch = async () => {
    if (!prepared || !window.confirm(`Approve the displayed ${prepared.stage} request to ${prepared.preview.preparedCall.endpoint}?`)) return;
    const call = prepared;
    setPrepared(undefined);
    try { const next = await onDispatch(call, sourceRequest); if (next) setPrepared(next); }
    catch { /* A failed or unknown request is never automatically resent. */ }
  };
  return <section className="card"><div className="section-heading"><span className="eyebrow">Reliable checkpoints</span><h2>Recover or reopen</h2>
    <p>Explicitly review the source selection below. Redacted fields may need re-entry. Preparing a preview makes no model call.</p></div>
    {unknown && <p className="alert">The previous external outcome is unknown. This run will not resend it. Reopen a linked run only after your own reconciliation.</p>}
    <label className="field">Explicit source selection JSON<textarea className="runtime-selection" value={sourceText} disabled={busy} spellCheck={false}
      onChange={(event) => { setSourceText(event.target.value); setPrepared(undefined); setSourceRequest(undefined); onInvalidate(); setInputError(''); }} /></label>
    <p className="muted">Keep the original selection to resume. Changed input creates a linked new run through Reopen.</p>
    {inputError && <p className="alert" role="alert">{inputError}</p>}
    <div className="rag-actions">
      <button className="button" type="button" disabled={busy || cannotResume || !sourceText.trim()}
        onClick={() => void prepare(false)}>Preview recovery</button>
      <button className="button" type="button" disabled={busy || !sourceText.trim()} onClick={() => void prepare(true)}>Reopen as linked run</button>
    </div>
    {prepared && <div className="runtime-recovered"><h3>{prepared.stage === 'context' ? 'Recovered Context preview' : 'Recovered Inference preview'}</h3>
      <p className="muted">Run: {prepared.runId} · Fresh approval required</p>
      <PreparedCallPreview call={prepared.preview.preparedCall} sources={prepared.stage === 'context' ? prepared.preview.sourceBindings : undefined} />
      {prepared.stage === 'context' && !prepared.preview.canApprove && <p className="alert">Resolve blocking checklist items in a linked input revision before approving.</p>}
      <button className="button primary" type="button" disabled={busy || (prepared.stage === 'context' && !prepared.preview.canApprove)}
        onClick={() => void dispatch()}>Approve recovered {prepared.stage === 'context' ? 'Context' : 'Inference'} request</button>
    </div>}
  </section>;
}
