import { useCallback, useState } from 'react';
import type { HarnessConfig } from '../../../shared/contracts/harness';
import type { SettingsView } from '../../../shared/contracts/reviewSettings';
import { saveApplicationSettings, saveProjectSettings } from '../../api/reviewSettingsClient';
import { TaskChecklistEditor } from '../../features/runtime/TaskChecklistEditor';
import { EvidencePicker, type EvidenceSelection } from './EvidencePicker';
import { checklistTask, evidenceSettings } from './settingsModel';
import GlideSelect from './reactbits/GlideSelect';

export function ReviewSettings({ saved, config, reload }: { saved: SettingsView; config?: HarnessConfig; reload: () => Promise<void> }) {
  const [application, setApplication] = useState(saved.application.settings);
  const [task, setTask] = useState(() => checklistTask(saved.application.settings.checklist));
  const [source, setSource] = useState<EvidenceSelection>();
  const [busy, setBusy] = useState(false), [message, setMessage] = useState('');
  const changeSource = useCallback((value: EvidenceSelection) => setSource(value), []);
  const save = async (operation: () => Promise<void>) => {
    if (busy) return;
    setBusy(true); setMessage('');
    try { await operation(); await reload(); setMessage('Saved. Future preparations use these defaults; frozen requests are unchanged.'); }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Settings could not be saved.'); }
    finally { setBusy(false); }
  };
  return <section className="review-settings"><span className="review-meta">Configuration, not execution</span><h1>Settings</h1>
    <p className="review-meta">Application preferences are shared within this VS Code instance. Concrete sources stay in this project. Saving never indexes files or calls a model.</p>
    <section className="review-settings-group"><h2>Application preferences</h2>
      <div className="review-field">Preferred evidence mode<GlideSelect ariaLabel="Preferred evidence mode" size="lg" value={application.mode} disabled={busy}
        options={[{value:'files',label:'Selected files'},{value:'retrieval',label:'RAG retrieval'},{value:'plugin',label:'Plugin evidence'}]}
        onChange={(mode) => setApplication({...application,mode:mode as typeof application.mode})} /></div>
      <div className="review-field">Default retrieval results<GlideSelect ariaLabel="Default retrieval results" value={String(application.topK)} disabled={busy}
        options={['1','3','5','10']} onChange={(value) => setApplication({...application,topK:Number(value) as typeof application.topK})} /></div>
      <label className="review-check"><input type="checkbox" checked={application.researchInCustom} disabled={busy}
        onChange={(event) => setApplication({...application,researchInCustom:event.target.checked})} />Suggest Research for special configurations</label>
      <p className="review-meta">Normal tasks begin at Context. This strategy is only a suggestion when customizing; every Research turn still requires exact approval.</p>
      <details><summary>Checklist template</summary><p className="review-meta">Only item text and blocking flags are saved. Each task starts pending and unreviewed.</p>
        <TaskChecklistEditor task={task} disabled={busy} onChange={setTask} /></details>
      <button type="button" className="review-primary" disabled={busy} onClick={() => void save(() => saveApplicationSettings(saved.application.revision,
        {...application, checklist:task.checklist.map(({id,text,blocking}) => ({id,text,blocking}))}))}>Save application preferences</button>
    </section>
    <section className="review-settings-group"><h2>Project evidence</h2><p className="review-meta">Explicit file and locator selection. New tasks reread and bind current source revisions; old Research and Context are never reused.</p>
      <EvidencePicker initial={saved.project.settings} initialTopK={application.topK} goal="" busy={busy} onChange={changeSource} />
      <button type="button" className="review-primary" disabled={busy || !source?.ready}
        onClick={() => source && void save(() => saveProjectSettings(saved.project.revision,evidenceSettings(source)))}>Save project evidence</button>
    </section>
    <section className="review-settings-group"><h2>Model readiness</h2>
      <p role="status">Context: {config ? config.context.ready ? 'Ready' : 'Not ready' : 'Not checked'} · Inference: {config ? config.inference.ready ? 'Ready' : 'Not ready' : 'Not checked'}</p>
      <p className="review-meta">Readiness belongs to the model saved on the current native task. Select a conversation first. Enumeration does not verify authentication, billing or response quality.</p>
      <p className="review-meta">Choose the model in the native conversation. Configure its provider and saved effort in VS Code Models. FRAG does not edit keys, provider routes or safety limits.</p>
      <button type="button" disabled={busy} onClick={() => void reload().catch(() => setMessage('Readiness could not be refreshed.'))}>Refresh readiness</button>
      <a href="/review/help" target="_blank" rel="noreferrer">Model setup and approval guide</a>
    </section>
    {message && <p className="review-alert" role="status">{message}</p>}
  </section>;
}
