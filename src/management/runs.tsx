type Evidence = {evidenceId:string;locatorId:string;locatorLabel?:string;relativePath?:string;sourceUri?:string;text:string;windowed?:boolean};
type Background = {memoryId:string;version:number;contentVersion?:number;text:string;general:boolean};
export type Run = {id:string;tool:string;status:string;createdAt:string;sourceId?:string|null;sourceRevision?:number|null;sourceBindings?:unknown[];outputTokens?:number|null;input?:{sourceId?:string;query?:string;searchRunId?:string;operation?:string;workspaceId?:string};pack?:{query?:string;evidence?:Evidence[];memoryBackground?:Background[];warnings?:string[];budget?:{maxBytes:number;omittedEvidenceIds:string[]};discovery?:unknown}|null;errorCode?:string|null};

export function isEvidenceRun(run:Run) {
  return run.status==='completed' && !!run.pack?.evidence?.length && !!run.sourceBindings?.length;
}

export function recentEvidenceRuns(runs:Run[]) { return runs.filter(isEvidenceRun).slice(0,4); }

export function formatLocalTime(value:string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, {
    year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23',timeZoneName:'short',
  });
}

export function RunSummary({run,runs}:{run:Run;runs:Run[]}) {
  const parent = runs.find(value=>value.id===run.input?.searchRunId);
  const query = run.pack?.query ?? run.input?.query ?? parent?.pack?.query ?? parent?.input?.query;
  return <summary>
    <span className="run-heading">{run.tool} · {run.status} · <time dateTime={run.createdAt} title={run.createdAt}>{formatLocalTime(run.createdAt)}</time></span>
    <span className="run-context">Source: <code>{run.sourceId ?? run.input?.sourceId ?? '—'}</code>
      {query ? ` · Query: ${query}` : run.input?.searchRunId ? ` · Search Run: ${run.input.searchRunId}` : run.input?.operation ? ` · Operation: ${run.input.operation}${run.input.workspaceId ? ` · Workspace: ${run.input.workspaceId}` : ''}` : ''}
    </span>
    <span className="run-id">Run: <code>{run.id}</code></span>
    <span className="run-context">Evidence: {run.pack?.evidence?.length ?? 0} · Memory: {run.pack?.memoryBackground?.length ?? 0} · Warnings: {run.pack?.warnings?.length ?? 0}</span>
  </summary>;
}

export function RunDetails({run}:{run:Run}) {
  const evidence = run.pack?.evidence ?? [], memory = run.pack?.memoryBackground ?? [];
  const files = new Set(evidence.map(item=>item.relativePath ?? item.sourceUri).filter(Boolean)).size;
  const omitted = run.pack?.budget?.omittedEvidenceIds ?? [];
  return <div className="run-details">
    <h3>Summary</h3>
    <p>{evidence.length} evidence {evidence.length===1?'snippet':'snippets'}{files ? ` from ${files} ${files===1?'file':'files'}` : ''} · Source revision: {run.sourceRevision ?? '—'} · Tool result tokens: {run.outputTokens ?? 'not counted'} · Omitted snippets: {omitted.length}</p>
    <p>{run.status==='completed' ? 'FRAG finalized this tool result. This does not confirm native model consumption or answer quality.' : `Tool state: ${run.status}. No successful delivery is claimed.`}</p>
    {run.errorCode && <p className="error">Error: <code>{run.errorCode}</code></p>}
    <h3>Evidence</h3>
    {evidence.length ? <ol className="evidence-list">{evidence.map(item=><li key={item.evidenceId}>
      <strong>{item.locatorLabel ?? item.locatorId}</strong>
      <p className="run-context">{item.relativePath ?? item.sourceUri ?? 'Selected record'} · {item.windowed ? 'Windowed excerpt' : 'Returned snippet'}</p>
      <p className="evidence-preview">{item.text.length>240 ? item.text.slice(0,240)+'…' : item.text}</p>
      <details><summary>Full returned text · {item.evidenceId}</summary><pre>{item.text}</pre></details>
    </li>)}</ol> : <p>{run.pack?.discovery ? 'Configured record discovery only; no evidence text.' : 'No evidence text in this Run.'}</p>}
    <h3>Memory</h3>
    {memory.length ? <ul>{memory.map(item=><li key={item.memoryId}><p>{item.text}</p><p className="run-context">{item.memoryId} · {item.contentVersion ? `v${item.contentVersion} · ` : ''}Revision {item.version} · {item.general?'General':'Source-scoped'} background, not evidence</p></li>)}</ul> : <p>No Memory included.</p>}
    <h3>Warnings</h3>
    {run.pack?.warnings?.length ? <ul>{run.pack.warnings.map(warning=><li key={warning}>{warning}</li>)}</ul> : <p>No recorded warnings.</p>}
    {!!omitted.length && <p>Omitted evidence IDs: {omitted.join(', ')}</p>}
    <details className="advanced"><summary>Advanced · complete audit JSON</summary><pre>{JSON.stringify(run,null,2)}</pre></details>
  </div>;
}
