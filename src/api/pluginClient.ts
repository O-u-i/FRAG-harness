import { pluginActionSchema, pluginCatalogSchema, pluginScopesSchema, type PluginCatalog, type PluginScopes } from '../../shared/contracts/plugins';
import { createApiRequestError } from './apiRequestError';

export async function fetchPlugins(): Promise<PluginCatalog> {
  const response = await fetch('/api/plugins');
  if (!response.ok) throw await createApiRequestError(response, `Plugin request failed (${response.status}).`);
  return pluginCatalogSchema.parse(await response.json());
}

export async function fetchPluginScopes(): Promise<PluginScopes> {
  const response = await fetch('/api/plugins/finance-core/scopes');
  if (!response.ok) throw await createApiRequestError(response, `Plugin scopes unavailable (${response.status}).`);
  return pluginScopesSchema.parse(await response.json());
}

export async function installPlugin(archive: File, expectedSha256: string): Promise<void> {
  const response = await fetch('/api/plugin-management/install', {
    method: 'POST', body: archive, headers: {
      'Content-Type': 'application/zip', 'X-Expected-Sha256': expectedSha256.trim(),
      'X-FRAG-Plugin-Action': 'install',
    },
  });
  if (!response.ok) throw await createApiRequestError(response, `Plugin installation failed (${response.status}).`);
  pluginActionSchema.parse(await response.json());
}

export async function uninstallPlugin(): Promise<void> {
  const response = await fetch('/api/plugin-management/uninstall', {
    method: 'POST', headers: { 'X-FRAG-Plugin-Action': 'uninstall' },
  });
  if (!response.ok) throw await createApiRequestError(response, `Plugin removal failed (${response.status}).`);
  pluginActionSchema.parse(await response.json());
}

export async function setPluginEnabled(enabled: boolean): Promise<void> {
  const response = await fetch('/api/plugin-management/state', {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-FRAG-Plugin-Action': 'state' },
    body: JSON.stringify({ enabled }),
  });
  if (!response.ok) throw await createApiRequestError(response, `Plugin state change failed (${response.status}).`);
  pluginActionSchema.parse(await response.json());
}
