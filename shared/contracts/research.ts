import { z } from 'zod';
import { preparedCallSchema } from './governance';

const evidenceIds = z.array(z.string().min(1)).refine((ids) => new Set(ids).size === ids.length, 'Evidence identifiers must be unique.');
export const researchToolCallSchema = z.object({
  callId: z.string().regex(/^[A-Za-z0-9_-]{1,80}$/), name: z.string().regex(/^[a-z][a-z0-9_.-]{1,79}$/),
  arguments: z.record(z.string(), z.unknown()),
}).strict();
export const researchDecisionSchema = z.object({
  action: z.enum(['continue', 'finish']), toolCalls: z.array(researchToolCallSchema).max(6),
  evidenceIds: evidenceIds.max(60), missingInformation: z.array(z.string()).max(20),
}).strict().superRefine((decision, context) => {
  if (decision.action === 'continue' && (!decision.toolCalls.length || decision.evidenceIds.length)) {
    context.addIssue({ code: 'custom', path: ['toolCalls'], message: 'Continue requires complete tool calls and no final evidence selection.' });
  }
  if (decision.action === 'finish' && decision.toolCalls.length) context.addIssue({ code: 'custom', path: ['toolCalls'], message: 'Finish cannot propose tool execution.' });
  if (new Set(decision.toolCalls.map((call) => call.callId)).size !== decision.toolCalls.length) {
    context.addIssue({ code: 'custom', path: ['toolCalls'], message: 'Tool call identifiers must be unique.' });
  }
});
export const researchStateSchema = z.object({
  status: z.enum(['ready', 'awaiting_context', 'exhausted', 'error', 'outcome_unknown']),
  turns: z.array(z.object({
    number: z.number().int().min(1).max(3), attemptId: z.string().min(1),
    status: z.enum(['model_pending', 'tools_pending', 'completed', 'failed', 'outcome_unknown']),
    decision: researchDecisionSchema.nullable(), errorCode: z.string().nullable(),
  }).strict()).max(3),
  selectedEvidenceIds: evidenceIds, missingInformation: z.array(z.string()), maxTurns: z.literal(3), maxToolCalls: z.literal(6),
  configurationHash: z.string().length(64),
}).strict();
export const researchPreviewSchema = z.object({
  runId: z.string().min(1), sessionId: z.string().min(1), stage: z.enum(['research', 'context', 'inference']),
  preparedCall: preparedCallSchema, fingerprint: z.string().length(64), approvalToken: z.string().nullable(), canApprove: z.boolean(),
  turn: z.number().int().min(1).max(3), maxTurns: z.literal(3), warnings: z.array(z.string()),
  contextFingerprint: z.string().length(64).nullable(),
}).strict().superRefine((preview, context) => {
  if (preview.stage !== preview.preparedCall.purpose) context.addIssue({ code: 'custom', path: ['preparedCall', 'purpose'], message: 'Preview stage and request purpose must match.' });
  if (preview.fingerprint !== preview.preparedCall.fingerprint) context.addIssue({ code: 'custom', path: ['fingerprint'], message: 'Preview and prepared request fingerprints must match.' });
  if (preview.canApprove && !preview.approvalToken) context.addIssue({ code: 'custom', path: ['approvalToken'], message: 'An approvable preview requires a fresh token.' });
});
export type ResearchPreview = z.infer<typeof researchPreviewSchema>;
export type ResearchState = z.infer<typeof researchStateSchema>;
