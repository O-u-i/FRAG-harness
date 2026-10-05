import { z } from 'zod';

export const pluginIdSchema = z.string().min(1).max(63).regex(/^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/);
export const pluginCatalogSchema = z.object({
  protocolVersion: z.literal(2),
  error: z.string().nullable(),
  plugins: z.array(z.object({
    id: pluginIdSchema, name: z.string(), installed: z.boolean(),
    version: z.string().nullable(), uiUrl: z.string().nullable(), packageVersion: z.string().nullable(),
    packageEnabled: z.boolean().nullable(), protocolVersion: z.union([z.literal(1), z.literal(2)]).nullable(),
    capabilities: z.array(z.string().min(1).max(64)),
  }).strict()),
}).strict();
export type PluginCatalog = z.infer<typeof pluginCatalogSchema>;

export const pluginActionSchema = z.object({
  status: z.enum(['installed', 'uninstalled', 'enabled', 'disabled']), restartRequired: z.literal(true),
  pluginId: pluginIdSchema.optional(),
}).strict();

export const pluginScopesSchema = z.object({ scopes: z.array(z.object({
  id: z.string(), label: z.string(), records: z.array(z.object({ id: z.string(), label: z.string() }).strict()),
}).strict()) }).strict();
export type PluginScopes = z.infer<typeof pluginScopesSchema>;
