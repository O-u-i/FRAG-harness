import { useEffect, useState } from 'react';
import type { SessionRecord } from '../../../shared/contracts/runtime';
import { fetchSessions } from '../../api/runtimeClient';

export function SessionPicker({ value, disabled, onChange }: { value: string; disabled: boolean; onChange: (value: string) => void }) {
  const [sessions, setSessions] = useState<SessionRecord[]>([]);
  const [unavailable, setUnavailable] = useState(false);
  useEffect(() => {
    let active = true;
    fetchSessions().then((items) => { if (active) setSessions(items); }).catch(() => { if (active) setUnavailable(true); });
    return () => { active = false; };
  }, []);
  return <>
    <label className="field">Save under session<select value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
      <option value="">Create a new session for this run</option>
      {value && !sessions.some((session) => session.id === value) && <option value={value}>Current run session</option>}
      {sessions.map((session) => <option key={session.id} value={session.id}>{session.title}</option>)}
    </select></label>
    {unavailable && <p className="muted">Session history is unavailable. A new session will be created when the request is prepared.</p>}
  </>;
}
