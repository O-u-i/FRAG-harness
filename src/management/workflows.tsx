import { formatLocalTime } from './runs';

export type WorkflowReceipt = {
  id:string; kind:'recommendation_workflow'; mode:'synthetic'; ruleVersion:string; revision:number;
  createdAt:string; updatedAt:string; stage:string; status:string; reasonCode:string|null;
  evidence:{runId:string;resultDigest:string;requiredEvidenceIds:string[]}[];
  planRevision:string|null; constraintsRevision:string|null;
  budget:{inputTokens:number;outputTokens:number;liabilityMicroCny:number;pendingRequests:number;usageUnknown:boolean;attempts:number;remediationRounds:number};
};

export function WorkflowReceipts({receipts}:{receipts:WorkflowReceipt[]}) {
  return <section aria-labelledby="workflow-heading">
    <h2 id="workflow-heading">Recommendation workflow receipts</h2>
    <p className="notice">Production recommendations are unavailable. These are synthetic safety diagnostics, not evidence ToolRuns, advice or human decisions. This gate does not filter native chat.</p>
    {!receipts.length && <p>No synthetic workflow receipts in this project.</p>}
    {receipts.map(receipt=><details key={receipt.id}>
      <summary><span className="run-heading">Synthetic · {receipt.status} · <time dateTime={receipt.createdAt}>{formatLocalTime(receipt.createdAt)}</time></span>
        <span className="run-id">Workflow: <code>{receipt.id}</code></span>
      </summary>
      <div className="run-details">
        <p>Stage: {receipt.stage} · Reason: <code>{receipt.reasonCode ?? '—'}</code> · Rule: {receipt.ruleVersion} · Revision: {receipt.revision}</p>
        <p>Checked is not correct, optimal, adopted or executed. No recommendation body is stored or exported here.</p>
        <h3>Shared synthetic budget</h3>
        <p>Input: {receipt.budget.inputTokens} · Counted output: {receipt.budget.outputTokens} · Reserved/known liability: {(receipt.budget.liabilityMicroCny/1_000_000).toFixed(6)} CNY · Pending: {receipt.budget.pendingRequests} · Usage: {receipt.budget.usageUnknown?'unknown':'synthetic accounting'}</p>
        <p>Attempts: {receipt.budget.attempts} · Remediation rounds: {receipt.budget.remediationRounds}. Synthetic arithmetic is not a provider billing guarantee.</p>
        <h3>Evidence references</h3>
        {receipt.evidence.length ? <ul>{receipt.evidence.map(item=><li key={item.runId}><code>{item.runId}</code> · Required IDs: {item.requiredEvidenceIds.join(', ')}</li>)}</ul> : <p>No evidence references recorded.</p>}
        <p>Plan revision: <code>{receipt.planRevision ?? 'not established'}</code></p>
        <p>Constraint revision: <code>{receipt.constraintsRevision ?? 'not established'}</code></p>
        <p>Updated <time dateTime={receipt.updatedAt}>{formatLocalTime(receipt.updatedAt)}</time></p>
      </div>
    </details>)}
  </section>;
}
