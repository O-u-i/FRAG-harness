import { useEffect, useState } from 'react';
import type { HarnessConfig, HarnessPreview, HarnessRequest, HarnessRun } from '../../../shared/contracts/harness';
import type { PluginScopes } from '../../../shared/contracts/plugins';
import type { LocalFileInspectResponse, LocalFileSource } from '../../../shared/contracts/contextSource';
import { fetchLocalFileSources, inspectLocalFile } from '../../api/contextSourceClient';
import { previewHarness, runHarness } from '../../api/harnessClient';
import { fetchPlugins, fetchPluginScopes } from '../../api/pluginClient';

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
  const [preview, setPreview] = useState<HarnessPreview>();
  const [run, setRun] = useState<HarnessRun>();
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

  const selectPath = async (path: string) => {
    setSelectedPath(path); setInspection(undefined); setSelectedLocators([]); setPreview(undefined); setRun(undefined); setError('');
    if (!path) return;
    setBusy('inspect');
    try { setInspection(await inspectLocalFile(path)); }
    catch (caught) { setError(message(caught)); }
    finally { setBusy(''); }
  };
  const input: HarnessRequest = {
    goal,
    fileSelections: mode === 'local' && selectedPath && selectedLocators.length ? [{
      relativePath: selectedPath, locatorIds: selectedLocators,
      relevanceReason: 'Explicitly selected for this evidence review.',
    }] : [],
    pluginSelection: mode === 'finance-core' && workspaceId && recordIds.length
      ? { pluginId: 'finance-core', workspaceId, recordIds } : undefined,
  };
  const buildPreview = async () => {
    setBusy('preview'); setError(''); setRun(undefined);
    try { setPreview(await previewHarness(input)); }
    catch (caught) { setError(message(caught)); }
    finally { setBusy(''); }
  };
  const generate = async () => {
    if (!preview || !window.confirm(`Send ${preview.candidateEvidence.length} displayed excerpt(s) to the Context and Inference model APIs for this run?`)) return;
    setBusy('run'); setError('');
    try {
      setRun(await runHarness({ ...input, contextFingerprint: preview.contextFingerprint,
        approvalToken: preview.approvalToken, approved: true }));
      setPreview(undefined);
    } catch (caught) { setError(message(caught)); }
    finally { setBusy(''); }
  };

  return <div className="work-grid">
    <section className="card source-card">
      <div className="section-heading"><span className="eyebrow">01 / Evidence</span><h2>Select local evidence</h2>
        <p>Files stay local until you review an exact outbound preview.</p></div>
      {pluginInstalled && <div className="source-switch" role="group" aria-label="Evidence source">
        <button type="button" className={`button ${mode === 'local' ? 'primary' : ''}`} onClick={() => { setMode('local'); setPreview(undefined); setRun(undefined); }}>Local files</button>
        <button type="button" className={`button ${mode === 'finance-core' ? 'primary' : ''}`} onClick={() => { setMode('finance-core'); setPreview(undefined); setRun(undefined); }}>Finance Core</button>
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
            setPreview(undefined); setRun(undefined);
          }} />
          <span><strong>{locator.label}</strong><small>{locator.excerpt}</small></span>
        </label>)}
      </fieldset>}
      </> : <>
        {pluginError && <p className="alert" role="alert">{pluginError}</p>}
        <label className="field">Workspace
          <select value={workspaceId} onChange={(event) => { setWorkspaceId(event.target.value); setRecordIds([]); setPreview(undefined); }}>
            <option value="">Choose a Workspace</option>
            {pluginScopes?.workspaces.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.label}</option>)}
          </select></label>
        {workspaceId && <fieldset className="locator-list"><legend>Choose up to 10 records</legend>
          {pluginScopes?.workspaces.find((item) => item.id === workspaceId)?.records.map((record) => <label key={record.id} className="locator-option">
            <input type="checkbox" checked={recordIds.includes(record.id)} disabled={!recordIds.includes(record.id) && recordIds.length >= 10}
              onChange={(event) => { setRecordIds((current) => event.target.checked ? [...current, record.id] : current.filter((id) => id !== record.id)); setPreview(undefined); setRun(undefined); }} />
            <span><strong>{record.label}</strong><small>{record.id}</small></span>
          </label>)}
        </fieldset>}
      </>}
      <label className="field">Review goal
        <textarea value={goal} maxLength={500} onChange={(event) => { setGoal(event.target.value); setPreview(undefined); setRun(undefined); }} />
      </label>
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
        <div className="section-heading"><span className="eyebrow">03 / Approval</span><h2>Exact outbound preview</h2>
          <p>Approve only after checking every excerpt shown below.</p></div>
        {error && <p className="alert" role="alert">{error}</p>}
        {!preview && !run && <p className="empty-state">Choose evidence to see the exact text the models would receive.</p>}
        {preview && <>
          <div className="preview-meta"><span>{preview.candidateEvidence.length} selected excerpt(s)</span>
            <span>{preview.budget.estimatedInputTokens} estimated input tokens</span></div>
          {preview.candidateEvidence.map((item) => <article className="evidence-item" key={item.chunkId}>
            <strong>{item.locatorLabel}</strong><pre>{item.text}</pre></article>)}
          {preview.warnings.map((warning) => <p className="notice" key={warning}>{warning}</p>)}
          <button className="button primary" type="button" disabled={!config?.context.ready || !config.inference.ready || !!busy}
            onClick={() => void generate()}>{busy === 'run' ? 'Running…' : 'Approve once and run'}</button>
        </>}
        {run && <div className="answer"><span className="eyebrow">Reviewed output</span><h3>{run.result.answer}</h3>
          {run.result.claims.map((claim, index) => <p key={index}>{claim.text} <small>[{claim.chunkIds.join(', ')}]</small></p>)}
          <p className="muted">{run.result.disclaimer}</p>
        </div>}
      </section>
    </div>
  </div>;
}
