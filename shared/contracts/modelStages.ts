import { z } from 'zod';

export const stageConfigSchema = z.object({
  provider: z.enum(['fake', 'openai', 'ollama']), model: z.string().nullable(), ready: z.boolean(),
}).strict();
export const tokenBudgetSchema = z.object({
  estimatedInputTokens: z.number().int().nonnegative(), inputBudget: z.number().int().positive(),
  reservedPercent: z.number().int().min(0).max(100), contextOutputLimit: z.number().int().positive(),
  inferenceOutputLimit: z.number().int().positive(), approximate: z.literal(true),
}).strict();
export const stageResultSchema = z.object({
  provider: z.enum(['fake', 'openai', 'ollama']), model: z.string(),
  usage: z.object({ inputTokens: z.number().int().nonnegative().nullable(),
                    outputTokens: z.number().int().nonnegative().nullable() }).strict(),
}).strict();
