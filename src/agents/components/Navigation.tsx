import BitsLineSidebar from './reactbits/LineSidebar';
import BranchedMenu from './reactbits/BranchedMenu';
import BitsStepper from './reactbits/Stepper';
export type ReviewPage = 'workflow' | 'runs' | 'settings' | 'memory';
export type MemorySection = 'candidates' | 'reviewed' | 'history';
const pages = ['workflow','runs','settings'] as const;
const labels = ['Workspace','Runs','Settings'];
export function LineSidebar({ active, onSelect, memory, onMemory }: { active: ReviewPage; onSelect: (page: ReviewPage) => void;
  memory: MemorySection; onMemory: (section: MemorySection) => void }) {
  const pick = (value: string) => { onMemory(value as MemorySection); onSelect('memory'); };
  const items = [{label:'Memory',children:[{value:'candidates',label:'Candidates'},{value:'reviewed',label:'Reviewed'},{value:'history',label:'History'}]}];
  return <div className="review-navigation">
    <BitsLineSidebar items={labels} active={pages.indexOf(active as typeof pages[number])}
      onItemClick={(index) => onSelect(pages[index])} showIndex={false} accentColor="#eeedf0" markerLength={14} maxShift={5} itemGap={14} fontSize={.875} />
    <div className="review-memory-group"><BranchedMenu items={items} activeValue={active === 'memory' ? memory : ''} defaultActive="" defaultOpen={-1}
      width={160} indent={25} trunk={6} fontSize={13} rowHeight={40} onSelect={pick} /></div>
  </div>;
}
export function Stepper({ names, current, reached, onView }: { names: string[]; current: number; reached: number; onView: (index: number) => void }) {
  return <BitsStepper step={current+1} reachedStep={reached+1} labels={names} headerOnly onStepChange={(step) => onView(step-1)}>
    {names.map((name) => <span key={name}>{name}</span>)}
  </BitsStepper>;
}
