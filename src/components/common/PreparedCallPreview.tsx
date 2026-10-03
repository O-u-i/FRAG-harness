import type { PreparedCall, SourceBinding } from '../../../shared/contracts/governance';

export function PreparedCallPreview({ call, sources }: { call: PreparedCall; sources?: SourceBinding[] }) {
  return <div className="inference-preview">
    <p>{call.provider} · {call.model} · {call.transport === 'fake' ? 'Local simulation' : 'Model API request'}</p>
    <p>Destination: <code>{call.endpoint}</code></p>
    <p>{call.estimatedInputTokens} estimated input tokens · {call.timeoutSeconds}s timeout · {call.maxRetries} retries</p>
    {sources && sources.map((source) => <article key={`${source.identity.namespace}-${source.identity.resourceId}`}>
      <strong>Source review · {source.identity.kind}</strong>
      <p>{(['authority', 'freshness', 'relevance', 'provenance'] as const).map((key) =>
        <span key={key}>{key}: {source.assessment[key].detail ?? 'unknown'}<br /></span>)}</p>
    </article>)}
    <strong>Complete request JSON</strong><pre>{JSON.stringify(JSON.parse(call.body), null, 2)}</pre>
    <details><summary>Bound source scope, checklist and versions</summary><pre>{JSON.stringify(JSON.parse(call.binding), null, 2)}</pre></details>
    <p className="muted">Review the full request before approval. Source revision equality and valid citations do not establish factual support.</p>
  </div>;
}
