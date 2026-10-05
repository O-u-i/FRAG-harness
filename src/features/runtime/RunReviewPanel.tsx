import { useEffect, useRef, useState } from 'react';
import type { ReviewRequest, RevisionRequest, RunReport } from '../../../shared/contracts/runtime';
import { TaskChecklistEditor } from './TaskChecklistEditor';
import { createMemoryCandidate } from '../../api/memoryClient';

type Props = { report: RunReport; busy: boolean; onReview: (input: ReviewRequest) => void; onRevision: (input: RevisionRequest) => void };

export function RunReviewPanel({ report, busy, onReview, onRevision }: Props) {
  const [task, setTask] = useState(report.reviews[report.reviews.length - 1]?.checklist ?? report.selection.task);
  const [target, setTarget] = useState(report.revisions[report.revisions.length - 1]?.id ?? 'model');
  const [note, setNote] = useState('');
  const [memoryBusy, setMemoryBusy] = useState(false);
  const [memoryMessage, setMemoryMessage] = useState('');
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const candidate = async () => {
    setMemoryBusy(true); setMemoryMessage('');
    try {
      const value = await createMemoryCandidate({ runId: report.run.id, revisionId: target === 'model' ? undefined : target, general: false });
      if (alive.current) setMemoryMessage(`Candidate ${value.id} saved. Open Memory to edit, review and promote it.`);
    } catch (caught) { if (alive.current) setMemoryMessage(caught instanceof Error ? caught.message : 'Memory candidate could not be saved.'); }
    finally { if (alive.current) setMemoryBusy(false); }
  };
  const blocked = task.checklist.some((item) => item.blocking && (item.status !== 'met' || !item.reviewed));
  return <section className="card"><div className="section-heading"><span className="eyebrow">Human decision</span><h2>Review this output</h2>
    <p>Record your assessment of factual support. A valid schema or citation identifier does not establish correctness.</p></div>
    <label className="field">Review target<select value={target} disabled={busy || memoryBusy} onChange={(event) => setTarget(event.target.value)}>
      <option value="model">Model original</option>{report.revisions.map((item, index) => <option key={item.id} value={item.id}>Human revision {index + 1} · {item.reviewStatus}</option>)}
    </select></label>
    <TaskChecklistEditor task={task} reviewOnly disabled={busy} onChange={setTask} />
    <label className="field">Review note<textarea value={note} maxLength={4000} disabled={busy} onChange={(event) => setNote(event.target.value)} /></label>
    {blocked && <p className="alert">Blocking items remain unmet or unreviewed. Save a pause while these gaps remain.</p>}
    <div className="rag-actions">{(['accepted', 'rejected', 'paused'] as const).map((decision) => <button key={decision} type="button"
      className={`button ${decision === 'accepted' ? 'primary' : ''}`} disabled={busy || (decision === 'accepted' && (blocked || !report.modelOutput))}
      onClick={() => onReview({ target, decision, checklist: task, note })}>{decision === 'accepted' ? 'Accept reviewed output' : decision === 'rejected' ? 'Reject output' : 'Pause review'}</button>)}</div>
    {report.modelOutput && <RevisionEditor original={report.modelOutput} busy={busy} onSave={onRevision} />}
    {report.modelOutput && <div className="runtime-revision"><p className="muted">Save the selected output as a source-scoped memory candidate. It will need separate editing, review and promotion.</p>
      <button className="button" type="button" disabled={busy || memoryBusy} onClick={() => void candidate()}>Create memory candidate from selected output</button>
      {memoryMessage && <p className="muted" role="status">{memoryMessage}</p>}
    </div>}
  </section>;
}

function RevisionEditor({ original, busy, onSave }: { original: NonNullable<RunReport['modelOutput']>; busy: boolean; onSave: (input: RevisionRequest) => void }) {
  const [answer, setAnswer] = useState(original.answer);
  const [claims, setClaims] = useState(original.claims.map((claim) => ({ text: claim.text, evidenceText: claim.evidenceIds.join(', ') })));
  const [missingText, setMissingText] = useState(original.missingInformation.join('\n'));
  const [disclaimer, setDisclaimer] = useState(original.disclaimer);
  const [note, setNote] = useState('');
  const result = { answer, disclaimer, missingInformation: missingText.split('\n').filter((item) => item.trim()),
    claims: claims.map((claim) => ({ text: claim.text, evidenceIds: claim.evidenceText.split(',').map((id) => id.trim()).filter(Boolean) })) };
  const invalid = !result.answer.trim() || !result.disclaimer.trim() || result.claims.some((claim) => !claim.text.trim() || !claim.evidenceIds.length);
  return <details className="runtime-revision-editor"><summary>Create a human revision</summary>
    <p className="muted">The original stays intact. This revision will need its own review.</p>
    <label className="field">Revised answer<textarea value={answer} disabled={busy} onChange={(event) => setAnswer(event.target.value)} /></label>
    {claims.map((claim, index) => <div className="checklist-item" key={index}>
      <label className="field">Claim {index + 1}<textarea value={claim.text} disabled={busy} onChange={(event) => setClaims(claims.map((item, position) => position === index ? { ...item, text: event.target.value } : item))} /></label>
      <label className="field">Evidence IDs (comma separated)<input value={claim.evidenceText} disabled={busy}
        onChange={(event) => setClaims(claims.map((item, position) => position === index ? { ...item, evidenceText: event.target.value } : item))} /></label>
      <button className="button" type="button" disabled={busy || claims.length <= 1} onClick={() => setClaims(claims.filter((_, position) => position !== index))}>Remove claim {index + 1}</button>
    </div>)}
    <button className="button" type="button" disabled={busy} onClick={() => setClaims([...claims, { text: '', evidenceText: '' }])}>Add revised claim</button>
    <label className="field">Missing information (one item per line)<textarea value={missingText} disabled={busy} onChange={(event) => setMissingText(event.target.value)} /></label>
    <label className="field">Disclaimer<textarea value={disclaimer} disabled={busy} onChange={(event) => setDisclaimer(event.target.value)} /></label>
    <label className="field">Revision note<textarea value={note} maxLength={4000} disabled={busy} onChange={(event) => setNote(event.target.value)} /></label>
    <button className="button" type="button" disabled={busy || invalid} onClick={() => onSave({ result, note })}>Save separate revision</button>
  </details>;
}
