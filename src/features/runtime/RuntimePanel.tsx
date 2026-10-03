import { useEffect, useRef, useState } from 'react';
import type { RecoveryPreview, ReviewRequest, RevisionRequest, RunRecord, RunReport, SessionRecord } from '../../../shared/contracts/runtime';
import { runHarness, runHarnessInference } from '../../api/harnessClient';
import { runRag, runRagInference } from '../../api/ragClient';
import {
  createSession, fetchReportJson, fetchReportMarkdown, fetchRunReport, fetchRuns, fetchSessions, parseReselection,
  previewRecovery, reviewRun, saveRevision,
} from '../../api/runtimeClient';
import type { HarnessRequest } from '../../../shared/contracts/harness';
import type { RagQueryRequest } from '../../../shared/contracts/rag';
import { RunRecoveryPanel, type RecoveryContinuation } from './RunRecoveryPanel';
import { RunReportView } from './RunReportView';
import { RunReviewPanel } from './RunReviewPanel';
import './runtime.css';

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.name !== 'ZodError') return error.message;
  return 'Runtime data did not match the expected contract.';
}
function download(text: string, filename: string, contentType: string) {
  const url = URL.createObjectURL(new Blob([text], { type: contentType }));
  const link = document.createElement('a');
  link.href = url; link.download = filename; link.click();
  globalThis.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function RuntimePanel() {
  const [sessions, setSessions] = useState<SessionRecord[]>([]);
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [filter, setFilter] = useState('');
  const [title, setTitle] = useState('Evidence review');
  const [selectedId, setSelectedId] = useState('');
  const [report, setReport] = useState<RunReport>();
  const [refresh, setRefresh] = useState(0);
  const [recoveryReset, setRecoveryReset] = useState(0);
  const [continuation, setContinuation] = useState<RecoveryContinuation>();
  const [historyLoading, setHistoryLoading] = useState(true);
  const [reportLoading, setReportLoading] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const actionActive = useRef(false);
  const selectionEpoch = useRef(0);
  const selectedIdRef = useRef('');
  const chooseRun = (id: string) => {
    if (selectedIdRef.current !== id) selectionEpoch.current += 1;
    selectedIdRef.current = id;
    setSelectedId(id); setReport((current) => current?.run.id === id ? current : undefined);
    setContinuation(undefined); setRecoveryReset((value) => value + 1); setError('');
  };

  useEffect(() => {
    let active = true;
    const epoch = selectionEpoch.current;
    setHistoryLoading(true);
    Promise.all([fetchSessions(), fetchRuns(filter || undefined)]).then(([nextSessions, nextRuns]) => {
      if (!active || selectionEpoch.current !== epoch) return;
      setSessions(nextSessions); setRuns(nextRuns);
      const nextId = nextRuns.some((run) => run.id === selectedIdRef.current) ? selectedIdRef.current : nextRuns[0]?.id ?? '';
      if (nextId !== selectedIdRef.current) chooseRun(nextId);
    }).catch((caught) => { if (active && selectionEpoch.current === epoch) setError(errorMessage(caught)); })
      .finally(() => { if (active) setHistoryLoading(false); });
    return () => { active = false; };
  }, [filter, refresh]);

  useEffect(() => {
    let active = true;
    const epoch = selectionEpoch.current;
    if (report?.run.id === selectedId) return () => { active = false; };
    setReport(undefined); setReportLoading(false); setError('');
    if (!selectedId) return () => { active = false; };
    setReportLoading(true);
    fetchRunReport(selectedId).then((value) => { if (active && selectionEpoch.current === epoch && selectedIdRef.current === value.run.id) setReport(value); })
      .catch((caught) => { if (active && selectionEpoch.current === epoch) setError(errorMessage(caught)); })
      .finally(() => { if (active) setReportLoading(false); });
    return () => { active = false; };
  }, [selectedId]);

  const action = async <T,>(name: string, operation: (epoch: number) => Promise<T>): Promise<T> => {
    if (actionActive.current) throw new Error('Wait for the current action to finish.');
    actionActive.current = true; setBusy(name); setError('');
    const epoch = selectionEpoch.current;
    try { const value = await operation(epoch); if (selectionEpoch.current !== epoch) throw new Error('Run selection changed. Review the selected run again.'); return value; }
    catch (caught) { if (selectionEpoch.current === epoch) setError(errorMessage(caught)); throw caught; }
    finally { actionActive.current = false; setBusy(''); }
  };
  const recordReview = (input: ReviewRequest) => {
    if (!report || report.run.id !== selectedIdRef.current) return;
    void action('review', () => reviewRun(report.run.id, input)).then((value) => {
      setReport(value); setContinuation(undefined); setRecoveryReset((value) => value + 1); setRefresh((value) => value + 1);
    }).catch(() => undefined);
  };
  const recordRevision = (input: RevisionRequest) => {
    if (!report || report.run.id !== selectedIdRef.current) return;
    void action('revision', () => saveRevision(report.run.id, input)).then((value) => {
      setReport(value); setContinuation(undefined); setRecoveryReset((value) => value + 1); setRefresh((value) => value + 1);
    }).catch(() => undefined);
  };
  const prepare = (input: unknown, reopen: boolean) => action('prepare', async (epoch) => {
    if (!report || report.run.id !== selectedIdRef.current) throw new Error('Select a saved run.');
    const value = await previewRecovery(report.run.id, report.run.kind, input, reopen);
    const nextReport = reopen ? await fetchRunReport(value.runId) : undefined;
    if (selectionEpoch.current !== epoch) throw new Error('Run selection changed.');
    const sourceRequest = reopen && nextReport ? { ...parseReselection(report.run.kind, input),
      sessionId: nextReport.run.sessionId, parentRunId: report.run.id } : input;
    setContinuation({ runId: value.runId, preview: value, sourceRequest });
    if (nextReport) { setReport(nextReport); selectedIdRef.current = value.runId; setSelectedId(value.runId); }
    setRefresh((value) => value + 1);
    return value;
  });
  const dispatch = (recovery: RecoveryPreview, input: unknown) => action('dispatch', async (epoch): Promise<RecoveryPreview | null> => {
    if (!report || report.run.id !== selectedIdRef.current || recovery.runId !== selectedIdRef.current
        || continuation?.runId !== recovery.runId || continuation.preview.preview.preparedCall.fingerprint !== recovery.preview.preparedCall.fingerprint) {
      throw new Error('The recovered request belongs to another selection. Prepare it again.');
    }
    setContinuation(undefined);
    let next: RecoveryPreview | null = null;
    try {
    if (recovery.stage === 'context') {
      const selection = parseReselection(recovery.kind, input);
      const approved = { ...selection, contextFingerprint: recovery.preview.contextFingerprint,
        approvalToken: recovery.preview.approvalToken, approved: true as const };
      const value = recovery.kind === 'harness'
        ? await runHarness(approved as HarnessRequest & typeof approved)
        : await runRag(approved as RagQueryRequest & typeof approved);
      next = { runId: recovery.runId, kind: recovery.kind, stage: 'inference',
        contextFingerprint: value.preview.contextFingerprint, preview: value.inferencePreview };
    } else {
      const approved = { contextFingerprint: recovery.contextFingerprint, inferenceFingerprint: recovery.preview.inferenceFingerprint,
        approvalToken: recovery.preview.approvalToken, approved: true as const };
      if (recovery.kind === 'harness') await runHarnessInference(approved); else await runRagInference(approved);
    }
    } catch (caught) {
      try {
        const value = await fetchRunReport(recovery.runId);
        if (selectionEpoch.current === epoch) { setReport(value); setRefresh((value) => value + 1); }
      } catch { /* Keep the external error; history can be refreshed separately. */ }
      throw caught;
    }
    const value = await fetchRunReport(recovery.runId);
    if (selectionEpoch.current !== epoch) throw new Error('Run selection changed.');
    setReport(value); setContinuation(next ? { runId: recovery.runId, preview: next, sourceRequest: input } : undefined);
    setRefresh((value) => value + 1);
    return next;
  });
  const exportReport = (format: 'json' | 'md') => {
    if (!report || report.run.id !== selectedIdRef.current) return;
    void action('export', async () => {
      const value = format === 'json' ? JSON.stringify(await fetchReportJson(report.run.id), null, 2) : await fetchReportMarkdown(report.run.id);
      download(value, `frag-run-${report.run.id}.${format}`, format === 'json' ? 'application/json' : 'text/markdown');
    }).catch(() => undefined);
  };
  return <div className="runtime-layout">
    <section className="card runtime-history"><div className="section-heading"><span className="eyebrow">Local history</span><h2>Sessions and runs</h2></div>
      <label className="field">Session filter<select value={filter} disabled={!!busy} onChange={(event) => { chooseRun(''); setFilter(event.target.value); }}>
        <option value="">All sessions</option>{sessions.map((session) => <option key={session.id} value={session.id}>{session.title}</option>)}
      </select></label>
      <div className="runtime-session-create"><label className="field">New session title<input value={title} maxLength={200} disabled={!!busy} onChange={(event) => setTitle(event.target.value)} /></label>
        <button className="button" type="button" disabled={!!busy || !title.trim()} onClick={() => {
          void action('session', () => createSession(title)).then((session) => { chooseRun(''); setFilter(session.id); setRefresh((value) => value + 1); }).catch(() => undefined);
        }}>Create session</button></div>
      <button className="button" type="button" disabled={!!busy || historyLoading} onClick={() => {
        setRefresh((value) => value + 1); setContinuation(undefined); setRecoveryReset((value) => value + 1);
        if (selectedId) void action('refresh', () => fetchRunReport(selectedId)).then(setReport).catch(() => undefined);
      }}>Refresh history</button>
      {historyLoading && <p className="muted" role="status">Loading history…</p>}
      {!historyLoading && runs.length === 0 && <p className="empty-state">No saved runs. Prepare a request in Harness or RAG Lab to begin.</p>}
      <div className="runtime-run-list">{runs.map((run) => <button type="button" key={run.id} disabled={!!busy}
        className={`runtime-run-option ${run.id === selectedId ? 'selected' : ''}`} onClick={() => chooseRun(run.id)}>
        <strong>{run.kind} · {run.status}</strong><small>{run.createdAt}</small><code>{run.id}</code>
      </button>)}</div>
    </section>
    <div className="runtime-detail">
      {error && <p className="alert" role="alert">{error}</p>}
      {busy && <p className="muted" role="status">Processing {busy}…</p>}
      {reportLoading && <p className="muted" role="status">Loading saved report…</p>}
      {report && report.run.id === selectedId && <>
        <div className="rag-actions"><button className="button" type="button" disabled={!!busy} onClick={() => exportReport('json')}>Export JSON</button>
          <button className="button" type="button" disabled={!!busy} onClick={() => exportReport('md')}>Export Markdown</button></div>
        <RunReportView report={report} />
        <RunReviewPanel key={`review-${report.run.id}-${report.run.version}`} report={report} busy={!!busy} onReview={recordReview} onRevision={recordRevision} />
        <RunRecoveryPanel key={`recovery-${report.run.id}-${recoveryReset}`} report={report} busy={!!busy} continuation={continuation}
          onInvalidate={() => setContinuation(undefined)} onPrepare={prepare} onDispatch={dispatch} />
      </>}
    </div>
  </div>;
}
