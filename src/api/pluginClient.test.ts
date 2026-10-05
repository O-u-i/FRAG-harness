import { afterEach, describe, expect, it, vi } from 'vitest';
import { pluginCatalogSchema } from '../../shared/contracts/plugins';
import { fetchPlugins, fetchPluginScopes, installPlugin, setPluginEnabled, uninstallPlugin } from './pluginClient';

afterEach(() => vi.unstubAllGlobals());
const entry = (id: string, protocolVersion: 1 | 2) => ({
  id, name: id, installed: true, version: '1.0.0', uiUrl: `/plugins/${id}/ui.js`,
  packageVersion: '1.0.0', packageEnabled: true, protocolVersion, capabilities: ['evidence.read'],
});

describe('generic plugin host contracts', () => {
  it('accepts two independently identified plugin protocols and an empty host', async () => {
    const catalog = { protocolVersion: 2, error: null, plugins: [entry('finance-core', 1), entry('kb', 2)] };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json(catalog)));
    await expect(fetchPlugins()).resolves.toEqual(catalog);
    expect(pluginCatalogSchema.parse({ ...catalog, plugins: [] }).plugins).toEqual([]);
    expect(pluginCatalogSchema.safeParse({ ...catalog, plugins: [entry('../escape', 2)] }).success).toBe(false);
    expect(pluginCatalogSchema.safeParse({ ...catalog, protocolVersion: 1 }).success).toBe(false);
  });

  it('requests scopes for the selected plugin and encodes explicit scope IDs', async () => {
    const scopes = { scopes: [{ id: 'selected file.md', label: 'Selected file', records: [{ id: 'section-1', label: 'Scope' }] }] };
    const fetchMock = vi.fn().mockResolvedValueOnce(Response.json(scopes)).mockResolvedValueOnce(Response.json(scopes));
    vi.stubGlobal('fetch', fetchMock);
    await expect(fetchPluginScopes('finance-core')).resolves.toEqual(scopes);
    await expect(fetchPluginScopes('kb', 'selected file.md')).resolves.toEqual(scopes);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/plugins/finance-core/evidence-scopes', '/api/plugins/kb/evidence-scopes?scopeId=selected+file.md',
    ]);
    await expect(fetchPluginScopes('../kb')).rejects.toThrow();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('pins management actions to the named plugin and accepts the installed archive identity', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(Response.json({ status: 'disabled', restartRequired: true, pluginId: 'kb' }))
      .mockResolvedValueOnce(Response.json({ status: 'installed', restartRequired: true, pluginId: 'kb' }));
    vi.stubGlobal('fetch', fetchMock);
    await setPluginEnabled('kb', false);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ enabled: false, pluginId: 'kb' });
    const archive = new Blob(['synthetic package']) as File;
    await installPlugin(archive, 'a'.repeat(64));
    expect(fetchMock.mock.calls[1][1].headers['X-Expected-Sha256']).toBe('a'.repeat(64));
    await expect(setPluginEnabled('../kb', false)).rejects.toThrow();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('surfaces safe manual removal instructions without deleting files', async () => {
    const instructions = 'Disable the plugin, stop FRAG, and manually remove .local-plugins/kb under the configured plugin root. No files were deleted.';
    const fetchMock = vi.fn().mockResolvedValueOnce(Response.json({
      error: { code: 'PLUGIN_MANUAL_REMOVAL_REQUIRED', message: instructions, issues: [] },
    }, { status: 409 }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(uninstallPlugin('kb')).rejects.toMatchObject({ message: instructions, code: 'PLUGIN_MANUAL_REMOVAL_REQUIRED', status: 409 });
    expect(fetchMock.mock.calls[0][1]).toEqual({ method: 'POST', headers: { 'X-FRAG-Plugin-Action': 'uninstall', 'X-FRAG-Plugin-Id': 'kb' } });
    await expect(uninstallPlugin('../kb')).rejects.toThrow();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
