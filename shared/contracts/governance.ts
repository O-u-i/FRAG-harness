import { z } from 'zod';

export const qualityFactSchema = z.object({ status: z.enum(['known', 'unknown']), detail: z.string().nullable() }).strict()
  .refine((value) => (value.status === 'known') === Boolean(value.detail), 'Known metadata requires detail.');
export const sourceAssessmentSchema = z.object({
  authority: qualityFactSchema, freshness: qualityFactSchema, relevance: qualityFactSchema, provenance: qualityFactSchema,
  permission: z.literal('selected_read_only'),
}).strict();
export const sourceIdentitySchema = z.object({
  kind: z.enum(['local_file', 'synthetic', 'fc_record', 'plugin_record']), namespace: z.string().min(1),
  resourceId: z.string().min(1), workspaceId: z.string().nullable(),
}).strict().refine((value) => (['fc_record', 'plugin_record'].includes(value.kind)) === Boolean(value.workspaceId), 'Plugin records require a source scope.');
const uniqueIds = z.array(z.string().min(1)).min(1).refine((values) => new Set(values).size === values.length);
export const sourceBindingSchema = z.object({
  identity: sourceIdentitySchema, revision: z.string().min(1), parserVersion: z.string().min(1),
  locatorIds: uniqueIds, evidenceIds: uniqueIds, assessment: sourceAssessmentSchema,
}).strict();
export const checklistItemSchema = z.object({
  id: z.string().min(1).max(80), text: z.string().min(1).max(500), blocking: z.boolean(),
  status: z.enum(['pending', 'met', 'missing', 'unknown']), reviewed: z.boolean(),
}).strict();
export const taskContractSchema = z.object({
  templateId: z.literal('evidence-review-v1'), checklist: z.array(checklistItemSchema).max(20),
}).strict().refine((value) => new Set(value.checklist.map((item) => item.id)).size === value.checklist.length,
  'Checklist identifiers must be unique.');
export const preparedCallSchema = z.object({
  schemaVersion: z.union([z.literal(1), z.literal(2)]), purpose: z.enum(['context', 'inference', 'research']),
  provider: z.enum(['fake', 'openai', 'ollama', 'vscode']), model: z.string(), endpoint: z.string(),
  transport: z.enum(['fake', 'responses-v1', 'pi-responses-v1', 'vscode-lm-v1']), body: z.string(), binding: z.string(),
  timeoutSeconds: z.number().positive().max(120), maxRetries: z.literal(0),
  estimatedInputTokens: z.number().int().positive(), inputBudget: z.number().int().positive(),
  reservedPercent: z.number().int().min(0).max(100), runTokenLimit: z.number().int().positive(),
  fingerprint: z.string().length(64),
}).strict().superRefine((value, ctx) => {
  for (const key of ['body', 'binding'] as const) {
    try { const parsed: unknown = JSON.parse(value[key]);
      if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error();
    } catch { ctx.addIssue({code: 'custom', path: [key], message: 'Expected a serialized JSON object.'}); }
  }
  try {
    const body = JSON.parse(value.body) as Record<string, unknown>;
    const binding = JSON.parse(value.binding) as Record<string, unknown>;
    if (value.transport === 'vscode-lm-v1') {
      const native = z.object({
        messages: z.tuple([z.object({ role: z.literal('user'), content: z.string() }).strict(),
                          z.object({ role: z.literal('user'), content: z.string() }).strict()]),
        options: z.object({ modelOptions: z.object({ max_tokens: z.number().int().positive().max(2000) }).strict() }).strict(),
      }).strict();
      if (!native.safeParse(body).success || value.schemaVersion !== 2 || value.provider !== 'vscode'
          || binding.approvalBoundary !== 'language_model_api'
          || !/^[a-f0-9]{64}$/.test(String(binding.modelConfigurationRevision))
          || binding.providerHttpBody !== 'unknown' || binding.providerInternalRetries !== 'unknown') {
        ctx.addIssue({code: 'custom', path: ['body'], message: 'Model API arguments and configuration must match.'});
      }
    } else {
      // A retired transport may be decoded for reports, never used to prepare or execute a new call.
      const validInput = value.transport === 'pi-responses-v1' ? Array.isArray(body.input) : typeof body.input === 'string';
      if (value.schemaVersion !== 1 || value.provider === 'vscode' || body.model !== value.model
          || typeof body.instructions !== 'string' || !validInput || !Number.isInteger(body.max_output_tokens)
          || Number(body.max_output_tokens) <= 0 || body.store !== false || !Array.isArray(body.tools)) {
        ctx.addIssue({code: 'custom', path: ['body'], message: 'Prepared body does not match the request contract.'});
      }
    }
  } catch { /* Invalid JSON already reported. */ }
});

export const loopLimitsSchema = z.object({
  modelTurns: z.number().int().min(1).max(3), toolCalls: z.number().int().min(1).max(6),
  toolTimeoutSeconds: z.number().int().min(1).max(10), toolResultBytes: z.number().int().min(1).max(16384),
  loopOutputTokens: z.number().int().min(1).max(800), runTokenLimit: z.number().int().positive().max(30000),
  serialTools: z.literal(true),
}).strict();
export const cliDefinitionSchema = z.object({
  toolInputSchema: z.string().nullable().optional(),
  name: z.string().min(1), version: z.string().regex(/^\d+\.\d+\.\d+$/), executable: z.string().min(1),
  subcommand: z.array(z.string()).min(1), workingDirectory: z.string().min(1), environmentNames: z.array(z.string()),
  inputSchema: z.string(), outputSchema: z.string(), ioFormat: z.literal('json-stdin-stdout'),
}).strict();
export const toolDefinitionSchema = z.object({
  name: z.string().regex(/^[a-z][a-z0-9_.-]{1,79}$/), version: z.string().regex(/^\d+\.\d+\.\d+$/),
  inputSchema: z.string(), outputSchema: z.string(), readOnly: z.literal(true),
  sourceKinds: z.array(z.enum(['local_file', 'synthetic'])).min(1), carrier: z.enum(['native', 'cli']), carrierId: z.string().min(1),
  timeoutSeconds: z.number().int().min(1).max(10), outputBytes: z.number().int().min(1).max(16384),
}).strict();
export const loopDefinitionSchema = z.object({
  name: z.enum(['fixed', 'research']), version: z.string().regex(/^\d+\.\d+\.\d+$/),
  stages: z.array(z.enum(['research', 'context', 'inference'])), limits: loopLimitsSchema,
}).strict();
export const capabilityCatalogSchema = z.object({
  policyVersion: z.string(), taskTemplates: z.array(z.string()), cli: z.array(cliDefinitionSchema),
  tools: z.array(toolDefinitionSchema), loops: z.array(loopDefinitionSchema), planned: z.array(z.enum(['cli', 'kb_tools', 'research'])),
}).strict();
export type PreparedCall = z.infer<typeof preparedCallSchema>;
export type TaskContract = z.infer<typeof taskContractSchema>;
export type SourceBinding = z.infer<typeof sourceBindingSchema>;
