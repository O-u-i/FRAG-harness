import { z } from 'zod';

export const pluginCatalogSchema = z.object({
  protocolVersion: z.literal(1),
  error: z.string().nullable(),
  plugins: z.array(z.object({
    id: z.literal('finance-core'), name: z.string(), installed: z.boolean(),
    version: z.string().nullable(), uiUrl: z.string().nullable(), packageVersion: z.string().nullable(),
    packageEnabled: z.boolean().nullable(),
  }).strict()),
}).strict();
export type PluginCatalog = z.infer<typeof pluginCatalogSchema>;

export const pluginActionSchema = z.object({
  status: z.enum(['installed', 'uninstalled', 'enabled', 'disabled']), restartRequired: z.literal(true),
}).strict();

export const pluginScopesSchema = z.object({ workspaces: z.array(z.object({
  id: z.string(), label: z.string(), records: z.array(z.object({ id: z.string(), label: z.string() }).strict()),
}).strict()) }).strict();
export type PluginScopes = z.infer<typeof pluginScopesSchema>;
