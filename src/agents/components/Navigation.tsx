// Adapted from the user-supplied React Bits LineSidebar / GlassIcons references.
// Notices: public/agents/REACT-BITS-LICENSE.md. Application integration only.
import { useRef, type CSSProperties, type ReactNode } from 'react';

export type ReviewPage = 'workflow' | 'runs' | 'memory';
const pages: { id: ReviewPage; label: string }[] = [
  { id: 'workflow', label: 'Workspace' }, { id: 'runs', label: 'Runs' },
];
export function LineSidebar({ active, onSelect }: { active: ReviewPage; onSelect: (page: ReviewPage) => void }) {
  const list = useRef<HTMLElement>(null);
  const reset = () => list.current?.querySelectorAll<HTMLElement>('button').forEach((item) => item.style.setProperty('--effect', '0'));
  return <nav className="review-line-sidebar" aria-label="FRAG pages" ref={list} onPointerLeave={reset}
    onPointerMove={(event) => {
      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
      list.current?.querySelectorAll<HTMLElement>('button').forEach((item) => {
        const rect = item.getBoundingClientRect();
        const p = Math.max(0, 1 - Math.abs(event.clientY - rect.top - rect.height / 2) / 90);
        item.style.setProperty('--effect', String(p * p * (3 - 2 * p)));
      });
    }}>
    {pages.map((item) => <button key={item.id} type="button" aria-current={active === item.id ? 'page' : undefined}
      onClick={() => onSelect(item.id)}><span className="review-tick" /><span>{item.label}</span></button>)}
  </nav>;
}

export function GlassIcons({ active, onSelect, colorful = false }: {
  active: ReviewPage; onSelect: (page: ReviewPage) => void; colorful?: boolean;
}) {
  const items: { id: ReviewPage; label: string; icon: ReactNode }[] = [
    { id: 'memory', label: 'Memory', icon: <path d="M7 3h10v18H7zM4 7h3M4 12h3M4 17h3M10 7h4M10 12h4" /> },
  ];
  return <nav className="review-glass-icons" aria-label="FRAG background">{items.map((item) => <button type="button" key={item.id}
    aria-label={item.label} aria-current={active === item.id ? 'page' : undefined} onClick={() => onSelect(item.id)}
    style={{ '--glass-color': colorful ? '#7465ad' : '#ffffff18' } as CSSProperties}>
    <span className="review-glass-back" /><span className="review-glass-front">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">{item.icon}</svg>
    </span><span className="review-glass-label">{item.label}</span>
  </button>)}</nav>;
}

export function Stepper({ current }: { current: number }) {
  return <ol className="review-stepper" aria-label="Review progress">{['Evidence', 'Context', 'Inference', 'Review'].map((name, index) =>
    <li key={name} aria-current={index === current ? 'step' : undefined} data-complete={index < current}>
      <span>{index < current ? '✓' : index + 1}</span><strong>{name}</strong>
    </li>)}</ol>;
}
