import { pluginActionSchema, pluginCatalogSchema, pluginIdSchema, pluginScopesSchema, type PluginCatalog, type PluginScopes } from '../../shared/contracts/plugins';
import { createApiRequestError } from './apiRequestError';

export async function fetchPlugins(): Promise<PluginCatalog> {
  const response = await fetch('/api/plugins');
  if (!response.ok) throw await createApiRequestError(response, `Plugin request failed (${response.status}).`);
  return pluginCatalogSchema.parse(await response.json());
}

export async function fetchPluginScopes(pluginId: string, scopeId?: string): Promise<PluginScopes> {
  pluginIdSchema.parse(pluginId);
  const query = scopeId ? `?${new URLSearchParams({ scopeId })}` : '';
  const response = await fetch(`/api/plugins/${pluginId}/evidence-scopes${query}`);
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

export async function uninstallPlugin(pluginId: string): Promise<void> {
  pluginIdSchema.parse(pluginId);
  const response = await fetch('/api/plugin-management/uninstall', {
    method: 'POST', headers: { 'X-FRAG-Plugin-Action': 'uninstall', 'X-FRAG-Plugin-Id': pluginId },
  });
  if (!response.ok) throw await createApiRequestError(response, `Plugin removal failed (${response.status}).`);
  pluginActionSchema.parse(await response.json());
}

export async function setPluginEnabled(pluginId: string, enabled: boolean): Promise<void> {
  pluginIdSchema.parse(pluginId);
  const response = await fetch('/api/plugin-management/state', {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-FRAG-Plugin-Action': 'state' },
    body: JSON.stringify({ enabled, pluginId }),
  });
  if (!response.ok) throw await createApiRequestError(response, `Plugin state change failed (${response.status}).`);
  pluginActionSchema.parse(await response.json());
}
