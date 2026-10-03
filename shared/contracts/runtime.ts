import { z } from 'zod';
import { preparedCallSchema, sourceBindingSchema, taskContractSchema } from './governance';
import { harnessPreviewSchema } from './harness';
import { stageResultSchema } from './modelStages';
import { inferencePreviewSchema, ragContextCompressionSchema, ragEvidenceSchema, ragGroundedAnswerSchema, ragPreviewSchema } from './rag';

export const runStatusSchema = z.enum(['ready_context', 'awaiting_inference', 'awaiting_review', 'paused', 'accepted', 'rejected', 'error', 'outcome_unknown']);
export const outcomeSchema = z.enum(['PASS', 'FAIL', 'ERROR', 'NOT_RUN', 'UNDETERMINED']);
export const sessionCreateSchema = z.object({ title: z.string().min(1).max(200) }).strict();
export const sessionRecordSchema = z.object({ id: z.string(), title: z.string(), createdAt: z.string() }).strict();
export const runRecordSchema = z.object({
  id: z.string(), sessionId: z.string(), parentRunId: z.string().nullable(), kind: z.enum(['harness', 'rag']),
  status: runStatusSchema, createdAt: z.string(), updatedAt: z.string(), version: z.number().int().min(1), activeCallId: z.string().nullable(),
}).strict();
export const selectionSnapshotSchema = z.object({
  goal: z.string(), sourceBindings: z.array(sourceBindingSchema), candidateEvidence: z.array(ragEvidenceSchema),
  task: taskContractSchema, input: z.record(z.string(), z.unknown()),
}).strict();
export const attemptRecordSchema = z.object({
  id: z.string(), stage: z.enum(['context', 'inference']), status: z.enum(['prepared', 'dispatching', 'completed', 'failed', 'outcome_unknown']),
  preparedCall: preparedCallSchema, createdAt: z.string(), finishedAt: z.string().nullable().optional(),
  usage: stageResultSchema.shape.usage.nullable().optional(), output: z.record(z.string(), z.unknown()).nullable().optional(),
  errorCode: z.string().nullable().optional(), structuralValidation: outcomeSchema,
  outputDigest: z.string().length(64).nullable().optional(),
}).strict();
export const reviewRequestSchema = z.object({
  target: z.string().min(1).max(64), decision: z.enum(['accepted', 'rejected', 'paused']), checklist: taskContractSchema, note: z.string().max(4000),
}).strict();
export const reviewRecordSchema = reviewRequestSchema.extend({ id: z.string(), createdAt: z.string() }).strict();
export const revisionRequestSchema = z.object({ result: ragGroundedAnswerSchema, note: z.string().max(4000) }).strict();
export const revisionRecordSchema = revisionRequestSchema.extend({
  id: z.string(), createdAt: z.string(), reviewStatus: z.enum(['pending', 'accepted', 'rejected', 'paused']),
  contentDigest: z.string().length(64).nullable().optional(),
}).strict();
export const runReportSchema = z.object({
  snapshotDigest: z.string().length(64).nullable().optional(),
  schemaVersion: z.literal(1), session: sessionRecordSchema, run: runRecordSchema, selection: selectionSnapshotSchema,
  requests: z.array(attemptRecordSchema), context: ragContextCompressionSchema.nullable(), modelOutput: ragGroundedAnswerSchema.nullable(),
  reviews: z.array(reviewRecordSchema), revisions: z.array(revisionRecordSchema), consumedTokens: z.number().int().nonnegative(),
  runTokenLimit: z.number().int().positive(), structuralValidation: outcomeSchema, semanticReview: outcomeSchema, limitations: z.array(z.string()),
}).strict();
const recoveryBase = { runId: z.string(), contextFingerprint: z.string().length(64) };
export const recoveryPreviewSchema = z.union([
  z.object({ ...recoveryBase, kind: z.literal('harness'), stage: z.literal('context'), preview: harnessPreviewSchema }).strict(),
  z.object({ ...recoveryBase, kind: z.literal('rag'), stage: z.literal('context'), preview: ragPreviewSchema }).strict(),
  z.object({ ...recoveryBase, kind: z.literal('harness'), stage: z.literal('inference'), preview: inferencePreviewSchema }).strict(),
  z.object({ ...recoveryBase, kind: z.literal('rag'), stage: z.literal('inference'), preview: inferencePreviewSchema }).strict(),
]).superRefine((value, context) => {
  if (value.preview.preparedCall.purpose !== value.stage) context.addIssue({code: 'custom', path: ['preview', 'preparedCall', 'purpose'], message: 'Recovery stage and prepared purpose must match.'});
  if (value.stage === 'context') {
    if (value.contextFingerprint !== value.preview.contextFingerprint) context.addIssue({code: 'custom', path: ['contextFingerprint'], message: 'Context fingerprints must match.'});
    if (value.preview.runId && value.preview.runId !== value.runId) context.addIssue({code: 'custom', path: ['runId'], message: 'Recovery run identifiers must match.'});
  }
});
export type SessionRecord = z.infer<typeof sessionRecordSchema>;
export type RunRecord = z.infer<typeof runRecordSchema>;
export type RunReport = z.infer<typeof runReportSchema>;
export type ReviewRequest = z.infer<typeof reviewRequestSchema>;
export type RevisionRequest = z.infer<typeof revisionRequestSchema>;
export type RecoveryPreview = z.infer<typeof recoveryPreviewSchema>;
