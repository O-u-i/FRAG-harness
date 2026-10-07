// Adapted from the user-supplied React Bits LineSidebar / GlassIcons references.
// Notices: public/agents/REACT-BITS-LICENSE.md. Application integration only.
import { useRef, type CSSProperties, type ReactNode } from 'react';

export type ReviewPage = 'workflow' | 'runs' | 'memory' | 'plugins' | 'models';
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

const paths = {
  memory: <><path d="M7 3h10v18H7zM4 7h3M4 12h3M4 17h3M10 7h4M10 12h4" /></>,
  plugins: <><path d="M8 3v5m8-5v5M6 8h12v4a6 6 0 0 1-12 0zM12 18v3" /></>,
  models: <><path d="m12 3 9 5-9 5-9-5zM3 12l9 5 9-5M3 16l9 5 9-5" /></>,
};
export function GlassIcons({ active, onSelect }: { active: ReviewPage; onSelect: (page: ReviewPage) => void }) {
  const items: { id: 'memory' | 'plugins' | 'models'; label: string; color: string; icon: ReactNode }[] = [
    { id: 'memory', label: 'Memory', color: '#7465ad', icon: paths.memory },
    { id: 'plugins', label: 'Plugins', color: '#50829b', icon: paths.plugins },
    { id: 'models', label: 'Models', color: '#87785b', icon: paths.models },
  ];
  return <div className="review-glass-icons">{items.map((item) => <button type="button" key={item.id}
    aria-label={item.label} aria-current={active === item.id ? 'page' : undefined} onClick={() => onSelect(item.id)}
    style={{ '--glass-color': item.color } as CSSProperties}>
    <span className="review-glass-back" /><span className="review-glass-front">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">{item.icon}</svg>
    </span><span className="review-glass-label">{item.label}</span>
  </button>)}</div>;
}

export function Stepper({ current }: { current: number }) {
  return <ol className="review-stepper" aria-label="Review progress">{['Evidence', 'Context', 'Inference', 'Review'].map((name, index) =>
    <li key={name} aria-current={index === current ? 'step' : undefined} data-complete={index < current}>
      <span>{index < current ? '✓' : index + 1}</span><strong>{name}</strong>
    </li>)}</ol>;
}
