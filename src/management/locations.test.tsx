import {expect,test,vi} from 'vitest';
import type {ReactElement,ReactNode} from 'react';
const hooks=vi.hoisted(()=>({states:[] as unknown[],cursor:0,effects:[] as {deps:unknown[];cleanup?:()=>void}[]}));
vi.mock('react',async original=>({...await original<typeof import('react')>(),
  useState:(initial:unknown)=>{const i=hooks.cursor++;if(!(i in hooks.states))hooks.states[i]=initial;return [hooks.states[i],(value:unknown)=>{hooks.states[i]=typeof value==='function'?value(hooks.states[i]):value;}];},
  useEffect:(effect:()=>void|(()=>void),deps:unknown[])=>{const i=hooks.cursor++,previous=hooks.effects[i];if(!previous||deps.some((value,j)=>value!==previous.deps[j])){previous?.cleanup?.();hooks.effects[i]={deps,cleanup:effect()||undefined};}},
}));
vi.mock('./client',()=>({request:vi.fn()}));
import {request} from './client';
import {LocationsPanel} from './locations';
import {AcceptancePanel} from './acceptance';
type Node=ReactElement<Record<string,any>>;
function render(component:()=>ReactElement){hooks.cursor=0;const element=component() as Node;return (typeof element.type==='function'?(element.type as (props:Record<string,any>)=>ReactElement)(element.props):element) as Node;}
function nodes(node:ReactNode):Node[]{if(Array.isArray(node))return node.flatMap(nodes);if(!node||typeof node!=='object'||!('props' in node))return [];const value=node as Node;return [value,...nodes(value.props.children)];}
function reset(){hooks.effects.forEach(effect=>effect?.cleanup?.());hooks.states=[];hooks.effects=[];hooks.cursor=0;vi.mocked(request).mockReset();}
const oldWorkspace={root:'old',sourceRoot:'old/sources',planPath:'old/sources/synthetic-plan.md',prepared:true};

test('a successful changed picker result notifies locations without authorizing or indexing',async()=>{
  reset();hooks.states[0]=oldWorkspace;const changed=vi.fn();
  vi.mocked(request).mockResolvedValue({...oldWorkspace,root:'new'});
  const view=render(()=> <AcceptancePanel open onToggle={()=>{}} onUseSource={()=>{}} onLocationChange={changed}/>);
  const pick=nodes(view).find(node=>node.type==='button'&&node.props.children==='Choose location…')!;
  pick.props.onClick();await Promise.resolve();await Promise.resolve();
  expect(changed).toHaveBeenCalledOnce();expect(request).toHaveBeenCalledExactlyOnceWith('workspace-pick',{});
  reset();hooks.states[0]=oldWorkspace;vi.mocked(request).mockResolvedValue(oldWorkspace);
  const unchanged=nodes(render(()=> <AcceptancePanel open onToggle={()=>{}} onUseSource={()=>{}} onLocationChange={changed}/>)).find(node=>node.type==='button'&&node.props.children==='Choose location…')!;
  unchanged.props.onClick();await Promise.resolve();expect(changed).toHaveBeenCalledOnce();
  reset();
});

test('expanded locations refresh on revision change and ignore an older pending result',async()=>{
  reset();let finishOld!:(value:unknown)=>void;
  vi.mocked(request).mockImplementationOnce(()=>new Promise(resolve=>{finishOld=resolve;}));
  const view=render(()=> <LocationsPanel refreshKey={0}/>);
  expect(request).not.toHaveBeenCalled();
  view.props.onToggle({currentTarget:{open:true}});render(()=> <LocationsPanel refreshKey={0}/>);
  expect(request).toHaveBeenCalledExactlyOnceWith('locations-info');
  const fresh={stateRoot:'state',hostRoot:'host',acceptanceRoot:'new',sourceRoot:'new/sources',planPath:'new/sources/synthetic-plan.md'};
  vi.mocked(request).mockResolvedValueOnce(fresh);render(()=> <LocationsPanel refreshKey={1}/>);await Promise.resolve();
  expect(hooks.states[0]).toEqual(fresh);finishOld({...fresh,acceptanceRoot:'old'});await Promise.resolve();
  expect(hooks.states[0]).toEqual(fresh);expect(request).toHaveBeenCalledTimes(2);
  reset();
});
