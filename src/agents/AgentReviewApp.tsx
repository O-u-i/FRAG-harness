import { useCallback, useEffect, useRef, useState } from 'react';
import type { AgentSession, AgentView } from '../../shared/contracts/agents';
import type { RunRecord, RunReport } from '../../shared/contracts/runtime';
import type { SettingsView } from '../../shared/contracts/reviewSettings';
import { fetchReviewSettings } from '../api/reviewSettingsClient';
import { MotionConfig } from 'motion/react';
import { fetchAgentSessions, fetchAgentView } from '../api/agentClient';
import { fetchRuns, fetchRunReport } from '../api/runtimeClient';
import { MemoryPanel } from '../features/memory/MemoryPanel';
import { LineSidebar, type ReviewPage, type MemorySection } from './components/Navigation';
import { ReviewSettings } from './components/ReviewSettings';
import { ReviewWorkflow } from './components/ReviewWorkflow';
import { ReviewReport } from './components/ReviewReport';
import './styles.css';
import './navigation.css';

function Runs({ sessionId }: { sessionId: string }) {
  const [runs, setRuns] = useState<RunRecord[]>([]), [id, setId] = useState('');
  const [report, setReport] = useState<RunReport>(), [error, setError] = useState('');
  const epoch = useRef(0);
  useEffect(() => {
    let active = true;
    fetchRuns(sessionId).then((items) => { if (active) { setRuns(items); setId(items[0]?.id ?? ''); } })
      .catch(() => { if (active) setError('Run history could not be loaded.'); });
    return () => { active = false; epoch.current += 1; };
  }, [sessionId]);
  useEffect(() => {
    const version = ++epoch.current;
    setReport(undefined); setError('');
    if (id) fetchRunReport(id).then((value) => { if (version === epoch.current) setReport(value); })
      .catch(() => { if (version === epoch.current) setError('This run could not be loaded.'); });
    return () => { epoch.current += 1; };
  }, [id]);
  return <><h2>Runs</h2><label className="review-field">Saved run<select value={id} onChange={(e) => setId(e.target.value)}>
    <option value="">Choose a run</option>{runs.map((item) => <option key={item.id} value={item.id}>{item.id.slice(0, 8)} · {item.kind} · {item.status}</option>)}
  </select></label>{error && <p className="review-alert" role="alert">{error}</p>}
  {report && <ReviewReport key={report.run.id} report={report} onChange={setReport} readOnly />}</>;
}

export default function AgentReviewApp() {
  const [page, setPage] = useState<ReviewPage>('workflow');
  const [memorySection, setMemorySection] = useState<MemorySection>('candidates');
  const [settings, setSettings] = useState<SettingsView>();
  const [sessionId, setSessionId] = useState(() => new URLSearchParams(window.location.search).get('sessionId') ?? '');
  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [view, setView] = useState<AgentView>();
  const [error, setError] = useState('');
  const requestEpoch = useRef(0);
  const settingsEpoch = useRef(0);
  const viewRevision = useRef(0);
  const updateView = useCallback((value: AgentView) => {
    viewRevision.current += 1;
    setView((current) => {
      if (current?.session.sessionId === value.session.sessionId &&
          (current.session.version > value.session.version ||
           (current.report?.run.id === value.report?.run.id &&
            (current.report?.run.version ?? 0) > (value.report?.run.version ?? 0)))) return current;
      return value;
    });
  }, []);
  const reloadSettings = useCallback(async () => {
    const epoch = ++settingsEpoch.current;
    const saved = await fetchReviewSettings(sessionId || undefined);
    if (epoch === settingsEpoch.current) setSettings(saved);
    if (sessionId) { const current = await fetchAgentView(sessionId); if (epoch === settingsEpoch.current) updateView(current); }
  }, [sessionId, updateView]);
  useEffect(() => { setSettings(undefined); void reloadSettings().catch(() => setError('Review settings could not be loaded.'));
    return () => { settingsEpoch.current += 1; }; }, [reloadSettings]);
  useEffect(() => {
    let active = true;
    document.title = 'FRAG Review · 1.10.3';
    fetchAgentSessions().then((items) => {
      if (active) setSessions(items);
    }).catch(() => { if (active) setError('Start the local FRAG Agents host to connect.'); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    const version = ++requestEpoch.current;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setView(undefined); setError('');
    const poll = async () => {
      if (version !== requestEpoch.current) return;
      if (sessionId) {
        const revision = viewRevision.current;
        try { const value = await fetchAgentView(sessionId); if (version === requestEpoch.current && revision === viewRevision.current) { updateView(value); setError(''); } }
        catch { if (version === requestEpoch.current && revision === viewRevision.current) { setView(undefined); setError('This native session is unavailable. Choose a current FRAG session.'); } }
      } else {
        try { const items = await fetchAgentSessions(); if (version === requestEpoch.current) setSessions(items); }
        catch { if (version === requestEpoch.current) setError('FRAG Agents host is unavailable.'); }
      }
      if (version === requestEpoch.current) timer = setTimeout(() => void poll(), 1500);
    };
    void poll();
    return () => { requestEpoch.current += 1; clearTimeout(timer); };
  }, [sessionId, updateView]);
  const chooseSession = (id: string) => {
    requestEpoch.current += 1; setView(undefined); setSessionId(id); setPage('workflow');
    window.history.replaceState(null, '', `/review${id ? `?sessionId=${encodeURIComponent(id)}` : ''}`);
  };
  const turn = view?.session.turns[view.session.turns.length - 1];
  return <MotionConfig reducedMotion="user"><div className="review-root">
    <main className="review-main"><header className="review-header"><div><span className="review-connection" aria-label={view ? 'Connected' : 'Waiting for session'} data-online={!!view} /><strong>{view?.project?.name ?? 'FRAG Review'}</strong></div>
      <button type="button" className="review-session-button" onClick={() => chooseSession('')}>Sessions</button></header>
      <div className="review-content">
        {error && <p className="review-alert" role="alert">{error}</p>}
        {!sessionId && page === 'workflow' && <section className="review-welcome"><h1>Select a native session</h1><p>Choose FRAG under Remote, send a task, then open its review here.</p>
          <label className="review-field">Session<select value="" onChange={(e) => chooseSession(e.target.value)}><option value="">Choose a FRAG session</option>
            {sessions.map((item) => <option key={item.sessionId} value={item.sessionId}>{item.turns[item.turns.length - 1]?.text ?? 'New FRAG session'}</option>)}</select></label>
        </section>}
        {view && settings && <div hidden={page !== 'workflow'}><ReviewWorkflow key={`${sessionId}:${turn?.id ?? 'draft'}`} view={view} config={view.config}
          settings={settings} onSettings={setSettings} onChange={updateView} openSettings={() => setPage('settings')} visible={page === 'workflow'} /></div>}
        {view && page === 'runs' && <Runs key={sessionId} sessionId={sessionId} />}
        {settings && <div hidden={page !== 'settings'}><ReviewSettings saved={settings} config={turn ? view?.config : undefined} reload={reloadSettings} /></div>}
        <div hidden={page !== 'memory'}><h2>Memory · {memorySection}</h2><MemoryPanel section={memorySection} onSectionChange={setMemorySection} /></div>

      </div>
    </main>
    <aside className="review-sidebar"><a className="review-brand" href="/review" aria-label="FRAG Review home"><span>F</span><strong>FRAG</strong></a>
      <LineSidebar active={page} onSelect={setPage} memory={memorySection} onMemory={setMemorySection} />
      <footer><a href="/review/help" target="_blank" rel="noreferrer">Documentation</a><span>1.10.3</span></footer>
    </aside>
  </div></MotionConfig>;
}
