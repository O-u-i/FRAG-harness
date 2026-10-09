import { expect, test, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
vi.mock('./client',()=>({request:vi.fn()}));
import { MemoryPanel, MemoryEditor, type Memory } from './memory';
import type { Run } from './runs';

const record:Memory = {id:'memory-1',version:4,contentVersion:2,status:'candidate',text:'Reviewed background',general:false,conflicts:[],provenanceRunId:'source-run',legacyReadOnly:false};

test('Memory panel offers exact-ID search separately from its four recent Run options',()=>{
  const runs:Run[] = Array.from({length:6},(_,i)=>({id:`run-${i}`,tool:'frag_search',status:'completed',createdAt:'2026-10-09T12:00:00Z',sourceBindings:[{}],pack:{evidence:[{evidenceId:`e${i}`,locatorId:'s',text:'Evidence'}]}}));
  const html = renderToStaticMarkup(<MemoryPanel runs={runs} records={[]} busy={false} perform={async()=>{}}/>);
  expect(html).toContain('Search by exact Run ID'); expect(html).toContain('latest 4');
  for(let i=0;i<4;i++) expect(html).toContain(`value="run-${i}"`);
  expect(html).not.toContain('value="run-4"'); expect(html).not.toContain('value="run-5"');
  expect(html.match(/<option /g)).toHaveLength(5);
});

test('Memory labels content versions separately from audit revisions and blocks unchanged saves',()=>{
  const html = renderToStaticMarkup(<MemoryEditor record={record} busy={false} perform={async()=>{}}/>);
  expect(html).toContain('v2 · Revision 4');
  expect(html).toContain('<button disabled="">Save candidate revision</button>');
  expect(html).toContain('Other reviewed audit revision');
  const historical = renderToStaticMarkup(<MemoryEditor record={{...record,legacyReadOnly:true}} busy={false} perform={async()=>{}}/>);
  expect(historical).toContain('historical read-only'); expect(historical).not.toContain('Promote');
});
