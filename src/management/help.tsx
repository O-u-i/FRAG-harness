import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

/** Desktop hover help; focus/Escape provide the basic keyboard equivalent. */
export function Help({ label, text }: { label: string; text: string }) {
  const trigger = useRef<HTMLSpanElement>(null), bubble = useRef<HTMLSpanElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined), id = useId();
  const [position, setPosition] = useState<{ left: number; top: number; width: number }>();
  const keep = () => clearTimeout(timer.current);
  const hide = () => { keep(); setPosition(undefined); };
  const leave = () => { keep(); timer.current = setTimeout(() => setPosition(undefined), 120); };
  const show = () => {
    keep();
    const rect = trigger.current!.getBoundingClientRect(), width = Math.min(400, innerWidth - 32);
    setPosition({ left: Math.max(16, Math.min(rect.left, innerWidth - width - 16)), top: rect.bottom + 8, width });
  };
  useEffect(() => () => clearTimeout(timer.current), []);
  useLayoutEffect(() => {
    if (!position || !bubble.current) return;
    const rect = bubble.current.getBoundingClientRect();
    if (rect.bottom > innerHeight - 16 && position.top > 16) {
      setPosition({ ...position, top: Math.max(16, innerHeight - rect.height - 16) });
    }
  }, [position]);
  return <span ref={trigger} className="help-icon" role="img" tabIndex={0} aria-label={`${label}: ${text}`}
    aria-describedby={position ? id : undefined} onFocus={show} onBlur={hide}
    onKeyDown={event => { if (event.key === 'Escape') hide(); }}
    onPointerEnter={event => { if (event.pointerType === 'mouse') show(); }} onPointerLeave={leave}>
    <span aria-hidden="true">?</span>
    {position && createPortal(<span ref={bubble} id={id} role="tooltip" className="help-tooltip" style={position}
      onPointerEnter={keep} onPointerLeave={leave}>{text}</span>, document.body)}
  </span>;
}
