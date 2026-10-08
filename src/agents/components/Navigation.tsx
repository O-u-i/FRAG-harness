import { useEffect, useRef, useState } from 'react';
import BitsLineSidebar from './reactbits/LineSidebar';
import GlassIcons from './reactbits/GlassIcons';
import BranchedMenu from './reactbits/BranchedMenu';
import BitsStepper from './reactbits/Stepper';
export type ReviewPage = 'workflow' | 'runs' | 'settings' | 'memory';
export type MemorySection = 'candidates' | 'reviewed' | 'history';
const pages = ['workflow','runs','settings'] as const;
const labels = ['Workspace','Runs','Settings'];
function Icon({ index }: { index: number }) {
  return <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
    <path d={['M4 4h16v16H4zM4 9h16M9 9v11','M6 3h12v18H6zM9 7h6M9 12h6M9 17h4','M12 3v3m0 12v3M3 12h3m12 0h3M5.6 5.6l2.1 2.1m8.6 8.6 2.1 2.1M18.4 5.6l-2.1 2.1m-8.6 8.6-2.1 2.1M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0','M7 3h10v18H7zM4 7h3M4 12h3M4 17h3M10 7h4M10 12h4'][index]} />
  </svg>;
}
export function LineSidebar({ active, onSelect, memory, onMemory }: { active: ReviewPage; onSelect: (page: ReviewPage) => void;
  memory: MemorySection; onMemory: (section: MemorySection) => void }) {
  const [open,setOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    container.current?.querySelector<HTMLButtonElement>('#review-memory-flyout button')?.focus();
    const close = (event: Event) => {
      if ((event instanceof KeyboardEvent && event.key === 'Escape') ||
          (event.type === 'pointerdown' && !container.current?.contains(event.target as Node))) {
        setOpen(false);
        const button = trigger.current?.querySelector('button');
        if (event instanceof KeyboardEvent) button?.focus();
        else if (!(event.target instanceof Element) || !event.target.closest('a,button,input,textarea,select,[tabindex]')) {
          // Pointer default focus runs after pointerdown; do not steal a clicked control's focus.
          setTimeout(() => { if (button?.isConnected) button.focus(); }, 0);
        }
      }
    };
    document.addEventListener('keydown',close); document.addEventListener('pointerdown',close);
    return () => {document.removeEventListener('keydown',close); document.removeEventListener('pointerdown',close);};
  }, [open]);
  const pick = (value: string) => { onMemory(value as MemorySection); onSelect('memory'); setOpen(false); trigger.current?.querySelector('button')?.focus(); };
  const items = [{label:'Memory',children:[{value:'candidates',label:'Candidates'},{value:'reviewed',label:'Reviewed'},{value:'history',label:'History'}]}];
  return <div className="review-navigation" ref={container}>
    <div className="review-expanded-nav"><BitsLineSidebar items={labels} active={pages.indexOf(active as typeof pages[number])}
      onItemClick={(index) => onSelect(pages[index])} showIndex={false} accentColor="#eeedf0" markerLength={14} maxShift={5} itemGap={14} fontSize={.875} />
      <div className="review-memory-group"><BranchedMenu items={items} activeValue={active === 'memory' ? memory : ''} defaultActive="" defaultOpen={-1}
        width={160} indent={25} trunk={6} fontSize={13} rowHeight={40} onSelect={pick} /></div>
    </div>
    <nav className="review-rail-nav" aria-label="FRAG pages">
      {pages.map((page,index) => <button type="button" key={page} aria-label={labels[index]} title={labels[index]} aria-current={active === page ? 'page' : undefined}
        onClick={() => onSelect(page)}><Icon index={index} /></button>)}
      <div ref={trigger}><GlassIcons items={[{label:'Memory',color:'#77777735',icon:<Icon index={3} />,expanded:open,controls:'review-memory-flyout',onClick:() => setOpen(!open)}]} /></div>
    </nav>
    {open && <div id="review-memory-flyout" className="review-memory-flyout" role="dialog" aria-label="Memory pages">
      <BranchedMenu items={items} defaultOpen={0} activeValue={active === 'memory' ? memory : ''} width={230} fontSize={14} onSelect={pick} />
      <button type="button" onClick={() => {setOpen(false);trigger.current?.querySelector('button')?.focus();}}>Close menu</button>
    </div>}
  </div>;
}
export function Stepper({ names, current, reached, onView }: { names: string[]; current: number; reached: number; onView: (index: number) => void }) {
  return <BitsStepper step={current+1} reachedStep={reached+1} labels={names} headerOnly onStepChange={(step) => onView(step-1)}>
    {names.map((name) => <span key={name}>{name}</span>)}
  </BitsStepper>;
}
