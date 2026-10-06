import { useEffect, useRef, useState } from 'react';
import { PreparedCallPreview } from '../common/PreparedCallPreview';
import type {
  RagContextRun, RagDatasetRequest, RagEvaluationReport, RagIndexStatus, RagPreview, RagRun, RagSearchResponse, RagQueryRequest,
} from '../../../shared/contracts/rag';
import type { HarnessConfig } from '../../../shared/contracts/harness';
import type { LocalFileInspectResponse, LocalFileSource } from '../../../shared/contracts/contextSource';
import { fetchLocalFileSources, inspectLocalFile } from '../../api/contextSourceClient';
import {
  evaluateRag, fetchRagStatus, previewRag, rebuildRagIndex, runRag, runRagInference, searchRag,
} from '../../api/ragClient';
import { PanelHeading } from '../common';
import type { TaskContract } from '../../../shared/contracts/governance';
import { emptyReviewTask, TaskChecklistEditor } from '../../features/runtime/TaskChecklistEditor';
import { SessionPicker } from '../../features/runtime/SessionPicker';
import type { MemorySelection } from '../../../shared/contracts/memory';
import { MemoryPicker } from '../../features/memory/MemoryPicker';

function safeMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'RAG operation failed.';
}

function Metric({ label, value }: { label: string; value: number }) {
  return <article><span>{label}</span><strong>{value.toFixed(3)}</strong></article>;
}

export function RagLab({ config }: { config?: HarnessConfig } = {}) {
  const [datasetId, setDatasetId] = useState<RagDatasetRequest['datasetId']>('synthetic-risk-review-v1');
  const [sources, setSources] = useState<LocalFileSource[]>([]);
  const [selectedPath, setSelectedPath] = useState('');
  const [inspection, setInspection] = useState<LocalFileInspectResponse>();
  const [selectedLocators, setSelectedLocators] = useState<string[]>([]);
  const [status, setStatus] = useState<RagIndexStatus>();
  const [query, setQuery] = useState('What regulatory risks are mentioned in the source?');
  const [topK, setTopK] = useState(3);
  const [task, setTask] = useState<TaskContract>(emptyReviewTask);
  const [sessionId, setSessionId] = useState('');
  const [lineage, setLineage] = useState<{ runId: string; sessionId: string }>();
  const [memoryRunId, setMemoryRunId] = useState<string>();
  const [selectedMemory, setSelectedMemory] = useState<MemorySelection[]>([]);
  const [previewInput, setPreviewInput] = useState<RagQueryRequest>();
  const [search, setSearch] = useState<RagSearchResponse>();
  const [preview, setPreview] = useState<RagPreview>();
  const [contextRun, setContextRun] = useState<RagContextRun>();
  const [run, setRun] = useState<RagRun>();
  const requestVersion = useRef(0);
  const [evaluation, setEvaluation] = useState<RagEvaluationReport>();
  const [busy, setBusy] = useState('status');
  const [error, setError] = useState('');
  const selectedLocal = datasetId === 'selected-local-v1';
  const selectionReady = !selectedLocal || Boolean(selectedPath && selectedLocators.length);
  const dataset: RagDatasetRequest = { datasetId, ...(selectedLocal && selectionReady ? { sourceSelection: {
    relativePath: selectedPath, locatorIds: selectedLocators,
    relevanceReason: 'Explicitly selected locators for this retrieval review.',
  } } : {}) };
  const datasetKey = JSON.stringify(dataset);

  useEffect(() => {
    let active = true;
    setStatus(undefined);
    if (!selectionReady) return () => { active = false; };
    setBusy('status');
    fetchRagStatus(selectedLocal ? dataset : undefined)
      .then((nextStatus) => { if (active) setStatus(nextStatus); })
      .catch((caught) => { if (active) setError(safeMessage(caught)); })
      .finally(() => { if (active) setBusy(''); });
    return () => { active = false; };
  }, [datasetKey]);

  useEffect(() => {
    let active = true;
    if (!selectedLocal) return () => { active = false; };
    fetchLocalFileSources().then((items) => { if (active) setSources(items.filter((item) => item.status === 'ready')); })
      .catch((caught) => { if (active) setError(safeMessage(caught)); });
    return () => { active = false; };
  }, [selectedLocal]);

  const resetQueryOutput = (clearMemory = false) => {
    if (clearMemory) { setSelectedMemory([]); setMemoryRunId(undefined); }
    requestVersion.current += 1;
    setSearch(undefined); setPreview(undefined); setPreviewInput(undefined); setContextRun(undefined); setRun(undefined); setError('');
    setBusy('');
  };
  const selectPath = async (path: string) => {
    resetQueryOutput(true); setEvaluation(undefined);
    const version = requestVersion.current;
    setSelectedPath(path); setInspection(undefined); setSelectedLocators([]);
    if (!path) return;
    setBusy('inspect');
    try { const value = await inspectLocalFile(path); if (version === requestVersion.current) setInspection(value); }
    catch (caught) { if (version === requestVersion.current) setError(safeMessage(caught)); }
    finally { if (version === requestVersion.current) setBusy(''); }
  };
  const input = { ...dataset, query, topK, task, selectedMemory, sessionId: sessionId || lineage?.sessionId || undefined, parentRunId: lineage?.runId };
  const ready = selectionReady && status?.datasetId === datasetId && status.state === 'ready';
  const modelsReady = config?.context.ready && config.inference.ready;

  const rebuild = async () => {
    setError(''); setEvaluation(undefined); resetQueryOutput(true); setBusy('rebuild');
    const version = requestVersion.current;
    try { const value = await rebuildRagIndex(dataset); if (version === requestVersion.current) setStatus(value); }
    catch (caught) { if (version === requestVersion.current) setError(safeMessage(caught)); }
    finally { if (version === requestVersion.current) setBusy(''); }
  };
  const retrieve = async () => {
    resetQueryOutput(); setBusy('search');
    const version = requestVersion.current;
    try { const value = await searchRag(input); if (version === requestVersion.current) setSearch(value); }
    catch (caught) { if (version === requestVersion.current) setError(safeMessage(caught)); }
    finally { if (version === requestVersion.current) setBusy(''); }
  };
  const buildPreview = async () => {
    resetQueryOutput();
    const version = requestVersion.current;
    setBusy('preview');
    try {
      const value = await previewRag(input);
      if (version === requestVersion.current) { setPreview(value); setPreviewInput(input);
      setMemoryRunId(value.runId || undefined);
      if (value.runId && value.sessionId) setLineage({ runId: value.runId, sessionId: value.sessionId });
      setSearch({
        datasetId: value.datasetId, query: value.query, topK: value.topK,
        indexRevision: value.indexRevision, results: value.retrievalResults,
      }); }
    } catch (caught) { if (version === requestVersion.current) setError(safeMessage(caught)); }
    finally { if (version === requestVersion.current) setBusy(''); }
  };
  const generate = async () => {
    if (!preview?.canApprove || !previewInput) return;
    const approved = window.confirm(
      `Send ${preview.candidateEvidence.length} displayed chunks to the ${config?.context.provider} Context model?`,
    );
    if (!approved) return;
    const version = requestVersion.current;
    setBusy('run'); setError('');
    try { const value = await runRag({ ...previewInput, contextFingerprint: preview.contextFingerprint, approvalToken: preview.approvalToken, approved: true });
      if (version === requestVersion.current) { setContextRun(value); setPreview(undefined); } }
    catch (caught) { if (version === requestVersion.current) setError(safeMessage(caught)); }
    finally { if (version === requestVersion.current) setBusy(''); }
  };
  const generateInference = async () => {
    if (!contextRun || !window.confirm(`Send the displayed compressed context to the ${contextRun.inferencePreview.provider} Inference model?`)) return;
    const version = requestVersion.current;
    setBusy('inference'); setError('');
    try { const value = await runRagInference({ contextFingerprint: contextRun.preview.contextFingerprint,
      inferenceFingerprint: contextRun.inferencePreview.inferenceFingerprint,
      approvalToken: contextRun.inferencePreview.approvalToken, approved: true });
      if (version === requestVersion.current) { setRun(value); setContextRun(undefined); } }
    catch (caught) { if (version === requestVersion.current) setError(safeMessage(caught)); }
    finally { if (version === requestVersion.current) setBusy(''); }
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
      subtitle="Explicit index build → selected evidence → exact request preview → separately approved Context and Inference."
    />

    <section className="rag-query-card">
      <label>RAG source<select aria-label="RAG source" value={datasetId} disabled={!!busy} onChange={(event) => {
        setDatasetId(event.target.value as RagDatasetRequest['datasetId']); setSelectedPath(''); setInspection(undefined); setSelectedLocators([]);
        setEvaluation(undefined); resetQueryOutput(true);
      }}><option value="synthetic-risk-review-v1">Bundled synthetic dataset</option><option value="selected-local-v1">Selected local file</option></select></label>
      {selectedLocal && <>
        <p className="muted">Select one file and up to 20 locators. Only those locators enter this local index after you choose Build Selected Index.</p>
        <label>RAG source file<select aria-label="RAG source file" value={selectedPath} disabled={!!busy} onChange={(event) => void selectPath(event.target.value)}>
          <option value="">Choose a file</option>{sources.map((item) => <option key={item.relativePath} value={item.relativePath}>{item.relativePath}</option>)}
        </select></label>
        {sources.length === 0 && <p className="muted">Add a supported file under <code>local-sources/</code> to begin.</p>}
        {inspection && <fieldset className="locator-list"><legend>Choose index locators</legend>
          {inspection.locators.map((locator) => <label key={locator.id} className="locator-option">
            <input type="checkbox" checked={selectedLocators.includes(locator.id)} disabled={!!busy || (!selectedLocators.includes(locator.id) && selectedLocators.length >= 20)}
              onChange={(event) => { setSelectedLocators((items) => event.target.checked ? [...items, locator.id] : items.filter((id) => id !== locator.id)); resetQueryOutput(true); }} />
            <span><strong>{locator.label}</strong><small>{locator.excerpt}</small></span>
          </label>)}
        </fieldset>}
        {inspection?.warnings.map((warning) => <p className="notice" key={warning}>{warning}</p>)}
      </>}
    </section>

    <section className="rag-status-card">
      <div>
        <span className={`rag-state ${status?.state ?? 'loading'}`}>{status?.state ?? 'loading'}</span>
        <strong>{status ? `${status.documentCount} document · ${status.chunkCount} chunks` : selectionReady ? 'Reading index status…' : 'Choose a file and locators before building'}</strong>
        <small>Local retrieval cache · explicit rebuild · no Finance Core data</small>
      </div>
      <button type="button" className="secondary-button" disabled={!selectionReady || busy !== ''} onClick={() => void rebuild()}>
        {busy === 'rebuild' ? 'Rebuilding…' : selectedLocal ? ready ? 'Rebuild Selected Index' : 'Build Selected Index' : ready ? 'Rebuild Demo Index' : 'Build Demo Index'}
      </button>
    </section>

    {status?.state === 'stale' && <p className="sandbox-notice">Source or index strategy changed. Rebuild before searching.</p>}
    {error && <p className="sandbox-error" role="alert">{error}</p>}

    <section className="rag-query-card">
      <label>Evidence question<textarea value={query} maxLength={500} disabled={busy !== ''} onChange={(event) => {
        setQuery(event.target.value); resetQueryOutput(true);
      }} /></label>
      <label>Top K<select value={topK} disabled={busy !== ''} onChange={(event) => {
        setTopK(Number(event.target.value)); resetQueryOutput(true);
      }}><option value={1}>1</option><option value={2}>2</option><option value={3}>3</option></select></label>
      <TaskChecklistEditor task={task} disabled={busy !== ''} onChange={(value) => { setTask(value); resetQueryOutput(true); }} />
      <SessionPicker value={sessionId || lineage?.sessionId || ''} disabled={busy !== ''} onChange={(value) => {
        setSessionId(value); if (value !== lineage?.sessionId) setLineage(undefined); resetQueryOutput(true);
      }} />
      <MemoryPicker runId={memoryRunId} query={query} selected={selectedMemory} disabled={!!busy}
        onChange={(items) => { setSelectedMemory(items); resetQueryOutput(); }} />
      {lineage && <p className="muted">The next prepared input creates a linked run in this session. Earlier input and output remain in Runs.</p>}
      <div className="rag-actions">
        <button type="button" className="secondary-button" disabled={!ready || query.trim().length < 3 || busy !== ''} onClick={() => void retrieve()}>
          {busy === 'search' ? 'Searching…' : '1. Retrieve Chunks'}
        </button>
        <button type="button" className="secondary-button" disabled={!ready || query.trim().length < 3 || busy !== ''} onClick={() => void buildPreview()}>
          {busy === 'preview' ? 'Building Preview…' : '2. Preview Exact Context'}
        </button>
        <button type="button" className="primary-button" disabled={!preview?.canApprove || preview.candidateEvidence.length === 0 || !modelsReady || busy !== ''} onClick={() => void generate()}>
          {busy === 'run' ? 'Running Context…' : '3. Approve Context Input'}
        </button>
      </div>
    </section>

    {search && <section className="rag-section">
      <div className="rag-section-heading"><h3>Ranked Retrieval</h3><small>Lower BM25 score ranks first.</small></div>
      {search.results.length === 0 ? <p className="muted-text">No matching chunks.</p> : <div className="rag-result-list">
        {search.results.map((item) => <article key={item.chunkId}>
          <div><strong>#{item.rank} · {item.locatorLabel}</strong><span>{item.bm25Score.toFixed(6)}</span></div>
          <p>{item.excerpt}</p>
          <small>Retrieval chunkId: {item.chunkId} → parentId: {item.parentId} → Context evidenceId: {item.evidenceId ?? 'preview to expand'}</small>
        </article>)}
      </div>}
    </section>}

    {preview && <section className="rag-section">
      <div className="rag-section-heading"><h3>Context Input Preview</h3><small>{preview.budget.estimatedInputTokens} estimated tokens</small></div>
      <div className="rag-result-list">{preview.candidateEvidence.map((item) => <article key={item.evidenceId}>
        <strong>Context evidenceId: {item.evidenceId} · {item.locatorLabel}</strong><pre>{item.text}</pre>
      </article>)}</div>
      <PreparedCallPreview call={preview.preparedCall} sources={preview.sourceBindings} />
      <ul>{preview.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
      <code className="sandbox-fingerprint">{preview.contextFingerprint}</code>
    </section>}

    {contextRun && <section className="rag-section inference-preview">
      <div className="rag-section-heading"><h3>Inference Input Preview</h3><small>Second approval · expires in 10 minutes</small></div>
      <p>Review the Context output before the second model call.</p>
      <PreparedCallPreview call={contextRun.inferencePreview.preparedCall} />
      <button type="button" className="primary-button" disabled={busy !== '' || !modelsReady} onClick={() => void generateInference()}>
        {busy === 'inference' ? 'Running Inference…' : '4. Approve Inference Input'}
      </button>
    </section>}

    {run && <section className="rag-section rag-answer">
      <div className="rag-section-heading"><h3>Grounded Answer</h3><small>{run.contextStage.provider} → {run.inferenceStage.provider}</small></div>
      <p>{run.result.answer}</p>
      {run.result.claims.map((claim) => <article key={`${claim.text}-${claim.evidenceIds.join('-')}`}>
        <p>{claim.text}</p><small>Evidence IDs: {claim.evidenceIds.join(', ')}</small>
      </article>)}
      <p className="sandbox-disclaimer">{run.result.disclaimer}</p>
    </section>}

    {!selectedLocal && <section className="rag-section">
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
    </section>}
    {selectedLocal && <p className="muted">The bundled Gold cases evaluate the synthetic dataset. Review selected-source claims, constraints, negation and citation support separately.</p>}
  </div>;
}
