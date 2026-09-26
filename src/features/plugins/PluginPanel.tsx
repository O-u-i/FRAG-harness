import { useEffect, useRef, useState } from 'react';
import type { PluginCatalog } from '../../../shared/contracts/plugins';
import { fetchPlugins } from '../../api/pluginClient';

type PluginModule = { mount: (element: HTMLElement, options: { apiBase: string }) => void | (() => void) };

function InstalledPlugin({ uiUrl }: { uiUrl: string }) {
  const container = useRef<HTMLDivElement>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    let dispose: void | (() => void);
    import(/* @vite-ignore */ uiUrl).then((module: PluginModule) => {
      if (!active || !container.current || typeof module.mount !== 'function') return;
      dispose = module.mount(container.current, { apiBase: '/api/plugins/finance-core' });
    }).catch(() => { if (active) setError('The installed plugin UI could not be loaded.'); });
    return () => { active = false; if (typeof dispose === 'function') dispose(); };
  }, [uiUrl]);
  return <div>{error && <p className="alert" role="alert">{error}</p>}<div ref={container} className="plugin-mount" /></div>;
}

export function PluginPanel() {
  const [catalog, setCatalog] = useState<PluginCatalog>();
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    fetchPlugins().then((value) => { if (active) setCatalog(value); })
      .catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : 'Plugin status unavailable.'); });
    return () => { active = false; };
  }, []);
  const plugin = catalog?.plugins[0];
  return <div className="plugin-layout">
    <section className="card">
      <span className="eyebrow">Optional integration</span><h2>Finance Core</h2>
      <p>Install a verified plugin package to show a read-only dashboard and select bounded finance evidence. Journal and other changes open in Finance Core.</p>
      <span className={`badge ${plugin?.installed ? 'ready' : ''}`}>{plugin?.installed ? `Installed · v${plugin.version}` : 'Not installed'}</span>
      {catalog?.error && <p className="alert" role="alert">{catalog.error}</p>}
      {error && <p className="alert" role="alert">{error}</p>}
      {!plugin?.installed && <div className="install-help">
        <h3>Install from a pinned release</h3>
        <p>Use the included PowerShell installer with the official release archive URL and its expected SHA-256, then restart FRAG. The installer also accepts a local archive.</p>
        <code>scripts/install-plugin.ps1 -ReleaseUrl &lt;release-asset-url&gt; -ExpectedSha256 &lt;sha256&gt;</code>
      </div>}
    </section>
    {plugin?.installed && plugin.uiUrl && <section className="card"><InstalledPlugin uiUrl={plugin.uiUrl} /></section>}
  </div>;
}
