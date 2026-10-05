import { z } from 'zod';
import { sourceIdentitySchema } from './governance';

export const memorySelectionSchema = z.object({
  memoryId: z.string().min(1).max(64), version: z.number().int().positive(),
}).strict();
export const selectedMemorySchema = z.array(memorySelectionSchema).max(3)
  .refine((items) => new Set(items.map((item) => item.memoryId)).size === items.length, 'Select each memory once.');
export const memoryRecordSchema = z.object({
  id: z.string().min(1), version: z.number().int().positive(), status: z.enum(['candidate', 'active', 'retired']),
  text: z.string().min(1).max(4000), scope: z.array(sourceIdentitySchema), general: z.boolean(),
  conflicts: z.array(z.string()), provenanceRunId: z.string().min(1), provenanceRevisionId: z.string().nullable(),
  createdAt: z.string(), reviewNote: z.string().nullable(),
}).strict();
export const memoryCandidateSchema = z.object({
  runId: z.string().min(1).max(64), revisionId: z.string().min(1).max(64).nullable().optional(),
  text: z.string().trim().min(1).max(4000).optional(), general: z.boolean().default(false),
}).strict();
export const memoryRevisionSchema = z.object({
  version: z.number().int().positive(), text: z.string().trim().min(1).max(4000), general: z.boolean().optional(),
}).strict();
export const memoryPromotionSchema = z.object({
  version: z.number().int().positive(), reviewed: z.literal(true), note: z.string().trim().min(1).max(4000),
}).strict();
export const memoryRetirementSchema = z.object({ version: z.number().int().positive() }).strict();
export const memoryConflictSchema = z.object({
  memoryIds: z.array(z.string().min(1).max(64)).length(2).refine((ids) => ids[0] !== ids[1], 'Choose two different memories.'),
}).strict();
export const memoryResolutionSchema = memoryConflictSchema.extend({
  versions: z.array(memorySelectionSchema).length(2),
  reviewed: z.literal(true), note: z.string().trim().min(1).max(4000),
}).strict().refine((value) => value.versions.every((item) => value.memoryIds.includes(item.memoryId))
  && new Set(value.versions.map((item) => item.memoryId)).size === 2, 'Reviewed versions must match both conflict records.');
export const memoryRecommendationSchema = z.object({
  query: z.string().trim().min(1).max(500), runId: z.string().min(1).max(64),
}).strict();
export type MemorySelection = z.infer<typeof memorySelectionSchema>;
export type MemoryRecord = z.infer<typeof memoryRecordSchema>;
