import { useEffect, useRef, useState } from 'react';
import type { HarnessConfig, HarnessContextRun, HarnessPreview, HarnessRequest, HarnessRun } from '../../../shared/contracts/harness';
import type { PluginScopes } from '../../../shared/contracts/plugins';
import type { LocalFileInspectResponse, LocalFileSource } from '../../../shared/contracts/contextSource';
import { fetchLocalFileSources, inspectLocalFile } from '../../api/contextSourceClient';
import { previewHarness, runHarness, runHarnessInference } from '../../api/harnessClient';
import { fetchPlugins, fetchPluginScopes } from '../../api/pluginClient';
import { PreparedCallPreview } from '../../components/common/PreparedCallPreview';
import type { TaskContract } from '../../../shared/contracts/governance';
import { emptyReviewTask, TaskChecklistEditor } from '../runtime/TaskChecklistEditor';
import { SessionPicker } from '../runtime/SessionPicker';
import type { MemorySelection } from '../../../shared/contracts/memory';
import { MemoryPicker } from '../memory/MemoryPicker';

function message(error: unknown): string {
  return error instanceof Error ? error.message : 'The request could not be completed.';
}

export function HarnessPanel({ config }: { config?: HarnessConfig }) {
  const [sources, setSources] = useState<LocalFileSource[]>([]);
  const [pluginInstalled, setPluginInstalled] = useState(false);
  const [pluginScopes, setPluginScopes] = useState<PluginScopes>();
  const [pluginError, setPluginError] = useState('');
  const [mode, setMode] = useState<'local' | 'finance-core'>('local');
  const [workspaceId, setWorkspaceId] = useState('');
  const [recordIds, setRecordIds] = useState<string[]>([]);
  const [selectedPath, setSelectedPath] = useState('');
  const [inspection, setInspection] = useState<LocalFileInspectResponse>();
  const [selectedLocators, setSelectedLocators] = useState<string[]>([]);
  const [goal, setGoal] = useState('Summarize the selected evidence and identify uncertainty.');
  const [task, setTask] = useState<TaskContract>(emptyReviewTask);
  const [sessionId, setSessionId] = useState('');
  const [lineage, setLineage] = useState<{ runId: string; sessionId: string }>();
  const [memoryRunId, setMemoryRunId] = useState<string>();
  const [selectedMemory, setSelectedMemory] = useState<MemorySelection[]>([]);
  const [previewInput, setPreviewInput] = useState<HarnessRequest>();
  const [preview, setPreview] = useState<HarnessPreview>();
  const [contextRun, setContextRun] = useState<HarnessContextRun>();
  const [run, setRun] = useState<HarnessRun>();
  const requestVersion = useRef(0);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    fetchLocalFileSources().then((items) => { if (active) setSources(items.filter((item) => item.status === 'ready')); })
      .catch((caught) => { if (active) setError(message(caught)); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    fetchPlugins().then(async (catalog) => {
      if (!catalog.plugins[0]?.installed) return;
      if (active) setPluginInstalled(true);
      try {
        const scopes = await fetchPluginScopes();
        if (active) setPluginScopes(scopes);
      } catch {
        if (active) setPluginError('Finance Core scopes are unavailable. Check the plugin and FC service.');
      }
    }).catch(() => undefined);
    return () => { active = false; };
  }, []);

  const resetOutput = (clearMemory = false) => {
    if (clearMemory) { setSelectedMemory([]); setMemoryRunId(undefined); }
    requestVersion.current += 1;
    setPreview(undefined); setPreviewInput(undefined); setContextRun(undefined); setRun(undefined);
    setBusy('');
  };
  const selectPath = async (path: string) => {
    resetOutput(true);
    const version = requestVersion.current;
    setSelectedPath(path); setInspection(undefined); setSelectedLocators([]); setError('');
    if (!path) return;
    setBusy('inspect');
    try { const value = await inspectLocalFile(path); if (version === requestVersion.current) setInspection(value); }
    catch (caught) { if (version === requestVersion.current) setError(message(caught)); }
    finally { if (version === requestVersion.current) setBusy(''); }
  };
  const input: HarnessRequest = {
    goal, task, selectedMemory, sessionId: sessionId || lineage?.sessionId || undefined, parentRunId: lineage?.runId,
    fileSelections: mode === 'local' && selectedPath && selectedLocators.length ? [{
      relativePath: selectedPath, locatorIds: selectedLocators,
      relevanceReason: 'Explicitly selected for this evidence review.',
    }] : [],
    pluginSelection: mode === 'finance-core' && workspaceId && recordIds.length
      ? { pluginId: 'finance-core', workspaceId, recordIds } : undefined,
  };
  const buildPreview = async () => {
    resetOutput();
    const version = requestVersion.current;
    setBusy('preview'); setError('');
    try { const value = await previewHarness(input); if (version === requestVersion.current) {
      setPreview(value); setPreviewInput(input);
      setMemoryRunId(value.runId || undefined);
      if (value.runId && value.sessionId) setLineage({ runId: value.runId, sessionId: value.sessionId });
    } }
    catch (caught) { if (version === requestVersion.current) setError(message(caught)); }
    finally { if (version === requestVersion.current) setBusy(''); }
  };
  const generate = async () => {
    if (!preview?.canApprove || !previewInput || !window.confirm(`Approve the displayed request to ${preview.preparedCall.endpoint}?`)) return;
    const version = requestVersion.current;
    setBusy('run'); setError('');
    try {
      const value = await runHarness({ ...previewInput, contextFingerprint: preview.contextFingerprint,
        approvalToken: preview.approvalToken, approved: true });
      if (version === requestVersion.current) { setContextRun(value); setPreview(undefined); }
    } catch (caught) { if (version === requestVersion.current) setError(message(caught)); }
    finally { if (version === requestVersion.current) setBusy(''); }
  };
  const generateInference = async () => {
    if (!contextRun || !window.confirm(`Send the displayed compressed context to the ${contextRun.inferencePreview.provider} Inference model API?`)) return;
    const version = requestVersion.current;
    setBusy('inference'); setError('');
    try {
      const value = await runHarnessInference({ contextFingerprint: contextRun.preview.contextFingerprint,
        inferenceFingerprint: contextRun.inferencePreview.inferenceFingerprint,
        approvalToken: contextRun.inferencePreview.approvalToken, approved: true });
      if (version === requestVersion.current) { setRun(value); setContextRun(undefined); }
    } catch (caught) { if (version === requestVersion.current) setError(message(caught)); }
    finally { if (version === requestVersion.current) setBusy(''); }
  };

  return <div className="work-grid">
    <section className="card source-card">
      <div className="section-heading"><span className="eyebrow">01 / Evidence</span><h2>Select local evidence</h2>
        <p>Files stay local until you review an exact outbound preview.</p></div>
      {pluginInstalled && <div className="source-switch" role="group" aria-label="Evidence source">
        <button type="button" className={`button ${mode === 'local' ? 'primary' : ''}`} onClick={() => { setMode('local'); resetOutput(true); }}>Local files</button>
        <button type="button" className={`button ${mode === 'finance-core' ? 'primary' : ''}`} onClick={() => { setMode('finance-core'); resetOutput(true); }}>Finance Core</button>
      </div>}
      {mode === 'local' ? <>
      <label className="field">Source file
        <select value={selectedPath} onChange={(event) => void selectPath(event.target.value)}>
          <option value="">Choose a file</option>
          {sources.map((item) => <option key={item.relativePath} value={item.relativePath}>{item.relativePath}</option>)}
        </select>
      </label>
      {sources.length === 0 && <p className="muted">Add a supported file under <code>local-sources/</code> to begin.</p>}
      {inspection && <fieldset className="locator-list"><legend>Choose sections or locators</legend>
        {inspection.locators.map((locator) => <label key={locator.id} className="locator-option">
          <input type="checkbox" checked={selectedLocators.includes(locator.id)} disabled={!selectedLocators.includes(locator.id) && selectedLocators.length >= 20} onChange={(event) => {
            setSelectedLocators((current) => event.target.checked
              ? [...current, locator.id] : current.filter((id) => id !== locator.id));
            resetOutput(true);
          }} />
          <span><strong>{locator.label}</strong><small>{locator.excerpt}</small></span>
        </label>)}
      </fieldset>}
      </> : <>
        {pluginError && <p className="alert" role="alert">{pluginError}</p>}
        <label className="field">Workspace
          <select value={workspaceId} onChange={(event) => { setWorkspaceId(event.target.value); setRecordIds([]); resetOutput(true); }}>
            <option value="">Choose a Workspace</option>
            {pluginScopes?.workspaces.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.label}</option>)}
          </select></label>
        {workspaceId && <fieldset className="locator-list"><legend>Choose up to 10 records</legend>
          {pluginScopes?.workspaces.find((item) => item.id === workspaceId)?.records.map((record) => <label key={record.id} className="locator-option">
            <input type="checkbox" checked={recordIds.includes(record.id)} disabled={!recordIds.includes(record.id) && recordIds.length >= 10}
              onChange={(event) => { setRecordIds((current) => event.target.checked ? [...current, record.id] : current.filter((id) => id !== record.id)); resetOutput(true); }} />
            <span><strong>{record.label}</strong><small>{record.id}</small></span>
          </label>)}
        </fieldset>}
      </>}
      <label className="field">Review goal
        <textarea value={goal} maxLength={500} onChange={(event) => { setGoal(event.target.value); resetOutput(true); }} />
      </label>
      <TaskChecklistEditor task={task} disabled={!!busy} onChange={(value) => { setTask(value); resetOutput(true); }} />
      <SessionPicker value={sessionId || lineage?.sessionId || ''} disabled={!!busy} onChange={(value) => {
        setSessionId(value); if (value !== lineage?.sessionId) setLineage(undefined); resetOutput(true);
      }} />
      {lineage && <p className="muted">The next prepared input creates a linked run in this session. Earlier input and output remain in Runs.</p>}
      <MemoryPicker runId={memoryRunId} query={goal} selected={selectedMemory} disabled={!!busy}
        onChange={(items) => { setSelectedMemory(items); resetOutput(); }} />
      <button className="button primary" type="button" disabled={!(mode === 'local' ? selectedLocators.length : recordIds.length) || goal.trim().length < 3 || !!busy}
        onClick={() => void buildPreview()}>{busy === 'preview' ? 'Preparing…' : 'Preview exact context'}</button>
    </section>

    <div className="result-column">
      <section className="card model-card">
        <div className="section-heading"><span className="eyebrow">02 / Model routes</span><h2>Two API stages</h2></div>
        <div className="model-stages">
          {(['context', 'inference'] as const).map((stage, index) => <article key={stage}>
            <span className="stage-number">0{index + 1}</span>
            <div><strong>{stage === 'context' ? 'Context LLM' : 'Inference LLM'}</strong>
              <small>{stage === 'context' ? 'Compresses approved evidence' : 'Produces a cited answer'}</small></div>
            <span className={`badge ${config?.[stage].ready ? 'ready' : ''}`}>
              {config ? `${config[stage].provider} · ${config[stage].ready ? 'ready' : 'setup needed'}` : 'checking'}
            </span>
          </article>)}
        </div>
      </section>

      <section className="card preview-card">
        <div className="section-heading"><span className="eyebrow">{run ? '04 / Review' : contextRun ? '04 / Inference approval' : '03 / Context approval'}</span>
          <h2>{run ? 'Answer for review' : contextRun ? 'Inference input preview' : 'Context input preview'}</h2>
          {!run && !contextRun && <p>Approve only after checking every excerpt shown below.</p>}</div>
        {error && <p className="alert" role="alert">{error}</p>}
        {!preview && !contextRun && !run && <p className="empty-state">Choose evidence to see the exact text the Context model would receive.</p>}
        {preview && <>
          <div className="preview-meta"><span>{preview.candidateEvidence.length} selected excerpt(s)</span>
            <span>{preview.budget.estimatedInputTokens} estimated input tokens</span></div>
          {preview.candidateEvidence.map((item) => <article className="evidence-item" key={item.evidenceId}>
            <strong>{item.locatorLabel}</strong><pre>{item.text}</pre></article>)}
          <PreparedCallPreview call={preview.preparedCall} sources={preview.sourceBindings} />
          {!preview.canApprove && <p className="alert">Review and satisfy all blocking checklist items before approving.</p>}
          {preview.warnings.map((warning) => <p className="notice" key={warning}>{warning}</p>)}
          <button className="button primary" type="button" disabled={!preview.canApprove || !config?.context.ready || !config.inference.ready || !!busy}
            onClick={() => void generate()}>{busy === 'run' ? 'Running Context…' : 'Approve Context input'}</button>
        </>}
        {contextRun && <div className="inference-preview">
          <p className="muted">Review the Context output before approving the second model call. Approval expires in 10 minutes.</p>
          <PreparedCallPreview call={contextRun.inferencePreview.preparedCall} />
          <button className="button primary" type="button" disabled={!!busy || !config?.inference.ready}
            onClick={() => void generateInference()}>{busy === 'inference' ? 'Running Inference…' : 'Approve Inference input'}</button>
        </div>}
        {run && <div className="answer"><h3>{run.result.answer}</h3>
          {run.result.claims.map((claim, index) => <p key={index}>{claim.text} <small>[{claim.evidenceIds.join(', ')}]</small></p>)}
          <p className="muted">{run.result.disclaimer}</p>
        </div>}
      </section>
    </div>
  </div>;
}
