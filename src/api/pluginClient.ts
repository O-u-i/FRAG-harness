import { pluginCatalogSchema, pluginScopesSchema, type PluginCatalog, type PluginScopes } from '../../shared/contracts/plugins';
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
