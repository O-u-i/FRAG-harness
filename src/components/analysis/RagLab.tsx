import { useEffect, useState } from 'react';
import type {
  RagEvaluationReport, RagIndexStatus, RagPreview, RagRun, RagSearchResponse,
} from '../../../shared/contracts/rag';
import type { HarnessConfig } from '../../../shared/contracts/harness';
import {
  evaluateRag, fetchRagStatus, previewRag, rebuildRagIndex, runRag, searchRag,
} from '../../api/ragClient';
import { PanelHeading } from '../common';

const dataset = { datasetId: 'synthetic-risk-review-v1' } as const;

function safeMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'RAG operation failed.';
}

function Metric({ label, value }: { label: string; value: number }) {
  return <article><span>{label}</span><strong>{value.toFixed(3)}</strong></article>;
}

export function RagLab({ config }: { config?: HarnessConfig } = {}) {
  const [status, setStatus] = useState<RagIndexStatus>();
  const [query, setQuery] = useState('What regulatory risks are mentioned in the source?');
  const [topK, setTopK] = useState(3);
  const [search, setSearch] = useState<RagSearchResponse>();
  const [preview, setPreview] = useState<RagPreview>();
  const [run, setRun] = useState<RagRun>();
  const [evaluation, setEvaluation] = useState<RagEvaluationReport>();
  const [busy, setBusy] = useState('status');
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    fetchRagStatus()
      .then((nextStatus) => { if (active) setStatus(nextStatus); })
      .catch((caught) => { if (active) setError(safeMessage(caught)); })
      .finally(() => { if (active) setBusy(''); });
    return () => { active = false; };
  }, []);


  const resetQueryOutput = () => {
    setSearch(undefined); setPreview(undefined); setRun(undefined); setError('');
  };
  const input = { ...dataset, query, topK };
  const ready = status?.state === 'ready';
  const modelsReady = config?.context.ready && config.inference.ready;

  const rebuild = async () => {
    setBusy('rebuild'); setError(''); setEvaluation(undefined); resetQueryOutput();
    try { setStatus(await rebuildRagIndex(dataset)); }
    catch (caught) { setError(safeMessage(caught)); }
    finally { setBusy(''); }
  };
  const retrieve = async () => {
    setBusy('search'); resetQueryOutput();
    try { setSearch(await searchRag(input)); }
    catch (caught) { setError(safeMessage(caught)); }
    finally { setBusy(''); }
  };
  const buildPreview = async () => {
    setBusy('preview'); setError(''); setRun(undefined);
    try {
      const value = await previewRag(input);
      setPreview(value);
      setSearch({
        datasetId: value.datasetId, query: value.query, topK: value.topK,
        indexRevision: value.indexRevision, results: value.retrievalResults,
      });
    } catch (caught) { setError(safeMessage(caught)); }
    finally { setBusy(''); }
  };
  const generate = async () => {
    if (!preview) return;
    const approved = window.confirm(
      `Send ${preview.candidateEvidence.length} displayed chunks to ${config?.context.provider} and ${config?.inference.provider} for this run?`,
    );
    if (!approved) return;
    setBusy('run'); setError('');
    try { setRun(await runRag({ ...input, contextFingerprint: preview.contextFingerprint, approvalToken: preview.approvalToken, approved: true })); setPreview(undefined); }
    catch (caught) { setError(safeMessage(caught)); }
    finally { setBusy(''); }
  };
  const evaluate = async () => {
    setBusy('eval'); setError('');
    try { setEvaluation(await evaluateRag(dataset)); }
    catch (caught) { setError(safeMessage(caught)); }
    finally { setBusy(''); }
  };

  return <div className="rag-lab">
    <PanelHeading
      title="RAG Lab · FTS Baseline"
      subtitle="Synthetic Markdown → section chunks → SQLite FTS5 → governed Context → grounded answer."
    />

    <section className="rag-status-card">
      <div>
        <span className={`rag-state ${status?.state ?? 'loading'}`}>{status?.state ?? 'loading'}</span>
        <strong>{status ? `${status.documentCount} document · ${status.chunkCount} chunks` : 'Reading index status…'}</strong>
        <small>markdown-section-v1 · explicit rebuild · no Finance Core data</small>
      </div>
      <button type="button" className="secondary-button" disabled={busy !== ''} onClick={() => void rebuild()}>
        {busy === 'rebuild' ? 'Rebuilding…' : ready ? 'Rebuild Demo Index' : 'Build Demo Index'}
      </button>
    </section>

    {status?.state === 'stale' && <p className="sandbox-notice">Synthetic source hash changed. Rebuild before searching.</p>}
    {error && <p className="sandbox-error" role="alert">{error}</p>}

    <section className="rag-query-card">
      <label>Evidence question<textarea value={query} maxLength={500} disabled={busy !== ''} onChange={(event) => {
        setQuery(event.target.value); resetQueryOutput();
      }} /></label>
      <label>Top K<select value={topK} disabled={busy !== ''} onChange={(event) => {
        setTopK(Number(event.target.value)); resetQueryOutput();
      }}><option value={1}>1</option><option value={2}>2</option><option value={3}>3</option></select></label>
      <div className="rag-actions">
        <button type="button" className="secondary-button" disabled={!ready || query.trim().length < 3 || busy !== ''} onClick={() => void retrieve()}>
          {busy === 'search' ? 'Searching…' : '1. Retrieve Chunks'}
        </button>
        <button type="button" className="secondary-button" disabled={!ready || query.trim().length < 3 || busy !== ''} onClick={() => void buildPreview()}>
          {busy === 'preview' ? 'Building Preview…' : '2. Preview Exact Context'}
        </button>
        <button type="button" className="primary-button" disabled={!preview || preview.candidateEvidence.length === 0 || !modelsReady || busy !== ''} onClick={() => void generate()}>
          {busy === 'run' ? 'Generating…' : '3. Approve Once and Generate'}
        </button>
      </div>
    </section>

    {search && <section className="rag-section">
      <div className="rag-section-heading"><h3>Ranked Retrieval</h3><small>Lower BM25 score ranks first.</small></div>
      {search.results.length === 0 ? <p className="muted-text">No matching chunks.</p> : <div className="rag-result-list">
        {search.results.map((item) => <article key={item.chunkId}>
          <div><strong>#{item.rank} · {item.locatorLabel}</strong><span>{item.bm25Score.toFixed(6)}</span></div>
          <p>{item.excerpt}</p>
          <small>{item.chunkId} → {item.sourceId} → {item.locatorId}</small>
        </article>)}
      </div>}
    </section>}

    {preview && <section className="rag-section">
      <div className="rag-section-heading"><h3>Exact Outbound Context</h3><small>{preview.budget.estimatedInputTokens} estimated tokens</small></div>
      <div className="rag-result-list">{preview.candidateEvidence.map((item) => <article key={item.chunkId}>
        <strong>{item.chunkId} · {item.locatorLabel}</strong><pre>{item.text}</pre>
      </article>)}</div>
      <ul>{preview.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
      <code className="sandbox-fingerprint">{preview.contextFingerprint}</code>
    </section>}

    {run && <section className="rag-section rag-answer">
      <div className="rag-section-heading"><h3>Grounded Answer</h3><small>{run.contextStage.provider} → {run.inferenceStage.provider}</small></div>
      <p>{run.result.answer}</p>
      {run.result.claims.map((claim) => <article key={`${claim.text}-${claim.chunkIds.join('-')}`}>
        <p>{claim.text}</p><small>Citations: {claim.chunkIds.join(', ')}</small>
      </article>)}
      <p className="sandbox-disclaimer">{run.result.disclaimer}</p>
    </section>}

    <section className="rag-section">
      <div className="rag-section-heading"><div><h3>Deterministic Evaluation</h3><small>3 canonical cases · release gate</small></div>
        <button type="button" className="secondary-button" disabled={!ready || busy !== ''} onClick={() => void evaluate()}>{busy === 'eval' ? 'Evaluating…' : 'Run Evaluation'}</button>
      </div>
      {evaluation && <>
        <div className={`rag-eval-banner ${evaluation.status.toLowerCase()}`}>{evaluation.status} · suite {evaluation.suiteVersion}</div>
        <div className="rag-metric-grid">
          <Metric label="Hit@1" value={evaluation.metrics.hitAt1} />
          <Metric label="Recall@3" value={evaluation.metrics.recallAt3} />
          <Metric label="MRR@3" value={evaluation.metrics.mrrAt3} />
          <Metric label="nDCG@3" value={evaluation.metrics.ndcgAt3} />
          <Metric label="Context coverage" value={evaluation.gates.contextCoverage} />
          <Metric label="Citation validity" value={evaluation.gates.citationValidity} />
          <Metric label="Expected citation" value={evaluation.gates.expectedCitationCoverage} />
          <Metric label="Stale residual" value={evaluation.gates.staleResidualCount} />
        </div>
        <div className="rag-eval-cases">{evaluation.cases.map((item) => <article key={item.id}>
          <strong>{item.passed ? 'PASS' : 'FAIL'} · {item.id}</strong>
          <span>Expected: {item.expectedChunkId}</span>
          <span>Rank: {item.expectedRank ?? 'not retrieved'} · Actual: {item.actualChunkIds.join(', ') || 'none'}</span>
        </article>)}</div>
      </>}
    </section>
  </div>;
}
