import type { RunReport } from '../../../shared/contracts/runtime';
import { PreparedCallPreview } from '../../components/common/PreparedCallPreview';

type Answer = NonNullable<RunReport['modelOutput']>;
export function RuntimeAnswer({ answer }: { answer: Answer }) {
  return <div className="answer">
    <h3>{answer.answer}</h3>
    {answer.claims.map((claim, index) => <p key={index}>{claim.text} <small>[{claim.evidenceIds.join(', ')}]</small></p>)}
    {answer.missingInformation.length > 0 && <div className="runtime-missing"><strong>Missing information</strong>
      <ul>{answer.missingInformation.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
    <p className="muted">{answer.disclaimer}</p>
  </div>;
}

export function RunReportView({ report }: { report: RunReport }) {
  return <>
    <section className="card">
      <div className="section-heading"><span className="eyebrow">Saved run / {report.run.kind}</span><h2>{report.selection.goal}</h2></div>
      <div className="preview-meta"><span>Status: {report.run.status}</span><span>{report.consumedTokens} / {report.runTokenLimit} run tokens</span></div>
      <p className="muted">Run <code>{report.run.id}</code> · Session: {report.session.title}</p>
      {report.run.parentRunId && <p className="muted">Linked original run: <code>{report.run.parentRunId}</code></p>}
      <div className="runtime-verdicts"><p>Structural validation <strong>{report.structuralValidation}</strong></p>
        <p>Human semantic review <strong>{report.semanticReview}</strong><small>{report.revisions.length ? 'Latest human revision' : 'Model original'}</small></p></div>
      {report.limitations.map((item, index) => <p className="notice" key={index}>{item}</p>)}
    </section>
    <section className="card"><div className="section-heading"><span className="eyebrow">Model original</span><h2>Original output</h2>
      <p>Human revisions are separate records. Review citation support against the selected evidence.</p></div>
      {report.modelOutput ? <RuntimeAnswer answer={report.modelOutput} /> : <p className="muted">No completed Inference output is saved.</p>}
      {report.context && <details><summary>Saved Context output</summary><pre className="runtime-data">{JSON.stringify(report.context, null, 2)}</pre></details>}
    </section>
    {report.revisions.length > 0 && <section className="card"><div className="section-heading"><span className="eyebrow">Human revisions</span><h2>Separate revisions</h2></div>
      {report.revisions.map((revision) => <article className="runtime-revision" key={revision.id}>
        <p className="preview-meta">{revision.id} · {revision.reviewStatus} · {revision.createdAt}</p>
        <RuntimeAnswer answer={revision.result} /><p className="muted">{revision.note || 'No revision note.'}</p>
      </article>)}
    </section>}
    <section className="card"><div className="section-heading"><span className="eyebrow">Provenance</span><h2>Selected snapshots and requests</h2></div>
      {report.selection.candidateEvidence.map((item) => <details key={item.evidenceId}><summary>{item.locatorLabel} · {item.evidenceId}</summary>
        <pre className="runtime-data">{item.text}</pre></details>)}
      {report.selection.sourceBindings.map((source) => <article className="runtime-source" key={`${source.identity.namespace}-${source.identity.resourceId}`}>
        <strong>{source.identity.kind} · {source.identity.resourceId}</strong>
        <p>{(['authority', 'freshness', 'relevance', 'provenance'] as const).map((key) => <span key={key}>{key}: {source.assessment[key].detail ?? 'unknown'}<br /></span>)}</p>
        {source.identity.workspaceId && <p>Workspace: {source.identity.workspaceId}</p>}
      </article>)}
      {report.requests.map((attempt) => <details key={attempt.id}><summary>{attempt.stage} · {attempt.status} · {attempt.structuralValidation}</summary>
        <p className="muted">{attempt.id} · {attempt.createdAt}</p>
        {attempt.errorCode && <p className="alert">{attempt.errorCode}</p>}
        <PreparedCallPreview call={attempt.preparedCall} />
      </details>)}
      {report.reviews.length > 0 && <details><summary>Human review history ({report.reviews.length})</summary>
        {report.reviews.map((review) => <article className="runtime-review" key={review.id}><p>{review.decision} · {review.target} · {review.createdAt}</p>
          <p>{review.note || 'No review note.'}</p><ul>{review.checklist.checklist.map((item) => <li key={item.id}>{item.text} · {item.status} · {item.reviewed ? 'reviewed' : 'not reviewed'}</li>)}</ul></article>)}
      </details>}
      <details><summary>Structured report</summary><pre className="runtime-data">{JSON.stringify(report, null, 2)}</pre></details>
    </section>
  </>;
}
