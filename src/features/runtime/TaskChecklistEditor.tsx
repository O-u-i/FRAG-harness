import type { TaskContract } from '../../../shared/contracts/governance';
import './runtime.css';

export const emptyReviewTask: TaskContract = { templateId: 'evidence-review-v1', checklist: [] };

type Props = { task: TaskContract; onChange: (task: TaskContract) => void; disabled?: boolean; reviewOnly?: boolean };

export function TaskChecklistEditor({ task, onChange, disabled = false, reviewOnly = false }: Props) {
  const update = (index: number, changes: Partial<TaskContract['checklist'][number]>) => {
    onChange({ ...task, checklist: task.checklist.map((item, position) => position === index ? { ...item, ...changes } : item) });
  };
  const addItem = () => {
    let number = 1;
    while (task.checklist.some((item) => item.id === `item-${number}`)) number += 1;
    onChange({ ...task, checklist: [...task.checklist, {
      id: `item-${number}`, text: 'Review selected evidence.', blocking: false, status: 'pending', reviewed: false,
    }] });
  };
  return <fieldset className="task-checklist" disabled={disabled}>
    <legend>Human checklist</legend>
    <p className="muted">Blocking items must be met and reviewed before approval. Ordinary gaps remain explicit.</p>
    {task.checklist.map((item, index) => <article className="checklist-item" key={item.id}>
      <label className="field">Item {index + 1}
        <textarea value={item.text} readOnly={reviewOnly} maxLength={500} onChange={(event) => update(index, { text: event.target.value, reviewed: false })} />
      </label>
      <div className="checklist-controls">
        <label><input type="checkbox" checked={item.blocking} disabled={reviewOnly} onChange={(event) => update(index, { blocking: event.target.checked })} /> Blocking</label>
        <label>Status <select value={item.status} onChange={(event) => update(index, { status: event.target.value as typeof item.status, reviewed: false })}>
          <option value="pending">Pending</option><option value="met">Met</option>
          <option value="missing">Missing</option><option value="unknown">Unknown</option>
        </select></label>
        <label><input type="checkbox" checked={item.reviewed} onChange={(event) => update(index, { reviewed: event.target.checked })} /> Reviewed by me</label>
        {!reviewOnly && <button className="button" type="button" aria-label={`Remove checklist item ${index + 1}`}
          onClick={() => onChange({ ...task, checklist: task.checklist.filter((_, position) => position !== index) })}>Remove</button>}
      </div>
    </article>)}
    {!reviewOnly && <button className="button" type="button" disabled={disabled || task.checklist.length >= 20} onClick={addItem}>Add checklist item</button>}
  </fieldset>;
}
