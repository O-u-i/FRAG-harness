import type { RunReport } from '../../../shared/contracts/runtime';

export function ResearchTrajectoryView({ report }: { report: RunReport }) {
  const research = report.research;
  if (!research) return null;
  return <section className="card"><div className="section-heading"><span className="eyebrow">Persisted Research trajectory</span><h2>Evidence collection</h2>
    <p>Research decisions select evidence and record gaps. The final answer still requires Context, Inference and human review.</p></div>
    <div className="preview-meta"><span>Loop: {research.status}</span><span>{research.turns.length} / {research.maxTurns} model turns</span>
      <span>{report.toolCalls.length} / {research.maxToolCalls} tools</span></div>
    <p>Context evidence: {research.selectedEvidenceIds.length ? research.selectedEvidenceIds.join(', ') : 'No final evidence selection yet.'}</p>
    {research.missingInformation.length > 0 && <div className="runtime-missing"><strong>Research missing information</strong>
      <ul>{research.missingInformation.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
    {research.turns.map((turn) => <details key={turn.attemptId}><summary>Research turn {turn.number} · {turn.status} · {turn.decision?.action ?? 'No saved decision'}</summary>
      <p className="muted">Attempt: {turn.attemptId}</p>
      {turn.errorCode && <p className="alert">{turn.errorCode}</p>}
      <pre className="runtime-data">{JSON.stringify(turn.decision ?? { status: turn.status, errorCode: turn.errorCode }, null, 2)}</pre>
    </details>)}
    <p className="muted">No next model turn starts automatically. Inspect tool observations and prepare the next exact request.</p>
  </section>;
}
