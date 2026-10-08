import { z } from 'zod';
import { harnessRequestSchema } from './harness';
const mode = z.enum(['files', 'retrieval', 'plugin']);
export const checklistTemplateSchema = z.object({ id: z.string().min(1).max(80), text: z.string().min(1).max(500), blocking: z.boolean() }).strict();
export const applicationSettingsSchema = z.object({ mode, topK: z.union([z.literal(1), z.literal(3), z.literal(5), z.literal(10)]),
  researchInCustom: z.boolean(), checklist: checklistTemplateSchema.array().max(20) }).strict()
  .refine((value) => new Set(value.checklist.map((item) => item.id)).size === value.checklist.length, 'Checklist identifiers must be distinct.');
export const evidenceSettingsSchema = z.object({ mode, file: harnessRequestSchema.shape.fileSelections.element.nullable(),
  plugin: harnessRequestSchema.shape.pluginSelection.unwrap().nullable(), synthetic: z.boolean() }).strict().superRefine((value, context) => {
    if ((value.mode !== 'plugin' && value.plugin) || (value.mode === 'plugin' && value.file) ||
        (value.synthetic && (value.mode !== 'retrieval' || value.file))) context.addIssue({code:'custom',message:'Select only the chosen evidence mode.'});
    if (value.file && (/^(?:[a-z]:|[/\\])|(?:^|[/\\])\.\.(?:[/\\]|$)/i.test(value.file.relativePath) ||
        new Set(value.file.locatorIds).size !== value.file.locatorIds.length)) context.addIssue({code:'custom',message:'Select relative project sources with distinct locators.'});
  });
export const conversationSettingsSchema = z.object({ evidence: evidenceSettingsSchema, topK: applicationSettingsSchema.shape.topK,
  research: z.boolean(), checklist: checklistTemplateSchema.array().max(20) }).strict()
  .refine((value) => !(value.research && value.evidence.mode === 'plugin') && new Set(value.checklist.map((item) => item.id)).size === value.checklist.length,
    'Plugin Research is unavailable; checklist identifiers must be distinct.');
const revision = z.number().int().nonnegative();
export const settingsViewSchema = z.object({
  application: z.object({ revision, settings: applicationSettingsSchema }).strict(),
  project: z.object({ revision, settings: evidenceSettingsSchema }).strict(),
  conversation: z.object({ revision, settings: conversationSettingsSchema.nullable() }).strict(),
}).strict();
export type SettingsView = z.infer<typeof settingsViewSchema>;
export type EvidenceSettings = z.infer<typeof evidenceSettingsSchema>;
export type ApplicationSettings = z.infer<typeof applicationSettingsSchema>;
export type ConversationSettings = z.infer<typeof conversationSettingsSchema>;
