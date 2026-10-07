import { useEffect, useRef, useState } from 'react';
import type { HarnessRequest } from '../../../shared/contracts/harness';
import type { LocalFileInspectResponse, LocalFileSource } from '../../../shared/contracts/contextSource';
import type { PluginCatalog, PluginScopes } from '../../../shared/contracts/plugins';
import type { RagDatasetRequest, RagSearchResponse, RagEvaluationReport } from '../../../shared/contracts/rag';
import { fetchLocalFileSources, inspectLocalFile } from '../../api/contextSourceClient';
import { fetchPlugins, fetchPluginScopes } from '../../api/pluginClient';
import { rebuildRagIndex, searchRag, evaluateRag } from '../../api/ragClient';

type FileSelection = HarnessRequest['fileSelections'][number];
export type EvidenceSelection = { mode: 'files' | 'retrieval' | 'plugin'; ready: boolean;
  file?: FileSelection; plugin?: HarnessRequest['pluginSelection']; dataset?: RagDatasetRequest; topK: number };
export function EvidencePicker({ goal, busy, onChange }: {
  goal: string; busy: boolean; onChange: (value: EvidenceSelection) => void;
}) {
  const [mode, setMode] = useState<EvidenceSelection['mode']>('files');
  const [files, setFiles] = useState<LocalFileSource[]>([]);
  const [plugins, setPlugins] = useState<PluginCatalog['plugins']>([]);
  const [path, setPath] = useState('');
  const [inspect, setInspect] = useState<LocalFileInspectResponse>();
  const [locators, setLocators] = useState<string[]>([]);
  const [plugin, setPlugin] = useState('');
  const [scopes, setScopes] = useState<PluginScopes>();
  const [scope, setScope] = useState('');
  const [records, setRecords] = useState<string[]>([]);
  const [demo, setDemo] = useState(false);
  const [topK, setTopK] = useState(3);
  const [search, setSearch] = useState<RagSearchResponse>();
  const [evaluation, setEvaluation] = useState<RagEvaluationReport>();
  const [operation, setOperation] = useState('');
  const [error, setError] = useState('');
  const epoch = useRef(0);
  useEffect(() => {
    let active = true;
    Promise.all([fetchLocalFileSources(), fetchPlugins()]).then(([f, p]) => {
      if (active) { setFiles(f.filter((item) => item.status === 'ready')); setPlugins(p.plugins.filter((item) => item.installed && item.capabilities.includes('evidence.read'))); }
    }).catch(() => { if (active) setError('Evidence sources could not be loaded.'); });
    return () => { active = false; epoch.current += 1; };
  }, []);
  useEffect(() => {
    let active = true;
    setScopes(undefined);
    if (mode === 'plugin' && plugin) fetchPluginScopes(plugin, scope || undefined).then((value) => {
      if (active) setScopes(value);
    }).catch(() => { if (active) setError('Plugin scope could not be loaded.'); });
    return () => { active = false; };
  }, [mode, plugin, scope]);
  const file = path && locators.length ? { relativePath: path, locatorIds: locators, relevanceReason: 'Explicitly selected for this native FRAG task.' } : undefined;
  const dataset: RagDatasetRequest = demo ? { datasetId: 'synthetic-risk-review-v1' } : { datasetId: 'selected-local-v1', sourceSelection: file };
  const selectedPlugin = plugin && scope && records.length ? { pluginId: plugin, scopeId: scope, recordIds: records } : undefined;
  useEffect(() => {
    onChange({ mode, ready: mode === 'plugin' ? !!selectedPlugin : mode === 'retrieval' ? demo || !!file : !!file,
      file, plugin: selectedPlugin, dataset: mode === 'retrieval' ? dataset : undefined, topK });
  }, [mode, path, locators, plugin, scope, records, demo, topK, onChange]);
  const clear = () => { epoch.current += 1; setSearch(undefined); setEvaluation(undefined); setError(''); setOperation(''); };
  const chooseFile = async (value: string) => {
    clear(); const version = epoch.current;
    setPath(value); setInspect(undefined); setLocators([]);
    if (!value) return;
    setOperation('inspect');
    try { const result = await inspectLocalFile(value); if (epoch.current === version) setInspect(result); }
    catch { if (epoch.current === version) setError('This file could not be inspected.'); }
    finally { if (epoch.current === version) setOperation(''); }
  };
  const retrieve = async (action: 'build' | 'search' | 'evaluate') => {
    const version = epoch.current; setError(''); setOperation(action);
    try {
      if (action === 'build') { await rebuildRagIndex(dataset); if (version === epoch.current) { setSearch(undefined); setEvaluation(undefined); } }
      if (action === 'search') { const value = await searchRag({ ...dataset, query: goal, topK }); if (version === epoch.current) setSearch(value); }
      if (action === 'evaluate') { const value = await evaluateRag(dataset); if (version === epoch.current) setEvaluation(value); }
    } catch (caught) { if (version === epoch.current) setError(caught instanceof Error ? caught.message : 'Retrieval failed.'); }
    finally { if (version === epoch.current) setOperation(''); }
  };
  const disabled = busy || !!operation;
  return <section className="review-evidence">
    <label className="review-field">Evidence source<select value={mode} disabled={disabled} onChange={(event) => {
      clear(); setMode(event.target.value as EvidenceSelection['mode']); setRecords([]);
    }}><option value="files">Selected files</option><option value="retrieval">RAG retrieval</option><option value="plugin">Plugin evidence</option></select></label>
    {mode === 'retrieval' && <div className="review-row">
      <label className="review-check"><input type="checkbox" checked={demo} disabled={disabled} onChange={(e) => { clear(); setDemo(e.target.checked); }} />Synthetic demo</label>
      <label className="review-field">Results<select value={topK} disabled={disabled} onChange={(e) => { clear(); setTopK(Number(e.target.value)); }}>{[1, 3, 5, 10].map((k) => <option key={k}>{k}</option>)}</select></label>
    </div>}
    {mode !== 'plugin' && !(mode === 'retrieval' && demo) && <>
      <label className="review-field">File<select value={path} disabled={disabled} onChange={(e) => void chooseFile(e.target.value)}>
        <option value="">Choose a file</option>{files.map((item) => <option key={item.relativePath}>{item.relativePath}</option>)}
      </select></label>
      {inspect && <fieldset className="review-locators" disabled={disabled}><legend>Sections</legend>{inspect.locators.map((item) =>
        <label key={item.id}><input type="checkbox" checked={locators.includes(item.id)} disabled={disabled || (!locators.includes(item.id) && locators.length >= 20)}
          onChange={(e) => { clear(); setLocators((values) => e.target.checked ? [...values, item.id] : values.filter((id) => id !== item.id)); }} />
          <span>{item.label}<small>{item.excerpt}</small></span></label>)}</fieldset>}
    </>}
    {mode === 'plugin' && <>
      <label className="review-field">Plugin<select value={plugin} disabled={disabled} onChange={(e) => { clear(); setPlugin(e.target.value); setScope(''); setRecords([]); }}>
        <option value="">Choose a plugin</option>{plugins.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
      <label className="review-field">Scope<select value={scope} disabled={disabled} onChange={(e) => { clear(); setScope(e.target.value); setRecords([]); }}>
        <option value="">Choose a scope</option>{scopes?.scopes.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
      {scope && <fieldset className="review-locators"><legend>Records</legend>{scopes?.scopes.find((item) => item.id === scope)?.records.map((item) =>
        <label key={item.id}><input type="checkbox" checked={records.includes(item.id)} disabled={disabled || (!records.includes(item.id) && records.length >= 10)}
          onChange={(e) => { clear(); setRecords((values) => e.target.checked ? [...values, item.id] : values.filter((id) => id !== item.id)); }} /><span>{item.label}</span></label>)}</fieldset>}
    </>}
    {mode === 'retrieval' && <div className="review-actions">{(['build', 'search', 'evaluate'] as const).map((action) =>
      <button type="button" key={action} disabled={disabled || (!demo && !file)} onClick={() => void retrieve(action)}>
        {action === 'build' ? 'Build selected index' : action === 'search' ? 'Search' : 'Evaluate retrieval'}</button>)}</div>}
    {operation && <p role="status">{operation === 'inspect' ? 'Reading selected file…' : 'Processing retrieval…'}</p>}
    {error && <p className="review-alert" role="alert">{error}</p>}
    {search && <details open><summary>{search.results.length} retrieved results</summary>{search.results.map((item) =>
      <article className="review-excerpt" key={item.chunkId}><strong>{item.rank}. {item.locatorLabel}</strong><p>{item.excerpt}</p></article>)}</details>}
    {evaluation && <p className="review-meta">Retrieval: {evaluation.status} · Recall@3 {evaluation.metrics.recallAt3.toFixed(2)}</p>}
  </section>;
}
