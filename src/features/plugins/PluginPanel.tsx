import { useEffect, useRef, useState } from 'react';
import type { PluginCatalog } from '../../../shared/contracts/plugins';
import { fetchPlugins, installPlugin, setPluginEnabled, uninstallPlugin } from '../../api/pluginClient';

type PluginModule = { mount: (element: HTMLElement, options: { apiBase: string }) => void | (() => void) };

function InstalledPlugin({ pluginId, uiUrl }: { pluginId: string; uiUrl: string }) {
  const container = useRef<HTMLDivElement>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    let dispose: void | (() => void);
    import(/* @vite-ignore */ uiUrl).then((module: PluginModule) => {
      if (!active || !container.current || typeof module.mount !== 'function') return;
      dispose = module.mount(container.current, { apiBase: `/api/plugins/${pluginId}` });
    }).catch(() => { if (active) setError('The installed plugin UI could not be loaded.'); });
    return () => { active = false; if (typeof dispose === 'function') dispose(); };
  }, [pluginId, uiUrl]);
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
  const uninstall = async (pluginId: string) => {
    setBusy(true); setError(''); setNotice('');
    try {
      await uninstallPlugin(pluginId);
      setCatalog(await fetchPlugins());
      setNotice('Plugin package removed. Restart FRAG to finish unloading it.');
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Plugin removal failed.'); }
    finally { setBusy(false); }
  };
  const toggleEnabled = async (pluginId: string, enabled: boolean) => {
    setBusy(true); setError(''); setNotice('');
    try {
      await setPluginEnabled(pluginId, enabled);
      setCatalog(await fetchPlugins());
      setNotice(enabled ? 'Plugin enabled. Restart FRAG to activate it.' : 'Plugin disabled. Its routes and UI are now hidden.');
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Plugin state change failed.'); }
    finally { setBusy(false); }
  };
  return <div className="plugin-layout">
    <section className="card">
      <span className="eyebrow">Optional integrations</span><h2>Plugins</h2>
      <p>Install a verified plugin package to select read-only evidence. Changes to external records stay in their own application.</p>
      {catalog?.error && <p className="alert" role="alert">{catalog.error}</p>}
      {error && <p className="alert" role="alert">{error}</p>}
      {notice && <p className="notice" role="status">{notice}</p>}
      <div className="install-help">
        <h3>Install a pinned archive</h3>
        <p>Choose a trusted plugin ZIP and enter its published SHA-256. FRAG checks the archive and manifest before installation.</p>
        <label className="field">Plugin archive
          <input type="file" accept=".zip,application/zip" disabled={busy} onChange={(event) => setArchive(event.target.files?.[0])} />
        </label>
        <label className="field">Expected SHA-256
          <input type="text" value={sha256} maxLength={64} spellCheck={false} autoComplete="off" disabled={busy}
            onChange={(event) => setSha256(event.target.value)} placeholder="64 hexadecimal characters" />
        </label>
        <button className="button primary" type="button" disabled={busy || !archive || !/^[a-f\d]{64}$/i.test(sha256) || archive.size > 20 * 1024 * 1024}
          onClick={() => void install()}>{busy ? 'Working…' : 'Install plugin'}</button>
        <p className="muted">Restart FRAG after any plugin change. External applications remain separate.</p>
      </div>
    </section>
    {catalog?.plugins.map((plugin) => <section className="card" key={plugin.id}>
      <h3>{plugin.name}</h3>
      <span className={`badge ${plugin.installed ? 'ready' : ''}`}>{plugin.installed ? `Active · v${plugin.version}` : plugin.packageVersion ? `Package v${plugin.packageVersion} on disk` : 'Not installed'}</span>
      {plugin.packageVersion && plugin.packageEnabled !== null && <button className="button" type="button" disabled={busy}
        onClick={() => void toggleEnabled(plugin.id, !plugin.packageEnabled)}>{plugin.packageEnabled ? 'Disable plugin' : 'Enable plugin'}</button>}
      {plugin.packageVersion && <button className="button" type="button" disabled={busy} onClick={() => void uninstall(plugin.id)}>Removal instructions</button>}
      {plugin.installed && plugin.uiUrl && <InstalledPlugin pluginId={plugin.id} uiUrl={plugin.uiUrl} />}
    </section>)}
  </div>;
}
