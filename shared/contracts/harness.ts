import { z } from 'zod';
import { inferencePreviewSchema, ragContextCompressionSchema, ragEvidenceSchema, ragGroundedAnswerSchema } from './rag';
import { stageConfigSchema, stageResultSchema, tokenBudgetSchema } from './modelStages';
import { preparedCallSchema, sourceBindingSchema, taskContractSchema } from './governance';
import { selectedMemorySchema } from './memory';

export const harnessConfigSchema = z.object({
  context: stageConfigSchema, inference: stageConfigSchema,
}).strict();
export const fileSelectionSchema = z.object({
  relativePath: z.string().min(1).max(500), locatorIds: z.array(z.string()).min(1).max(20),
  relevanceReason: z.string().min(3).max(500),
}).strict();
export const harnessRequestSchema = z.object({
  goal: z.string().min(3).max(500), fileSelections: z.array(fileSelectionSchema).max(3),
  pluginSelection: z.object({pluginId: z.string().max(63).regex(/^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/),
    workspaceId: z.string().min(1).max(128).nullable().optional(), scopeId: z.string().min(1).max(500).nullable().optional(),
    recordIds: z.array(z.string().min(1).max(128)).min(1).max(10).refine((ids) => new Set(ids).size === ids.length)}).strict()
      .refine((value) => Boolean(value.scopeId) !== Boolean(value.workspaceId) && (!value.workspaceId || value.pluginId === 'finance-core'))
      .nullable().optional(),
  task: taskContractSchema.optional(),
  selectedMemory: selectedMemorySchema.optional(),
  sessionId: z.string().max(64).nullable().optional(), parentRunId: z.string().max(64).nullable().optional(),
}).strict().refine((value) => Boolean(value.fileSelections.length) !== Boolean(value.pluginSelection), 'Select one evidence source.');
export const harnessRunRequestSchema = harnessRequestSchema.extend({
  contextFingerprint: z.string().length(64), approvalToken: z.string().min(32), approved: z.literal(true),
}).strict();
export const harnessPreviewSchema = z.object({
  goal: z.string(), candidateEvidence: z.array(ragEvidenceSchema), budget: tokenBudgetSchema,
  instructions: z.string(), input: z.string(),
  warnings: z.array(z.string()), contextFingerprint: z.string().length(64), approvalToken: z.string(),
  preparedCall: preparedCallSchema, sourceBindings: z.array(sourceBindingSchema), task: taskContractSchema,
  canApprove: z.boolean(),
  runId: z.string().nullable().optional(), sessionId: z.string().nullable().optional(),
}).strict();
export const harnessRunSchema = z.object({
  preview: harnessPreviewSchema, compressedContext: ragContextCompressionSchema,
  result: ragGroundedAnswerSchema, contextStage: stageResultSchema, inferenceStage: stageResultSchema,
}).strict();
export const harnessContextRunSchema = z.object({
  preview: harnessPreviewSchema, compressedContext: ragContextCompressionSchema,
  contextStage: stageResultSchema, inferencePreview: inferencePreviewSchema,
}).strict();

export type HarnessConfig = z.infer<typeof harnessConfigSchema>;
export type HarnessRequest = z.infer<typeof harnessRequestSchema>;
export type HarnessPreview = z.infer<typeof harnessPreviewSchema>;
export type HarnessRunRequest = z.infer<typeof harnessRunRequestSchema>;
export type HarnessRun = z.infer<typeof harnessRunSchema>;
export type HarnessContextRun = z.infer<typeof harnessContextRunSchema>;
