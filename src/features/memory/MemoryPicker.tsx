import { useEffect, useRef, useState } from 'react';
import type { MemoryRecord, MemorySelection } from '../../../shared/contracts/memory';
import { recommendMemories } from '../../api/memoryClient';

type Props = { runId?: string; query: string; selected: MemorySelection[]; disabled?: boolean; onChange: (items: MemorySelection[]) => void };

export function MemoryPicker({ runId, query, selected, disabled = false, onChange }: Props) {
  const [suggestions, setSuggestions] = useState<MemoryRecord[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const epoch = useRef(0);
  useEffect(() => {
    epoch.current += 1; setSuggestions([]); setMessage(''); setBusy(false);
    return () => { epoch.current += 1; };
  }, [runId, query]);
  const recommend = async () => {
    if (!runId || disabled || busy) return;
    const current = ++epoch.current;
    setBusy(true); setMessage(''); setSuggestions([]);
    try {
      const items = await recommendMemories(runId, query);
      if (epoch.current === current) { setSuggestions(items); if (!items.length) setMessage('No applicable reviewed memories matched.'); }
    } catch (caught) {
      if (epoch.current === current) setMessage(caught instanceof Error ? caught.message : 'Memory recommendations could not be loaded.');
    } finally { if (epoch.current === current) setBusy(false); }
  };
  return <fieldset className="memory-picker"><legend>Optional reviewed memory</legend>
    <p className="muted">Memory is background, not evidence or permission. Confirm at most three records, then prepare a new exact preview.</p>
    {!runId && <p className="muted">Prepare the selected source first to enable scope-filtered recommendations.</p>}
    <button type="button" className="button" disabled={disabled || busy || !runId || !query.trim()} onClick={() => void recommend()}>
      {busy ? 'Finding memories…' : 'Recommend reviewed memories'}</button>
    {message && <p className="muted" role="status">{message}</p>}
    {suggestions.map((item) => {
      const checked = selected.some((value) => value.memoryId === item.id && value.version === item.version);
      return <label className="locator-option" key={`${item.id}-${item.version}`}>
        <input type="checkbox" checked={checked} disabled={disabled || (!checked && selected.length >= 3)}
          onChange={(event) => onChange(event.target.checked
            ? [...selected.filter((value) => value.memoryId !== item.id), { memoryId: item.id, version: item.version }]
            : selected.filter((value) => value.memoryId !== item.id))} />
        <span><strong>Confirm memory v{item.version} · {item.general ? 'General experience' : 'Selected source scope'}</strong><small>{item.text}</small></span>
      </label>;
    })}
    {selected.length > 0 && <div className="memory-confirmed"><p className="muted">Confirmed for the next preview: {selected.length} / 3</p>
      {selected.map((item) => <div key={item.memoryId}><code>{item.memoryId} · v{item.version}</code>
        <button type="button" className="button" disabled={disabled} aria-label={`Remove memory ${item.memoryId}`}
          onClick={() => onChange(selected.filter((value) => value.memoryId !== item.memoryId))}>Remove</button></div>)}
    </div>}
  </fieldset>;
}
