import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { harnessRequestSchema } from '../../shared/contracts/harness';
import { ragQueryRequestSchema } from '../../shared/contracts/rag';
import { selectedMemorySchema, type MemoryRecord } from '../../shared/contracts/memory';
import { MemoryPicker } from '../features/memory/MemoryPicker';
import { MemoryPanel } from '../features/memory/MemoryPanel';
import {
  createMemoryCandidate, fetchMemories, fetchMemoryVersions, markMemoryConflict, promoteMemory,
  recommendMemories, resolveMemoryConflict, retireMemory, reviseMemory,
} from './memoryClient';

afterEach(() => vi.unstubAllGlobals());
const record: MemoryRecord = {
  id: 'memory-1', version: 1, status: 'candidate', text: 'Preserve explicit unknown information.',
  scope: [{ kind: 'fc_record', namespace: 'finance-core', resourceId: 'record-1', workspaceId: 'workspace-A' }],
  general: false, conflicts: [], provenanceRunId: 'run-1', provenanceRevisionId: null, createdAt: 'now', reviewNote: null,
};
const active = { ...record, version: 2, status: 'active' as const, reviewNote: 'Reviewed text and scope.' };
const selectedMemory = [{ memoryId: record.id, version: active.version }];

describe('reviewed memory boundaries', () => {
  it('keeps scoped provenance and version history intact', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(Response.json([active])).mockResolvedValueOnce(Response.json([record, active]));
    vi.stubGlobal('fetch', fetchMock);
    await expect(fetchMemories()).resolves.toEqual([active]);
    await expect(fetchMemoryVersions(record.id)).resolves.toEqual([record, active]);
    expect(fetchMock.mock.calls[1][0]).toBe('/api/memory/memory-1/versions');
  });
  it('requires explicit human review for promotion and preserves source scope by default', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(Response.json(record)).mockResolvedValueOnce(Response.json(active));
    vi.stubGlobal('fetch', fetchMock);
    await createMemoryCandidate({ runId: 'run-1' });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ runId: 'run-1', general: false });
    await expect(promoteMemory(record.id, { version: 1, reviewed: false as true, note: 'Reviewed' })).rejects.toThrow();
    await expect(promoteMemory(record.id, { version: 1, reviewed: true, note: ' ' })).rejects.toThrow();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await promoteMemory(record.id, { version: 1, reviewed: true, note: 'Reviewed text and scope.' });
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ version: 1, reviewed: true, note: 'Reviewed text and scope.' });
  });
  it('versions edits and retirement, and pins both reviewed conflict records', async () => {
    const second = { ...active, id: 'memory-2' };
    const fetchMock = vi.fn().mockResolvedValueOnce(Response.json({ ...record, version: 3 }))
      .mockResolvedValueOnce(Response.json({ ...active, version: 4, status: 'retired' }))
      .mockResolvedValueOnce(Response.json([active, second])).mockResolvedValueOnce(Response.json([active, second]));
    vi.stubGlobal('fetch', fetchMock);
    await reviseMemory(record.id, { version: 2, text: record.text, general: false });
    await retireMemory(record.id, 3);
    await expect(markMemoryConflict([record.id, record.id])).rejects.toThrow();
    await markMemoryConflict([record.id, second.id]);
    const versions = [selectedMemory[0], { memoryId: second.id, version: second.version }];
    await resolveMemoryConflict(versions, 'Both versions reviewed.');
    expect(JSON.parse(fetchMock.mock.calls[3][1].body)).toEqual({ memoryIds: [record.id, second.id], versions, reviewed: true, note: 'Both versions reviewed.' });
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ version: 3 });
  });
  it('rejects unusable, duplicate or excessive recommendations from the API', async () => {
    const invalid = [[record], [{ ...active, status: 'retired' }], [{ ...active, conflicts: ['memory-2'] }], [active, active],
      Array.from({ length: 4 }, (_, index) => ({ ...active, id: `memory-${index}` }))];
    const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
    for (const items of invalid) {
      fetchMock.mockResolvedValueOnce(Response.json(items));
      await expect(recommendMemories('run-1', 'unknown information')).rejects.toThrow();
    }
    fetchMock.mockResolvedValueOnce(Response.json([active]));
    await expect(recommendMemories('run-1', 'unknown information')).resolves.toEqual([active]);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ runId: 'run-1', query: 'unknown information' });
  });
  it('bounds and preserves explicit selection on both fixed request kinds', () => {
    const harness = harnessRequestSchema.parse({ goal: 'Review unknown information', fileSelections: [
      { relativePath: 'synthetic.md', locatorIds: ['section-1'], relevanceReason: 'Human selected' },
    ], selectedMemory });
    const rag = ragQueryRequestSchema.parse({ datasetId: 'synthetic-risk-review-v1', query: 'Unknown information', selectedMemory });
    expect(harness.selectedMemory).toEqual(selectedMemory); expect(rag.selectedMemory).toEqual(selectedMemory);
    expect(selectedMemorySchema.safeParse([...selectedMemory, ...selectedMemory]).success).toBe(false);
    expect(selectedMemorySchema.safeParse([{ memoryId: record.id, version: 0 }]).success).toBe(false);
    expect(selectedMemorySchema.safeParse(Array.from({ length: 4 }, (_, index) => ({ memoryId: `memory-${index}`, version: 1 }))).success).toBe(false);
  });
  it('makes no recommendation or promotion automatically and exposes human confirmation controls', () => {
    const fetchMock = vi.fn(); const change = vi.fn(); vi.stubGlobal('fetch', fetchMock);
    const initial = renderToStaticMarkup(<MemoryPicker query="Unknown information" selected={[]} onChange={change} />);
    expect(initial).toContain('Prepare the selected source first'); expect(initial).toContain('disabled="">Recommend reviewed memories');
    const confirmed = renderToStaticMarkup(<MemoryPicker runId="run-1" query="Unknown information" selected={selectedMemory} onChange={change} />);
    expect(confirmed).toContain('Confirmed for the next preview: 1 / 3'); expect(confirmed).toContain('Remove memory memory-1');
    const page = renderToStaticMarkup(<MemoryPanel />);
    expect(page).toContain('Explicitly mark as general experience'); expect(page).toContain('No saved memories yet.');
    expect(change).not.toHaveBeenCalled(); expect(fetchMock).not.toHaveBeenCalled();
  });
});
