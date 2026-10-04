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
const nativeResearchReplayV1Schema = z.object({
  version: z.literal(1), calls: z.array(z.object({
    callId: z.string().min(1).max(256), itemId: z.string().min(1).max(256),
    name: z.enum(['kb_read', 'kb_search']), argumentsText: z.string().min(2).max(16384),
    hostCallId: z.string().regex(/^pi_[a-f0-9]{64}$/),
  }).strict()).min(1).max(6),
}).strict().superRefine((value, context) => {
  for (const key of ['callId', 'itemId', 'hostCallId'] as const) {
    if (new Set(value.calls.map(call => call[key])).size !== value.calls.length) {
      context.addIssue({code: 'custom', path: ['calls'], message: 'Native call identifiers must be unique.'});
    }
  }
});
const rawId = z.string().min(1).max(256);
const rawOutputItemSchema = z.discriminatedUnion('type', [
  z.object({type: z.literal('reasoning'), id: rawId,
    summary: z.array(z.object({type: z.literal('summary_text'), text: z.string()}).strict()),
    content: z.array(z.object({type: z.literal('reasoning_text'), text: z.string()}).strict()).optional(),
    status: z.literal('completed').optional(), encrypted_content: z.string().nullable().optional(),
  }).strict(),
  z.object({type: z.literal('message'), id: rawId, role: z.literal('assistant'), status: z.literal('completed'),
    phase: z.enum(['commentary', 'final_answer']).nullable().optional(),
    content: z.array(z.object({type: z.literal('output_text'), text: z.string(),
      annotations: z.array(z.never()).max(0), logprobs: z.array(z.never()).max(0).optional(),
    }).strict()).min(1),
  }).strict(),
  z.object({type: z.literal('function_call'), id: rawId, call_id: rawId, name: z.enum(['kb_read', 'kb_search']),
    arguments: z.string().min(1).max(16384), status: z.literal('completed').optional(),
  }).strict(),
]);
const nativeResearchReplayV2Schema = z.object({
  version: z.literal(2), calls: z.array(nativeResearchReplayV1Schema.shape.calls.element).max(6),
  outputItems: z.array(rawOutputItemSchema).min(1).max(64),
}).strict().superRefine((value, context) => {
  const fail = (message: string) => context.addIssue({code: 'custom', path: ['outputItems'], message});
  if (new TextEncoder().encode(JSON.stringify(value.outputItems)).byteLength > 256 * 1024) fail('Raw output exceeds bounds.');
  if (new Set(value.outputItems.map(item => item.id)).size !== value.outputItems.length) fail('Raw item IDs must be unique.');
  for (const key of ['callId', 'itemId', 'hostCallId'] as const) {
    if (new Set(value.calls.map(call => call[key])).size !== value.calls.length) fail('Native call identifiers must be unique.');
  }
  const calls = value.outputItems.filter(item => item.type === 'function_call');
  if (calls.some(item => new TextEncoder().encode(item.arguments).byteLength > 16384)) fail('Raw arguments exceed byte bounds.');
  if (calls.length !== value.calls.length || calls.some((item, index) => {
    const call = value.calls[index];
    return item.call_id !== call?.callId || item.id !== call?.itemId || item.name !== call?.name || item.arguments !== call?.argumentsText;
  })) fail('Raw calls and host mapping must match in order.');
  const text = value.outputItems.filter(item => item.type === 'message' && item.phase !== 'commentary')
    .flatMap(item => item.type === 'message' ? item.content.map(part => part.text) : []).join('');
  if (calls.length && (text.trim() || value.outputItems.some(item => item.type === 'reasoning' && !item.encrypted_content))) {
    fail('Tool continuations need ciphertext and cannot contain final text.');
  }
  if (!calls.length && !text.trim()) fail('Finish needs final text.');
});
export const nativeResearchReplaySchema = z.discriminatedUnion('version', [nativeResearchReplayV1Schema, nativeResearchReplayV2Schema]);
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
