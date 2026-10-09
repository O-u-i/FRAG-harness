import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { AgentView } from '../../shared/contracts/agents';
import { Runs } from './AgentReviewApp';
import { LineSidebar } from './components/Navigation';

const view: AgentView = { session: { sessionId: 'a'.repeat(32), resource: 'frag:/session', version: 1,
  turns: [{ id: 'task', text: 'Explain the synthetic finding', state: 'running', createdAt: 'now', runId: null }] }, report: null, preview: null };

describe('Review task history and fixed navigation', () => {
  it('shows the waiting task without inventing a Run or calling the backend', () => {
    const html = renderToStaticMarkup(<Runs view={view} openWorkspace={vi.fn()} />);
    expect(html).toContain(view.session.turns[0].text);
    expect(html).toContain('Waiting for task configuration. No Run has been created.');
    expect(html).toContain('Configure in Workspace');
    expect(html).toContain('No saved Runs in this native session.');
    expect(html).toMatch(/<select[^>]*disabled=""/);
  });
  it('does not label a cancelled task as waiting', () => {
    const cancelled = { ...view, session: { ...view.session, turns: [{ ...view.session.turns[0], state: 'cancelled' as const }] } };
    const html = renderToStaticMarkup(<Runs view={cancelled} openWorkspace={vi.fn()} />);
    expect(html).toContain('Task cancelled before a Run was created.');
    expect(html).not.toContain('Waiting for task configuration');
  });
  it('uses one text navigation without a duplicate rail or flyout', () => {
    const html = renderToStaticMarkup(<LineSidebar active="runs" onSelect={vi.fn()} memory="candidates" onMemory={vi.fn()} />);
    for (const label of ['Workspace', 'Runs', 'Settings', 'Memory']) expect(html).toContain(label);
    expect(html).not.toContain('review-rail-nav');
    expect(html).not.toContain('review-memory-flyout');
    expect(html).not.toContain('icon-btn');
  });
});
