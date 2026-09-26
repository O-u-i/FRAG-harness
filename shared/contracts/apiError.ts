import { z } from 'zod';

export const apiErrorIssueSchema = z.object({
  path: z.string(),
  message: z.string(),
}).strict();

export const apiErrorResponseSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    issues: z.array(apiErrorIssueSchema),
  }).strict(),
}).strict();

export type ApiErrorIssue = z.infer<typeof apiErrorIssueSchema>;
export type ApiErrorResponse = z.infer<typeof apiErrorResponseSchema>;
