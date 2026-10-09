import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { AgentView } from '../../../shared/contracts/agents';
import { ReviewWorkflow } from './ReviewWorkflow';
import { settingsFixture } from '../testSettingsFixture';
import { runReportSchema } from '../../../shared/contracts/runtime';

const saved: AgentView = { session: { sessionId: 'a'.repeat(32), resource: 'frag:/session', version: 1,
  turns: [{ id: 'task', text: 'Explain the synthetic finding', state: 'running', createdAt: 'now', runId: null }] }, report: null, preview: null };

describe('Review task status and recovery', () => {
  it('explains waiting without dispatching a model request', () => {
    const change = vi.fn();
    const html = renderToStaticMarkup(<ReviewWorkflow view={saved} onChange={change} settings={settingsFixture} onSettings={vi.fn()} openSettings={vi.fn()} visible />);
    expect(html).toContain('Choose task configuration');
    expect(html).toContain('The native reply is complete');
    expect(html).toContain('no model calls occur while waiting');
    expect(html).toContain('Cancel task');
    expect(html).toContain('No project evidence configured.');
    expect(html).toMatch(/disabled=""[^>]*>Preview Context/);
    expect(change).not.toHaveBeenCalled();
  });
  it('makes cancellation and restart visible and hides obsolete controls', () => {
    const cancelled: AgentView = { ...saved, session: { ...saved.session, turns: [{ ...saved.session.turns[0], state: 'cancelled' }] },
      preview: {} as AgentView['preview'] };
    const html = renderToStaticMarkup(<ReviewWorkflow view={cancelled} onChange={vi.fn()} settings={settingsFixture} onSettings={vi.fn()} openSettings={vi.fn()} visible />);
    expect(html).toContain('Task cancelled');
    expect(html).toContain('Previous approvals are invalid');
    expect(html).toContain('this page switches to the new task automatically');
    expect(html).toContain('Remove any native Context attachments');
    expect(html).not.toContain('Choose evidence');
    expect(html).not.toContain('Preview Context');
    expect(html).not.toContain('Evidence source');
    expect(html).not.toContain('I reviewed this exact request');
  });
  it('keeps a legacy run read only even if its old carrier contains a preview', () => {
    const report = runReportSchema.parse({ schemaVersion: 1,
      session: { id: saved.session.sessionId, title: 'Legacy synthetic run', createdAt: 'now' },
      run: { id: 'legacy-run', sessionId: saved.session.sessionId, parentRunId: null, kind: 'harness',
        status: 'ready_context', createdAt: 'now', updatedAt: 'now', version: 1, activeCallId: null },
      selection: { goal: saved.session.turns[0].text, sourceBindings: [], candidateEvidence: [],
        task: { templateId: 'evidence-review-v1', checklist: [] }, input: {} },
      requests: [], context: null, modelOutput: null, reviews: [], revisions: [], consumedTokens: 0,
      runTokenLimit: 30000, structuralValidation: 'NOT_RUN', semanticReview: 'NOT_RUN', limitations: [],
    });
    const html = renderToStaticMarkup(<ReviewWorkflow view={{ ...saved, report, preview: {} as AgentView['preview'] }}
      onChange={vi.fn()} settings={settingsFixture} onSettings={vi.fn()} openSettings={vi.fn()} visible />);
    expect(html).toContain('Legacy saved run');
    expect(html).toContain('old request bindings are not rewritten');
    expect(html).not.toContain('I reviewed this exact request');
    expect(html).not.toContain('Preview next stage');
  });
  it('names blocking checklist items and explains model setup before preparation', () => {
    const settings = { ...settingsFixture, application: { ...settingsFixture.application,
      settings: { ...settingsFixture.application.settings, checklist: [{ id: 'scope', text: 'Review selected scope', blocking: true }] } } };
    const html = renderToStaticMarkup(<ReviewWorkflow view={saved} onChange={vi.fn()} settings={settings}
      onSettings={vi.fn()} openSettings={vi.fn()} visible />);
    expect(html).toContain('Review selected scope');
    expect(html).toContain('Set each item to Met and confirm Reviewed by me');
    expect(html).toContain('Selected native model is not ready. Open Settings');
    expect(html).not.toContain('Check model readiness and blocking checklist items before approval.');
  });
});
