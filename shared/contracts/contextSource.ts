import { z } from 'zod';

export const localFileSourceSchema = z.object({
  relativePath: z.string(), category: z.string(),
  format: z.enum(['md', 'txt', 'pdf', 'docx', 'csv', 'xlsx', 'html']).nullable(),
  sizeBytes: z.number().int().nonnegative(), modifiedAt: z.string(), sha256: z.string().length(64).nullable(),
  status: z.enum(['ready', 'unsupported', 'too_large', 'error']), statusReason: z.string().nullable(),
}).strict();

export const sourceLocatorSchema = z.object({
  id: z.string(), kind: z.enum(['document', 'section', 'page', 'rows', 'sheet']), label: z.string(), excerpt: z.string(),
}).strict();

export const localFileInspectResponseSchema = z.object({
  source: localFileSourceSchema, locators: z.array(sourceLocatorSchema), warnings: z.array(z.string()),
}).strict();

export type LocalFileSource = z.infer<typeof localFileSourceSchema>;
export type SourceLocator = z.infer<typeof sourceLocatorSchema>;
export type LocalFileInspectResponse = z.infer<typeof localFileInspectResponseSchema>;
