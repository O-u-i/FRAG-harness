import { z } from 'zod';
import { recoveryPreviewSchema, runReportSchema } from './runtime';
import { researchPreviewSchema } from './research';

const agentPreviewSchema = z.union([recoveryPreviewSchema, z.object({
  runId: z.string(), kind: z.enum(['harness', 'rag']), stage: z.enum(['research', 'context', 'inference']),
  contextFingerprint: z.string().length(64), preview: researchPreviewSchema,
}).strict().superRefine((value, ctx) => {
  if (value.preview.runId !== value.runId || value.preview.stage !== value.stage || value.preview.preparedCall.purpose !== value.stage)
    ctx.addIssue({ code: 'custom', message: 'Research preview must match its run and stage.' });
})]);

export const agentSessionSchema = z.object({
  sessionId: z.string().regex(/^[a-f0-9]{32}$/), resource: z.string().startsWith('frag:/'),
  version: z.number().int().positive(), turns: z.array(z.object({
    id: z.string(), text: z.string(), createdAt: z.string(),
    state: z.enum(['running', 'complete', 'cancelled']), runId: z.string().nullable(),
  }).strict()),
}).strict();
export const agentViewSchema = z.object({
  session: agentSessionSchema, report: runReportSchema.nullable(), preview: agentPreviewSchema.nullable(),
}).strict();
export type AgentSession = z.infer<typeof agentSessionSchema>;
export type AgentView = z.infer<typeof agentViewSchema>;
