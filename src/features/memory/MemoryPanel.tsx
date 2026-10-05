import { useEffect, useRef, useState } from 'react';
import type { MemoryRecord } from '../../../shared/contracts/memory';
import {
  createMemoryCandidate, fetchMemories, fetchMemoryVersions, markMemoryConflict, promoteMemory,
  resolveMemoryConflict, retireMemory, reviseMemory,
} from '../../api/memoryClient';
import './memory.css';

export function MemoryPanel() {
  const [records, setRecords] = useState<MemoryRecord[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [versions, setVersions] = useState<MemoryRecord[]>([]);
  const [runId, setRunId] = useState('');
  const [revisionId, setRevisionId] = useState('');
  const [candidateText, setCandidateText] = useState('');
  const [generalCandidate, setGeneralCandidate] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const alive = useRef(true);
  const listEpoch = useRef(0);
  const historyEpoch = useRef(0);
  const selected = records.find((item) => item.id === selectedId);
  useEffect(() => {
    alive.current = true;
    const current = ++listEpoch.current;
    fetchMemories().then((value) => { if (alive.current && current === listEpoch.current) setRecords(value); })
      .catch((caught) => { if (alive.current && current === listEpoch.current) setMessage(caught instanceof Error ? caught.message : 'Memory history could not be loaded.'); });
    return () => { alive.current = false; listEpoch.current += 1; historyEpoch.current += 1; };
  }, []);
  useEffect(() => {
    const current = ++historyEpoch.current; setVersions([]);
    if (selectedId) fetchMemoryVersions(selectedId).then((value) => { if (current === historyEpoch.current) setVersions(value); })
      .catch((caught) => { if (current === historyEpoch.current) setMessage(caught instanceof Error ? caught.message : 'Memory versions could not be loaded.'); });
  }, [selectedId, selected?.version]);
  const action = async (operation: () => Promise<MemoryRecord | MemoryRecord[]>, success: string) => {
    setBusy(true); setMessage('');
    listEpoch.current += 1;
    try {
      const updated = await operation();
      const latest = await fetchMemories();
      if (alive.current) { setRecords(latest); if (!Array.isArray(updated)) setSelectedId(updated.id); setMessage(success); }
    } catch (caught) { if (alive.current) setMessage(caught instanceof Error ? caught.message : 'Memory operation failed.'); }
    finally { if (alive.current) setBusy(false); }
  };
  return <div className="memory-layout">
    <section className="card"><div className="section-heading"><span className="eyebrow">Human curated</span><h2>Candidate memories</h2>
      <p>Derive a candidate from a saved model output or human revision. It remains unusable until you edit, review and promote it.</p></div>
      <label className="field">Provenance Run ID<input value={runId} maxLength={64} disabled={busy} onChange={(event) => setRunId(event.target.value)} /></label>
      <label className="field">Human revision ID (optional)<input value={revisionId} maxLength={64} disabled={busy} onChange={(event) => setRevisionId(event.target.value)} /></label>
      <label className="field">Candidate text (optional; blank derives from output)<textarea value={candidateText} maxLength={4000} disabled={busy}
        onChange={(event) => setCandidateText(event.target.value)} /></label>
      <label className="memory-check"><input type="checkbox" checked={generalCandidate} disabled={busy} onChange={(event) => setGeneralCandidate(event.target.checked)} />
        Explicitly mark as general experience across sources and Workspaces</label>
      <button type="button" className="button primary" disabled={busy || !runId.trim()} onClick={() => void action(() => createMemoryCandidate({
        runId: runId.trim(), revisionId: revisionId.trim() || undefined, text: candidateText.trim() || undefined, general: generalCandidate,
      }), 'Candidate saved. Review its text and scope before promotion.')}>Create candidate</button>
      <div className="section-heading memory-heading"><h2>Latest records</h2><p>All versions remain in local history. A new version invalidates requests using an earlier version.</p></div>
      <button type="button" className="button" disabled={busy} onClick={() => void action(fetchMemories, 'Memory history refreshed.')}>Refresh memories</button>
      {!records.length && <p className="empty-state">No saved memories yet.</p>}
      <div className="runtime-run-list">{records.map((item) => <button key={item.id} type="button" disabled={busy}
        className={`runtime-run-option ${selectedId === item.id ? 'selected' : ''}`} onClick={() => {
          if (selectedId !== item.id) { historyEpoch.current += 1; setVersions([]); setSelectedId(item.id); }
          setMessage('');
        }}>
        <strong>{item.status} · v{item.version}{item.conflicts.length ? ' · known conflict' : ''}</strong><small>{item.text.slice(0, 120)}</small><code>{item.id}</code>
      </button>)}</div>
    </section>
    <div className="runtime-detail">
      {message && <p className="alert" role="status">{message}</p>}
      {busy && <p className="muted" role="status">Saving memory…</p>}
      {selected ? <MemoryEditor key={`${selected.id}-${selected.version}`} record={selected} records={records} versions={versions} busy={busy} action={action} />
        : <section className="card"><p className="empty-state">Choose a record to inspect scope, review, version, retire or resolve a known conflict.</p></section>}
    </div>
  </div>;
}

type EditorProps = { record: MemoryRecord; records: MemoryRecord[]; versions: MemoryRecord[]; busy: boolean;
  action: (operation: () => Promise<MemoryRecord | MemoryRecord[]>, success: string) => Promise<void> };
function MemoryEditor({ record, records, versions, busy, action }: EditorProps) {
  const [text, setText] = useState(record.text);
  const [general, setGeneral] = useState(record.general);
  const [reviewed, setReviewed] = useState(false);
  const [note, setNote] = useState('');
  const [otherId, setOtherId] = useState('');
  const [conflictReviewed, setConflictReviewed] = useState(false);
  const [conflictNote, setConflictNote] = useState('');
  const dirty = text.trim() !== record.text || general !== record.general;
  const knownConflict = record.conflicts.includes(otherId);
  const other = records.find((item) => item.id === otherId);
  return <section className="card memory-editor"><div className="section-heading"><span className="eyebrow">{record.status} / v{record.version}</span><h2>Review this memory</h2>
    <p>Memory cannot replace current evidence, widen source access or authorize an action.</p></div>
    <p className="muted">Record: <code>{record.id}</code> · Run: <code>{record.provenanceRunId}</code>{record.provenanceRevisionId && <> · Revision: <code>{record.provenanceRevisionId}</code></>}</p>
    <details><summary>Source scope and provenance</summary><pre className="runtime-data">{JSON.stringify(record.scope, null, 2)}</pre>
      <p className="muted">Created: {record.createdAt} · Review: {record.reviewNote ?? 'Not reviewed'}</p></details>
    <label className="field">Memory text<textarea value={text} maxLength={4000} disabled={busy} onChange={(event) => { setText(event.target.value); setReviewed(false); }} /></label>
    <label className="memory-check"><input type="checkbox" checked={general} disabled={busy} onChange={(event) => { setGeneral(event.target.checked); setReviewed(false); }} />
      General experience across sources and Workspaces (explicit opt-in)</label>
    <button type="button" className="button" disabled={busy || !text.trim() || !dirty} onClick={() => void action(() => reviseMemory(record.id,
      { version: record.version, text: text.trim(), general }), 'New candidate version saved; review it before promotion.')}>Save edited candidate version</button>
    <label className="field">Promotion review note<textarea value={note} maxLength={4000} disabled={busy} onChange={(event) => setNote(event.target.value)} /></label>
    <label className="memory-check"><input type="checkbox" checked={reviewed} disabled={busy || dirty} onChange={(event) => setReviewed(event.target.checked)} />
      I reviewed this saved text, provenance, scope and known conflicts</label>
    {dirty && <p className="muted">Save edits as a candidate version before reviewing and promoting.</p>}
    {record.conflicts.length > 0 && <p className="alert">Known conflicts: {record.conflicts.join(', ')}. Conflicting memories are not recommended or sent.</p>}
    <div className="rag-actions"><button type="button" className="button primary" disabled={busy || record.status !== 'candidate' || dirty || !reviewed || !note.trim() || !!record.conflicts.length}
      onClick={() => void action(() => promoteMemory(record.id, { version: record.version, reviewed: true, note: note.trim() }), 'Memory promoted. It still needs explicit confirmation in a source preview.')}>
      Promote reviewed memory</button>
      <button type="button" className="button" disabled={busy || record.status === 'retired'} onClick={() => void action(() => retireMemory(record.id, record.version), 'Memory retired; older approved previews are invalid.')}>Retire memory</button></div>
    <details><summary>Manage known conflicts</summary>
      <label className="field">Other memory<select value={otherId} disabled={busy} onChange={(event) => { setOtherId(event.target.value); setConflictReviewed(false); }}>
        <option value="">Choose a different record</option>{records.filter((item) => item.id !== record.id).map((item) => <option key={item.id} value={item.id}>{item.id} · {item.status} · v{item.version}</option>)}
      </select></label>
      {other && <article className="runtime-revision"><strong>Other record v{other.version} · {other.status}</strong><p>{other.text}</p>
        <pre className="runtime-data">{JSON.stringify({ scope: other.scope, general: other.general, provenanceRunId: other.provenanceRunId,
          provenanceRevisionId: other.provenanceRevisionId, conflicts: other.conflicts }, null, 2)}</pre></article>}
      <button type="button" className="button" disabled={busy || !otherId || knownConflict} onClick={() => void action(() => markMemoryConflict([record.id, otherId]), 'Known conflict recorded; both memories are excluded from requests.')}>Mark known conflict</button>
      <label className="field">Resolution review note<textarea value={conflictNote} maxLength={4000} disabled={busy} onChange={(event) => setConflictNote(event.target.value)} /></label>
      <label className="memory-check"><input type="checkbox" checked={conflictReviewed} disabled={busy || !knownConflict} onChange={(event) => setConflictReviewed(event.target.checked)} />
        I reviewed both records and their resolution</label>
      <button type="button" className="button" disabled={busy || !knownConflict || !conflictReviewed || !conflictNote.trim()}
        onClick={() => other && void action(() => resolveMemoryConflict([
          { memoryId: record.id, version: record.version }, { memoryId: other.id, version: other.version },
        ], conflictNote.trim()), 'Conflict resolution recorded as new versions.')}>Resolve reviewed conflict</button>
    </details>
    <details><summary>Version history ({versions.length})</summary>{versions.map((item) => <article className="runtime-revision" key={item.version}>
      <strong>v{item.version} · {item.status}{item.conflicts.length ? ' · known conflict' : ''}</strong><p>{item.text}</p><p className="muted">{item.reviewNote ?? 'Not reviewed'} · {item.createdAt}</p>
    </article>)}</details>
  </section>;
}
