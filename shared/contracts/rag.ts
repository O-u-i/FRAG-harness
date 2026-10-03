import { z } from 'zod';
import { stageResultSchema, tokenBudgetSchema } from './modelStages';
import { preparedCallSchema, sourceBindingSchema, taskContractSchema } from './governance';

export const ragDatasetIdSchema = z.literal('synthetic-risk-review-v1');
export const ragDatasetRequestSchema = z.object({ datasetId: ragDatasetIdSchema }).strict();
export const ragQueryRequestSchema = ragDatasetRequestSchema.extend({
  query: z.string().min(3).max(500),
  topK: z.number().int().min(1).max(10).default(3),
  task: taskContractSchema.optional(),
}).strict();
export const ragRunRequestSchema = ragQueryRequestSchema.extend({
  contextFingerprint: z.string().length(64),
  approvalToken: z.string().min(32),
  approved: z.literal(true),
}).strict();
export const inferenceRunRequestSchema = z.object({
  contextFingerprint: z.string().length(64), inferenceFingerprint: z.string().length(64),
  approvalToken: z.string().min(32), approved: z.literal(true),
}).strict();
export const inferencePreviewSchema = z.object({
  provider: z.string(), model: z.string(), instructions: z.string(), input: z.string(),
  maxOutputTokens: z.number().int().positive(), inferenceFingerprint: z.string().length(64),
  approvalToken: z.string().min(32),
  preparedCall: preparedCallSchema,
}).strict();

export const ragIndexStatusSchema = z.object({
  datasetId: ragDatasetIdSchema,
  schemaVersion: z.literal(2),
  chunkStrategyVersion: z.literal('markdown-hierarchy-v2'),
  state: z.enum(['not_built', 'ready', 'stale']),
  documentCount: z.number().int().nonnegative(),
  chunkCount: z.number().int().nonnegative(),
  indexRevision: z.string().length(64).nullable(),
  sourceHash: z.string().length(64).nullable(),
}).strict();

export const ragChunkResultSchema = z.object({
  rank: z.number().int().positive(),
  bm25Score: z.number(),
  chunkId: z.string().min(1),
  parentId: z.string().min(1),
  evidenceId: z.string().min(1).nullable(),
  documentId: z.string().min(1),
  sourceId: z.string().min(1),
  locatorId: z.string().min(1),
  locatorLabel: z.string().min(1),
  excerpt: z.string(),
}).strict();

export const ragSearchResponseSchema = z.object({
  datasetId: ragDatasetIdSchema,
  query: z.string(),
  topK: z.number().int().min(1).max(10),
  indexRevision: z.string().length(64),
  results: z.array(ragChunkResultSchema),
}).strict();

export const ragEvidenceSchema = z.object({
  evidenceId: z.string().min(1), documentId: z.string().min(1), sourceId: z.string().min(1),
  locatorId: z.string().min(1), locatorLabel: z.string().min(1), text: z.string().min(1),
}).strict();

export const ragPreviewSchema = z.object({
  datasetId: ragDatasetIdSchema,
  query: z.string(),
  topK: z.number().int().min(1).max(10),
  indexRevision: z.string().length(64),
  retrievalResults: z.array(ragChunkResultSchema),
  candidateEvidence: z.array(ragEvidenceSchema),
  instructions: z.string(), input: z.string(),
  budget: tokenBudgetSchema,
  warnings: z.array(z.string()),
  contextFingerprint: z.string().length(64),
  approvalToken: z.string(),
  preparedCall: preparedCallSchema, sourceBindings: z.array(sourceBindingSchema), task: taskContractSchema,
  canApprove: z.boolean(),
}).strict();

export const ragCompressedEvidenceSchema = z.object({
  evidenceId: z.string().min(1), summary: z.string().min(1),
  preservedFacts: z.array(z.string()), uncertainty: z.array(z.string()),
}).strict();
export const ragContextCompressionSchema = z.object({
  evidence: z.array(ragCompressedEvidenceSchema), missingInformation: z.array(z.string()),
}).strict();
export const ragClaimSchema = z.object({
  text: z.string().min(1), evidenceIds: z.array(z.string().min(1)).min(1),
}).strict();
export const ragGroundedAnswerSchema = z.object({
  answer: z.string().min(1), claims: z.array(ragClaimSchema).min(1),
  missingInformation: z.array(z.string()), disclaimer: z.string().min(1),
}).strict();
export const ragRunSchema = z.object({
  preview: ragPreviewSchema,
  compressedContext: ragContextCompressionSchema,
  result: ragGroundedAnswerSchema,
  contextStage: stageResultSchema,
  inferenceStage: stageResultSchema,
}).strict();
export const ragContextRunSchema = z.object({
  preview: ragPreviewSchema, compressedContext: ragContextCompressionSchema,
  contextStage: stageResultSchema, inferencePreview: inferencePreviewSchema,
}).strict();

export const ragEvaluationCaseSchema = z.object({
  id: z.string(), query: z.string(), expectedChunkId: z.string(), actualChunkIds: z.array(z.string()),
  expectedRank: z.number().int().positive().nullable(), passed: z.boolean(),
}).strict();
export const ragRetrievalMetricsSchema = z.object({
  hitAt1: z.number().min(0).max(1), recallAt3: z.number().min(0).max(1),
  mrrAt3: z.number().min(0).max(1), ndcgAt3: z.number().min(0).max(1),
}).strict();
export const ragEvaluationGatesSchema = z.object({
  contextCoverage: z.number().min(0).max(1), citationValidity: z.number().min(0).max(1),
  expectedCitationCoverage: z.number().min(0).max(1), staleResidualCount: z.number().int().nonnegative(),
}).strict();
export const ragEvaluationReportSchema = z.object({
  suiteVersion: z.string(), datasetId: ragDatasetIdSchema, cases: z.array(ragEvaluationCaseSchema),
  metrics: ragRetrievalMetricsSchema, gates: ragEvaluationGatesSchema,
  status: z.enum(['PASS', 'FAIL']),
}).strict();

export type RagDatasetRequest = z.infer<typeof ragDatasetRequestSchema>;
export type RagQueryRequest = z.infer<typeof ragQueryRequestSchema>;
export type RagRunRequest = z.infer<typeof ragRunRequestSchema>;
export type InferenceRunRequest = z.infer<typeof inferenceRunRequestSchema>;
export type InferencePreview = z.infer<typeof inferencePreviewSchema>;
export type RagIndexStatus = z.infer<typeof ragIndexStatusSchema>;
export type RagSearchResponse = z.infer<typeof ragSearchResponseSchema>;
export type RagPreview = z.infer<typeof ragPreviewSchema>;
export type RagRun = z.infer<typeof ragRunSchema>;
export type RagContextRun = z.infer<typeof ragContextRunSchema>;
export type RagEvaluationReport = z.infer<typeof ragEvaluationReportSchema>;
