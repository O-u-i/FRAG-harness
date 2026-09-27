import { useEffect, useRef, useState } from 'react';
import type { PluginCatalog } from '../../../shared/contracts/plugins';
import { fetchPlugins, installPlugin, setPluginEnabled, uninstallPlugin } from '../../api/pluginClient';

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
  const [archive, setArchive] = useState<File>();
  const [sha256, setSha256] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  useEffect(() => {
    let active = true;
    fetchPlugins().then((value) => { if (active) setCatalog(value); })
      .catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : 'Plugin status unavailable.'); });
    return () => { active = false; };
  }, []);
  const plugin = catalog?.plugins[0];
  const install = async () => {
    if (!archive) return;
    setBusy(true); setError(''); setNotice('');
    try {
      await installPlugin(archive, sha256);
      setCatalog(await fetchPlugins());
      setArchive(undefined);
      setNotice('Plugin package installed. Restart FRAG to activate it.');
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Plugin installation failed.'); }
    finally { setBusy(false); }
  };
  const uninstall = async () => {
    if (!window.confirm('Uninstall all local Finance Core plugin versions? Restart FRAG after removal.')) return;
    setBusy(true); setError(''); setNotice('');
    try {
      await uninstallPlugin();
      setCatalog(await fetchPlugins());
      setNotice('Plugin package removed. Restart FRAG to finish unloading it.');
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Plugin removal failed.'); }
    finally { setBusy(false); }
  };
  const toggleEnabled = async (enabled: boolean) => {
    setBusy(true); setError(''); setNotice('');
    try {
      await setPluginEnabled(enabled);
      setCatalog(await fetchPlugins());
      setNotice(`Plugin ${enabled ? 'enabled' : 'disabled'}. Restart FRAG to apply the change.`);
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Plugin state change failed.'); }
    finally { setBusy(false); }
  };
  return <div className="plugin-layout">
    <section className="card">
      <span className="eyebrow">Optional integration</span><h2>Finance Core</h2>
      <p>Install a verified plugin package to show a read-only dashboard and select bounded finance evidence. Journal and other changes open in Finance Core.</p>
      <span className={`badge ${plugin?.installed ? 'ready' : ''}`}>{plugin?.installed ? `Active · v${plugin.version}` : plugin?.packageVersion ? `Package v${plugin.packageVersion} on disk` : 'Not installed'}</span>
      {catalog?.error && <p className="alert" role="alert">{catalog.error}</p>}
      {error && <p className="alert" role="alert">{error}</p>}
      {notice && <p className="notice" role="status">{notice}</p>}
      <div className="install-help">
        <h3>Install a pinned archive</h3>
        <p>Choose a trusted Finance Core plugin ZIP and enter its published SHA-256. FRAG checks the archive and manifest before installation.</p>
        <label className="field">Plugin archive
          <input type="file" accept=".zip,application/zip" disabled={busy} onChange={(event) => setArchive(event.target.files?.[0])} />
        </label>
        <label className="field">Expected SHA-256
          <input type="text" value={sha256} maxLength={64} spellCheck={false} autoComplete="off" disabled={busy}
            onChange={(event) => setSha256(event.target.value)} placeholder="64 hexadecimal characters" />
        </label>
        <button className="button primary" type="button" disabled={busy || !archive || !/^[a-f\d]{64}$/i.test(sha256) || archive.size > 20 * 1024 * 1024}
          onClick={() => void install()}>{busy ? 'Working…' : 'Install plugin'}</button>
        {plugin?.packageVersion && plugin.packageEnabled !== null && <button className="button" type="button" disabled={busy}
          onClick={() => void toggleEnabled(!plugin.packageEnabled)}>{plugin.packageEnabled ? 'Disable plugin' : 'Enable plugin'}</button>}
        {plugin?.packageVersion && <button className="button" type="button" disabled={busy} onClick={() => void uninstall()}>Uninstall plugin</button>}
        <p className="muted">Restart FRAG after any plugin change. Finance Core remains a separate application.</p>
      </div>
    </section>
    {plugin?.installed && plugin.uiUrl && <section className="card"><InstalledPlugin uiUrl={plugin.uiUrl} /></section>}
  </div>;
}
