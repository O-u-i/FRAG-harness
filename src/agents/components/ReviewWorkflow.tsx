import { useCallback, useEffect, useRef, useState } from 'react';
import type { AgentView } from '../../../shared/contracts/agents';
import type { HarnessConfig } from '../../../shared/contracts/harness';
import type { SettingsView } from '../../../shared/contracts/reviewSettings';
import { preparedCallSchema } from '../../../shared/contracts/governance';
import type { MemorySelection } from '../../../shared/contracts/memory';
import { cancelAgent, executeAgent, recoverAgent } from '../../api/agentClient';
import { fetchReviewSettings, prepareFromSettings, saveConversationSettings } from '../../api/reviewSettingsClient';
import { MemoryPicker } from '../../features/memory/MemoryPicker';
import { TaskChecklistEditor } from '../../features/runtime/TaskChecklistEditor';
import { EvidencePicker, type EvidenceSelection } from './EvidencePicker';
import { RequestPreview, ReviewReport } from './ReviewReport';
import { checklistTask, conversationSettings } from './settingsModel';
import { Stepper } from './Navigation';
import GlideSelect from './reactbits/GlideSelect';

export function ReviewWorkflow({ view, config, settings, onChange, onSettings, openSettings, visible }: {
  view: AgentView; config?: HarnessConfig; settings: SettingsView; onChange: (value: AgentView) => void;
  onSettings: (settings: SettingsView) => void; openSettings: () => void; visible: boolean;
}) {
  const turn = view.session.turns.at(-1);
  const inherited = settings.conversation.settings;
  const [initialEvidence] = useState(inherited?.evidence ?? settings.project.settings);
  const [selection, setSelection] = useState<EvidenceSelection>({ mode: initialEvidence.mode, ready: false, topK: inherited?.topK ?? settings.application.settings.topK });
  const [task, setTask] = useState(() => checklistTask(inherited?.checklist ?? settings.application.settings.checklist));
  const [memory, setMemory] = useState<MemorySelection[]>([]);
  const [research, setResearch] = useState(inherited?.research ?? settings.application.settings.researchInCustom);
  const [custom, setCustom] = useState(false), [scope,setScope] = useState('run');
  const [dirty,setDirty] = useState(false), [consent,setConsent] = useState(false);
  const [busy,setBusy] = useState(''), [error,setError] = useState('');
  const [viewStep,setViewStep] = useState<number | null>(null), [reportTab,setReportTab] = useState('output');
  const alive = useRef(true), actionActive = useRef(false), reportEntry = useRef<HTMLDivElement>(null);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const running = turn?.state === 'running', report = view.report;
  const preview = dirty || !running || !report?.configuration ? null : view.preview;
  const call = preview ? preparedCallSchema.parse(preview.preview.preparedCall) : undefined;
  const stage = preview?.stage ?? (report?.modelOutput ? 'review' : report?.context ? 'inference' : report?.research ? 'research' : 'context');
  const special = custom || report?.configuration?.origin === 'run' || report?.configuration?.origin === 'conversation';
  const withResearch = report ? !!report.research : custom ? research && selection.mode !== 'plugin' : !!inherited?.research;
  const names = [...(special ? ['Evidence'] : []), ...(withResearch ? ['Research'] : []), 'Context','Inference','Review'];
  const reached = custom && (!report || dirty) ? 0 : Math.max(0,names.indexOf(stage[0].toUpperCase()+stage.slice(1)));
  const current = viewStep === null ? reached : Math.min(viewStep,reached);
  const historical = current < reached;
  useEffect(() => { setConsent(false); setViewStep(null); }, [call?.fingerprint, view.session.version, stage]);
  useEffect(() => { setConsent(false); }, [report?.run.version]);
  useEffect(() => { if (!visible) setConsent(false); }, [visible]);
  const invalidate = () => {setDirty(true);setConsent(false);setViewStep(null);};
  const changeSelection = useCallback((value: EvidenceSelection) => {setSelection(value);setMemory([]);if(value.mode==='plugin')setResearch(false);}, []);
  const act = async (name: string, operation: () => Promise<AgentView>) => {
    if (actionActive.current) return;
    actionActive.current = true; setBusy(name);setError('');setConsent(false);
    try {const result = await operation();if(alive.current){setDirty(false);onChange(result);setViewStep(null);}}
    catch(error){if(alive.current)setError(error instanceof Error ? error.message : 'Review action failed.');}
    finally{actionActive.current=false;if(alive.current)setBusy('');}
  };
  const prepare = async () => {
    let saved = settings;
    if (custom && scope === 'conversation') {
      await saveConversationSettings(view,saved.conversation.revision,conversationSettings(selection,research,task));
      saved = await fetchReviewSettings(view.session.sessionId);
      if (saved.application.revision !== settings.application.revision || saved.project.revision !== settings.project.revision) {
        onSettings(saved);
        throw new Error('Defaults changed while saving. Review the current settings before preparing again.');
      }
    }
    onSettings(saved);
    return prepareFromSettings(view,saved,custom && scope === 'run' ? conversationSettings(selection,research,task) : null,task,memory);
  };
  if (!turn) return <p className="review-empty">Send a native task to begin.</p>;
  const ready = !!config?.context.ready && !!config.inference.ready;
  const blocking = ((!report || dirty) ? task : report.reviews.at(-1)?.checklist ?? report.selection.task).checklist.filter((item) => item.blocking && (item.status !== 'met' || !item.reviewed));
  const evidenceCount = report?.selection.candidateEvidence.length ?? 0;
  const canApprove = !!preview && evidenceCount > 0 && !blocking.length && (!('canApprove' in preview.preview) || preview.preview.canApprove !== false) && !!preview.preview.approvalToken && ready && running && !historical;
  const canRecover = report?.configuration && !report.modelOutput && !['outcome_unknown','accepted','rejected','error'].includes(report.run.status) && running;
  const showSetup = running && (!report || dirty);
  const snapshot = report?.requests.filter((item) => item.stage.toLowerCase() === names[current].toLowerCase()).at(-1);
  const reportLink = () => {setReportTab('output');reportEntry.current?.scrollIntoView({block:'start',behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});};
  return <div className="review-workflow">
    <div className="review-sticky-entries"><Stepper names={names} current={current} reached={reached} onView={(index) => {setConsent(false);setViewStep(index);}} />
      <div className="review-entry-actions"><button type="button" disabled={current===0 || !!busy} onClick={() => {setConsent(false);setViewStep(current-1);}}>Back to view</button>
        {historical && <button type="button" onClick={() => setViewStep(null)}>Current stage</button>}
        <button type="button" disabled={!report} onClick={reportLink}>Output</button><button type="button" onClick={openSettings}>Settings</button></div>
    </div>
    <section className="review-task"><span className="review-meta">Native task</span><h2>{turn.text}</h2>
      <span className="review-status" role="status">{turn.state==='cancelled'?'Task cancelled':busy==='execute'?'Running approved stage':preview?'Waiting for approval':report?.run.status.replace(/_/g,' ')??'Choose task configuration'}</span>
      {running && <p className="review-meta">The native reply is complete. Review controls this task; no model calls occur while waiting for configuration or approval.</p>}
      {running && <button type="button" disabled={!!busy} onClick={() => void act('cancel',() => cancelAgent(view))}>Cancel task</button>}
    </section>
    {turn.state==='cancelled' && <section className="review-alert" role="status"><strong>Task cancelled. Evidence selection and approval are disabled.</strong>
      <p>Previous approvals are invalid. Send a new task in the native conversation; saved settings remain available.</p>
      <ol><li>Remove any native Context attachments; select evidence in Settings or this task instead.</li>
        <li>After “Task saved”, this page switches to the new task automatically. Use Sessions if you opened another conversation.</li></ol></section>}
    {historical && report && <section className="review-snapshot"><h3>{names[current]} · saved snapshot</h3><p className="review-meta">Read-only viewing. Back does not edit, recover, roll back or resend a model request.</p>
      {names[current]==='Evidence' ? <><p>{evidenceCount} excerpts</p><pre>{JSON.stringify(report.selection.sourceBindings,null,2)}</pre></>
        : snapshot ? <><RequestPreview call={snapshot.preparedCall} />{snapshot.output && <pre>{JSON.stringify(snapshot.output,null,2)}</pre>}</>
          : <p className="review-meta">No saved request for this stage.</p>}
    </section>}
    {!historical && showSetup && <section className="review-task-setup"><h3>Configure this task</h3>
      <p className="review-meta">{inherited?'Conversation configuration':'Project defaults'} · Fresh evidence and request bindings on every native task. No automatic history inclusion.</p>
      <div className="review-actions"><button type="button" aria-pressed={!custom} disabled={!!busy} onClick={() => {setCustom(false);invalidate();}}>Use saved configuration</button>
        <button type="button" aria-pressed={custom} disabled={!!busy} onClick={() => {setCustom(true);invalidate();}}>Special configuration</button></div>
      {inherited && <button type="button" disabled={!!busy} onClick={() => void act('settings',async () => {
        await saveConversationSettings(view,settings.conversation.revision,null);
        onSettings(await fetchReviewSettings(view.session.sessionId)); setCustom(false); return view;
      })}>Clear conversation override for future preparations</button>}
      {custom && <><div className="review-field">Apply to<GlideSelect ariaLabel="Apply to" value={scope} disabled={!!busy} options={[{value:'run',label:'Current run'},{value:'conversation',label:'Conversation'}]} onChange={setScope} /></div>
        <EvidencePicker goal={turn.text} busy={!!busy} initial={initialEvidence} initialTopK={selection.topK} onChange={changeSelection} />
        <label className="review-check"><input type="checkbox" checked={research} disabled={!!busy || selection.mode==='plugin'} onChange={(event) => setResearch(event.target.checked)} />Research before Context (optional)</label></>}
      <details><summary>Checklist and background memory</summary><TaskChecklistEditor task={task} disabled={!!busy} onChange={(value) => {setTask(value);invalidate();}} />
        <MemoryPicker runId={report?.run.id} query={turn.text} selected={memory} disabled={!!busy} onChange={(value) => {setMemory(value);invalidate();}} /></details>
      {!ready && <p className="review-alert">Selected native model is not ready. Open Settings for the model setup guide, then refresh readiness.</p>}
      {blocking.length>0 && <p className="review-alert">Blocking checklist: {blocking.map((item)=>item.text).join('; ')}. Set each item to Met and confirm Reviewed by me before approval.</p>}
      <button type="button" className="review-primary" disabled={!!busy || (custom && !selection.ready)} onClick={() => void act('prepare',prepare)}>Preview {withResearch?'Research':'Context'}</button>
    </section>}
    {error && <p className="review-alert" role="alert">{error}</p>}{busy && <p role="status">{busy==='execute'?'Running the approved stage…':'Updating the current task…'}</p>}
    {!historical && call && preview && <section className="review-approval"><h3>{stage[0].toUpperCase()+stage.slice(1)} approval</h3><RequestPreview call={call} />
      {'warnings' in preview.preview && preview.preview.warnings.map((warning:string) => <p className="review-meta" key={warning}>{warning}</p>)}
      {!ready && <p className="review-alert">Native model is not ready. Open Settings, configure the model in VS Code, then prepare a fresh request.</p>}
      {!evidenceCount && <p className="review-alert">No evidence matched the selected scope. Customize the source, build its index explicitly if needed, or adjust retrieval. Prepare a new preview; approval cannot bypass this check.</p>}
      {blocking.length>0 && <p className="review-alert">Blocking items need human review: {blocking.map((item)=>item.text).join('; ')}. Customize the checklist and prepare a linked new run.</p>}
      {!canApprove && ready && evidenceCount>0 && !blocking.length && <p className="review-alert">No valid one-use approval is available. Prepare a fresh exact preview; source and budget checks remain enforced.</p>}
      <p className="review-meta">Input changes create a linked new run. Completed calls are not undone. You can confirm background memory after this source-bound preview, then prepare again.</p>
      <button type="button" disabled={!!busy} onClick={() => {setCustom(true);invalidate();}}>Customize and prepare again</button>
      <label className="review-check"><input type="checkbox" checked={consent} disabled={!canApprove || !!busy} onChange={(event) => setConsent(event.target.checked)} />I reviewed this exact request</label>
      <button type="button" className="review-primary" disabled={!consent || !canApprove || !!busy} onClick={() => void act('execute',() => executeAgent(view))}>Approve {stage}</button>
    </section>}
    {!historical && !preview && canRecover && !dirty && <button type="button" className="review-primary" disabled={!!busy} onClick={() => void act('recover',() => recoverAgent(view))}>Preview next stage</button>}
    {report?.run.status==='outcome_unknown' && <p className="review-alert">Unknown external outcome. Reconcile it before starting another task; this run will not resend.</p>}
    {report && !report.configuration && !preview && <p className="review-meta">Legacy saved run · read-only history. Send a new native task for the current Settings workflow; old request bindings are not rewritten.</p>}
    {report && <div ref={reportEntry} className="review-report-area"><h3>Run report</h3><ReviewReport report={report} tab={reportTab} onTabChange={setReportTab}
      readOnly={historical || turn.state==='cancelled' || !report.configuration} onChange={(value) => onChange({...view,report:value,preview:null})} /></div>}
  </div>;
}
