import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { AgentView } from '../../../shared/contracts/agents';
import { ReviewWorkflow } from './ReviewWorkflow';

const saved: AgentView = { session: { sessionId: 'a'.repeat(32), resource: 'frag:/session', version: 1,
  turns: [{ id: 'task', text: 'Explain the synthetic finding', state: 'running', createdAt: 'now', runId: null }] }, report: null, preview: null };

describe('Review task status and recovery', () => {
  it('explains waiting without dispatching a model request', () => {
    const change = vi.fn();
    const html = renderToStaticMarkup(<ReviewWorkflow view={saved} onChange={change} />);
    expect(html).toContain('Waiting for evidence selection');
    expect(html).toContain('The native reply is complete');
    expect(html).toContain('no model calls occur while waiting');
    expect(html).toContain('Cancel task');
    expect(change).not.toHaveBeenCalled();
  });
  it('makes cancellation and restart visible and hides obsolete controls', () => {
    const cancelled: AgentView = { ...saved, session: { ...saved.session, turns: [{ ...saved.session.turns[0], state: 'cancelled' }] },
      preview: {} as AgentView['preview'] };
    const html = renderToStaticMarkup(<ReviewWorkflow view={cancelled} onChange={vi.fn()} />);
    expect(html).toContain('Task cancelled');
    expect(html).toContain('Previous approvals are invalid');
    expect(html).toContain('this page switches to the new task automatically');
    expect(html).toContain('Remove any native Context attachments');
    expect(html).not.toContain('Choose evidence');
    expect(html).not.toContain('Preview Context');
    expect(html).not.toContain('Evidence source');
    expect(html).not.toContain('I reviewed this exact request');
  });
});
