import { useEffect, useRef, useState } from 'react';
import type { RunReport } from '../../../shared/contracts/runtime';
import type { PreparedCall } from '../../../shared/contracts/governance';
import { reviewRun, saveRevision } from '../../api/runtimeClient';
import { RuntimeAnswer } from '../../features/runtime/RunReportView';
import { RunReviewPanel } from '../../features/runtime/RunReviewPanel';

export function RequestPreview({ call }: { call: PreparedCall }) {
  return <section className="review-request" aria-label="Exact outbound request">
    <div className="review-route"><strong>{call.provider}</strong><span>{call.model}</span></div>
    <code className="review-endpoint">{call.endpoint}</code>
    <p className="review-meta">{call.estimatedInputTokens} input tokens (estimated) · {call.timeoutSeconds}s · {call.maxRetries} retries</p>
    <details open><summary>Complete request JSON</summary><pre>{JSON.stringify(JSON.parse(call.body), null, 2)}</pre></details>
    <details><summary>Source, checklist and memory bindings</summary><pre>{JSON.stringify(JSON.parse(call.binding), null, 2)}</pre></details>
  </section>;
}

export function ReviewReport({ report, onChange }: { report: RunReport; onChange: (value: RunReport) => void }) {
  const [tab, setTab] = useState('output');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const active = useRef(true), actionActive = useRef(false);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  const act = async (operation: () => Promise<RunReport>) => {
    if (actionActive.current) return;
    actionActive.current = true;
    setBusy(true); setError('');
    try { const value = await operation(); if (active.current) onChange(value); }
    catch (caught) { if (active.current) setError(caught instanceof Error ? caught.message : 'Review could not be saved.'); }
    finally { actionActive.current = false; if (active.current) setBusy(false); }
  };
  return <section className="review-report">
    <div className="review-tabs" role="tablist" aria-label="Run report">
      {['output', 'requests', 'sources', 'review'].map((name) => <button type="button" role="tab" id={`report-tab-${name}`} key={name}
        aria-selected={tab === name} tabIndex={tab === name ? 0 : -1} aria-controls="review-report-content" onClick={() => setTab(name)}
        onKeyDown={(event) => {
          const tabs = ['output', 'requests', 'sources', 'review'];
          const index = tabs.indexOf(name);
          const next = event.key === 'ArrowRight' ? (index + 1) % tabs.length : event.key === 'ArrowLeft' ? (index + tabs.length - 1) % tabs.length
            : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : -1;
          if (next < 0) return;
          event.preventDefault(); setTab(tabs[next]);
          document.getElementById(`report-tab-${tabs[next]}`)?.focus();
        }}>{name[0].toUpperCase() + name.slice(1)}</button>)}
    </div>
    <div id="review-report-content" role="tabpanel" aria-labelledby={`report-tab-${tab}`}>
      {error && <p className="review-alert" role="alert">{error}</p>}
      {tab === 'output' && <>
        <div className="review-verdicts"><span>Structure <strong>{report.structuralValidation}</strong></span><span>Human review <strong>{report.semanticReview}</strong></span></div>
        {report.modelOutput ? <RuntimeAnswer answer={report.modelOutput} /> : <p className="review-meta">No Inference output yet.</p>}
        {report.context && <details><summary>Context output</summary><pre>{JSON.stringify(report.context, null, 2)}</pre></details>}
        {report.revisions.map((revision, index) => <details key={revision.id}><summary>Human revision {index + 1} · {revision.reviewStatus}</summary><RuntimeAnswer answer={revision.result} /></details>)}
      </>}
      {tab === 'requests' && <>
        <p className="review-meta">{report.consumedTokens} / {report.runTokenLimit} tokens · {report.requests.length} requests</p>
        {report.requests.map((attempt) => <details key={attempt.id}><summary>{attempt.stage} · {attempt.status}</summary>
          <RequestPreview call={attempt.preparedCall} />{attempt.errorCode && <p role="alert">{attempt.errorCode}</p>}</details>)}
        {report.research && <details><summary>Research trajectory</summary><pre>{JSON.stringify(report.research, null, 2)}</pre></details>}
        {report.toolCalls.map((tool) => <details key={tool.callId}><summary>{tool.name} · {tool.status}</summary><pre>{JSON.stringify(tool.result, null, 2)}</pre></details>)}
      </>}
      {tab === 'sources' && <>
        {report.selection.candidateEvidence.map((item) => <details key={item.evidenceId}><summary>{item.locatorLabel}</summary><pre>{item.text}</pre></details>)}
        <details><summary>Source revisions &amp; assessments</summary><pre>{JSON.stringify(report.selection.sourceBindings, null, 2)}</pre></details>
        <details><summary>Limitations</summary>{report.limitations.map((item) => <p key={item}>{item}</p>)}</details>
      </>}
      {tab === 'review' && <RunReviewPanel key={report.run.id} report={report} busy={busy}
        onReview={(value) => void act(() => reviewRun(report.run.id, value))}
        onRevision={(value) => void act(() => saveRevision(report.run.id, value))} />}
    </div>
    <footer className="review-report-footer"><span>Run {report.run.id.slice(0, 8)} · v{report.run.version}</span>
      <a href={`/api/runtime/runs/${encodeURIComponent(report.run.id)}/report.json`} target="_blank" rel="noreferrer">JSON</a>
      <a href={`/api/runtime/runs/${encodeURIComponent(report.run.id)}/report.md`} target="_blank" rel="noreferrer">Markdown</a>
    </footer>
  </section>;
}
