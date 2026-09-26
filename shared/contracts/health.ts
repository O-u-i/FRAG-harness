import { z } from 'zod';

export const contextHealthSchema = z.object({
  status: z.literal('ok'),
  service: z.literal('frag-harness'),
  serviceVersion: z.string(),
}).strict();

export type ContextHealth = z.infer<typeof contextHealthSchema>;
