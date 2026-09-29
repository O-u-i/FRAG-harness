import { useEffect, useState } from 'react';
import { fetchHarnessConfig } from './api/harnessClient';
import { checkBackendHealth } from './api/healthClient';
import { RagLab } from './components/analysis/RagLab';
import { HarnessPanel } from './features/harness/HarnessPanel';
import { PluginPanel } from './features/plugins/PluginPanel';
import type { HarnessConfig } from '../shared/contracts/harness';

type Page = 'harness' | 'rag' | 'plugins';
const pages: { id: Page; number: string; label: string; description: string }[] = [
  { id: 'harness', number: '01', label: 'Harness', description: 'Select, preview, approve, run' },
  { id: 'rag', number: '02', label: 'RAG lab', description: 'Build, search, evaluate' },
  { id: 'plugins', number: '03', label: 'Plugins', description: 'Optional integrations' },
];

export default function App() {
  const [page, setPage] = useState<Page>('harness');
  const [config, setConfig] = useState<HarnessConfig>();
  const [health, setHealth] = useState<'checking' | 'online' | 'offline'>('checking');
  useEffect(() => {
    let active = true;
    Promise.all([fetchHarnessConfig(), checkBackendHealth()]).then(([value]) => {
      if (active) { setConfig(value); setHealth('online'); }
    }).catch(() => { if (active) setHealth('offline'); });
    return () => { active = false; };
  }, []);
  const current = pages.find((item) => item.id === page)!;
  return <div className="app-frame">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark">F<span>·</span></div><div><strong>FRAG</strong><small>HARNESS / v1.1.0</small></div></div>
      <div className="sidebar-label">WORKSPACE</div>
      <nav aria-label="Primary navigation">{pages.map((item) => <button key={item.id} type="button"
        className={`nav-item ${page === item.id ? 'active' : ''}`} onClick={() => setPage(item.id)}>
        <span className="nav-number">{item.number}</span><span><strong>{item.label}</strong><small>{item.description}</small></span>
      </button>)}</nav>
      <div className="sidebar-bottom"><span className={`status-dot ${health}`} /><div><strong>{health === 'online' ? 'Local backend online' : health === 'offline' ? 'Backend unavailable' : 'Checking backend'}</strong><small>Evidence stays under your control</small></div></div>
    </aside>
    <main className="main-content">
      <header className="topbar"><span>LOCAL INTELLIGENCE / {current.label.toUpperCase()}</span><span className="topbar-version">PROTOCOL 1.1.0</span></header>
      <div className="page-content">
        <div className="page-intro"><div><span className="eyebrow">FRAG / {current.number}</span><h1>{page === 'harness' ? 'Evidence, governed.' : page === 'rag' ? 'Retrieval you can inspect.' : 'Extend when needed.'}</h1>
          <p>{page === 'harness' ? 'A local workflow for selecting evidence, checking exactly what leaves the machine, and reviewing a cited answer.' : page === 'rag' ? 'A transparent retrieval sandbox using a synthetic dataset and deterministic evaluation.' : 'Install trusted capabilities at runtime. The core harness runs independently.'}</p></div>
          <div className="intro-symbol" aria-hidden="true">{current.number}<span>/03</span></div></div>
        {page === 'harness' && <HarnessPanel config={config} />}
        {page === 'rag' && <RagLab config={config} />}
        {page === 'plugins' && <PluginPanel />}
      </div>
    </main>
  </div>;
}
