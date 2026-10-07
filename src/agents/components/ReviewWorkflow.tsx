import { useCallback, useEffect, useRef, useState } from 'react';
import type { AgentView } from '../../../shared/contracts/agents';
import type { HarnessConfig } from '../../../shared/contracts/harness';
import type { TaskContract } from '../../../shared/contracts/governance';
import { preparedCallSchema } from '../../../shared/contracts/governance';
import type { MemorySelection } from '../../../shared/contracts/memory';
import { executeAgent, prepareAgent, recoverAgent } from '../../api/agentClient';
import { MemoryPicker } from '../../features/memory/MemoryPicker';
import { emptyReviewTask, TaskChecklistEditor } from '../../features/runtime/TaskChecklistEditor';
import { EvidencePicker, type EvidenceSelection } from './EvidencePicker';
import { RequestPreview, ReviewReport } from './ReviewReport';
import { Stepper } from './Navigation';

export function ReviewWorkflow({ view, config, onChange }: {
  view: AgentView; config?: HarnessConfig; onChange: (value: AgentView) => void;
}) {
  const turn = view.session.turns[view.session.turns.length - 1];
  const [selection, setSelection] = useState<EvidenceSelection>({ mode: 'files', ready: false, topK: 3 });
  const [task, setTask] = useState<TaskContract>(emptyReviewTask);
  const [memory, setMemory] = useState<MemorySelection[]>([]);
  const [research, setResearch] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const active = useRef(true), actionActive = useRef(false), selectionKey = useRef('');
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  const preview = dirty ? null : view.preview;
  const report = view.report;
  const call = preview ? preparedCallSchema.parse(preview.preview.preparedCall) : undefined;
  const fingerprint = call?.fingerprint;
  useEffect(() => { setConsent(false); }, [fingerprint, view.session.version, report?.run.version]);
  const changeSelection = useCallback((value: EvidenceSelection) => {
    const key = JSON.stringify(value);
    if (selectionKey.current && selectionKey.current !== key) { setDirty(true); setConsent(false); setMemory([]); }
    selectionKey.current = key;
    setSelection(value);
    if (value.mode === 'plugin') setResearch(false);
  }, []);
  const invalidate = () => { setDirty(true); setConsent(false); };
  const act = async (name: string, operation: () => Promise<AgentView>) => {
    if (actionActive.current) return;
    actionActive.current = true; setBusy(name); setError(''); setConsent(false);
    try { const value = await operation(); if (active.current) { setDirty(false); onChange(value); } }
    catch (caught) { if (active.current) { setError(caught instanceof Error ? caught.message : 'Review action failed.'); } }
    finally { actionActive.current = false; if (active.current) setBusy(''); }
  };
  if (!turn) return <p className="review-empty">Send a task in the native FRAG conversation to begin.</p>;
  const kind = selection.mode === 'retrieval' ? 'rag' : 'harness';
  const input = kind === 'rag' ? { ...selection.dataset!, query: turn.text, topK: selection.topK, task, selectedMemory: memory,
    sessionId: view.session.sessionId, parentRunId: turn.runId }
    : { goal: turn.text, fileSelections: selection.mode === 'files' && selection.file ? [selection.file] : [],
      pluginSelection: selection.plugin, task, selectedMemory: memory, sessionId: view.session.sessionId, parentRunId: turn.runId };
  const stage = preview?.stage;
  const step = report?.modelOutput ? 3 : stage === 'inference' || report?.context ? 2 : preview || report ? 1 : 0;
  const canRecover = report && !report.modelOutput && !['outcome_unknown', 'accepted', 'rejected', 'error'].includes(report.run.status) && turn.state === 'running';
  const ready = !!config?.context.ready && !!config.inference.ready;
  const canApprove = !!preview && (!('canApprove' in preview.preview) || preview.preview.canApprove !== false) && !!preview.preview.approvalToken && ready && turn.state === 'running';
  return <div className="review-workflow">
    <Stepper current={step} />
    <section className="review-task"><span className="review-meta">Native task</span><h2>{turn.text}</h2>
      <span className="review-status">{report?.run.status.replace(/_/g, ' ') ?? 'Choose evidence'}</span></section>
    <details className="review-selection" open={!report || dirty}>
      <summary>Evidence &amp; context{report ? ` · ${report.selection.candidateEvidence.length} excerpts` : ''}</summary>
      <EvidencePicker goal={turn.text} busy={!!busy || turn.state !== 'running'} onChange={changeSelection} />
      <details><summary>Checklist &amp; background memory</summary>
        <TaskChecklistEditor task={task} disabled={!!busy} onChange={(value) => { setTask(value); invalidate(); }} />
        <MemoryPicker runId={report?.run.id} query={turn.text} selected={memory} disabled={!!busy}
          onChange={(value) => { setMemory(value); invalidate(); }} />
      </details>
      <label className="review-check"><input type="checkbox" checked={research} disabled={!!busy || selection.mode === 'plugin'}
        onChange={(e) => { setResearch(e.target.checked); invalidate(); }} />Research before Context</label>
      <button className="review-primary" type="button" disabled={!selection.ready || !!busy || turn.state !== 'running'}
        onClick={() => void act('prepare', () => prepareAgent(view, kind, input, research))}>Preview {research ? 'Research' : 'Context'}</button>
    </details>
    {error && <p className="review-alert" role="alert">{error}</p>}
    {busy && <p role="status">{busy === 'execute' ? 'Running the approved stage…' : 'Preparing the exact request…'}</p>}
    {call && preview && <section className="review-approval"><h3>{stage === 'research' ? 'Research' : stage === 'inference' ? 'Inference' : 'Context'} approval</h3>
      <RequestPreview call={call} />
      {'warnings' in preview.preview && preview.preview.warnings.map((warning: string) => <p className="review-meta" key={warning}>{warning}</p>)}
      {!canApprove && <p className="review-alert">Check model readiness and blocking checklist items before approval.</p>}
      <label className="review-check"><input type="checkbox" checked={consent} disabled={!canApprove || !!busy}
        onChange={(e) => setConsent(e.target.checked)} />I reviewed this exact request</label>
      <button type="button" className="review-primary" disabled={!consent || !canApprove || !!busy}
        onClick={() => void act('execute', () => executeAgent(view))}>Approve {stage}</button>
    </section>}
    {!preview && canRecover && !dirty && <button type="button" className="review-primary" disabled={!!busy}
      onClick={() => void act('recover', () => recoverAgent(view))}>Preview next stage</button>}
    {report?.run.status === 'outcome_unknown' && <p className="review-alert">Unknown external outcome. Reconcile it before starting a new task; this run will not resend.</p>}
    {turn.state !== 'running' && <p className="review-meta">Send a new native task to start another run.</p>}
    {report && <ReviewReport report={report} onChange={(value) => onChange({ ...view, report: value, preview: null })} />}
  </div>;
}
