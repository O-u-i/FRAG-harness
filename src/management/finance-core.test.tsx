import { expect, test } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { FinanceCoreFields, validateFcSelection, type FcCatalog } from './finance-core';

const catalog:FcCatalog = {schemaVersion:1,workspace:{id:'synthetic',label:'Synthetic sandbox',kind:'sandbox'},
  readGrant:{mode:'all',itemIds:[]},selectedRecordIds:[],items:[
    {id:'account:'+'a'.repeat(32),label:'Living cash',kind:'account',segment:'living'},
    {id:'report:month-to-date',label:'Month to date · Journal',kind:'report',segment:'investment'}]};

test('connection UI offers the private editor and scoped friendly choices, never raw credential fields or JSON editing',()=>{
 const html=renderToStaticMarkup(<FinanceCoreFields catalog={catalog} busy={false} perform={async()=>{}} onChange={()=>{}}/ >);
 for(const label of ['Open connection file','Check connection','Synthetic sandbox','sandbox','Living cash','Month to date','0 / 10 selected','No financial records are read']) expect(html).toContain(label);
 for(const forbidden of ['type="password"','<textarea','RECORDS_JSON','Copy token']) expect(html).not.toContain(forbidden);
});

test('an explicitly selected report exposes a required native cutoff date, not an inferred full-month range',()=>{
 const html=renderToStaticMarkup(<FinanceCoreFields catalog={catalog} selection={{workspaceId:'synthetic',recordIds:['month-to-date:2026-08-18']}} busy={false} perform={async()=>{}} onChange={()=>{}}/ >);
 expect(html).toContain('type="date"');expect(html).toContain('required=""');expect(html).toContain('value="2026-08-18"');
 expect(html).toContain('1 / 10 selected');expect(html).toContain('Posted Journal activity only');
});

test('connected catalogs start compact with an accessible search toggle and meaningful type filters',()=>{
 const html=renderToStaticMarkup(<FinanceCoreFields catalog={catalog} busy={false} perform={async()=>{}} onChange={()=>{}}/>);
 expect(html).toContain('<details class="fc-setup">');
 expect(html).not.toContain('type="search"');
 expect(html).toContain('aria-label="Search items"');expect(html).toContain('aria-expanded="false"');
 for(const label of ['Selected only','aria-label="Item type"','Accounts','Reports','Living','Investment','2 shown']) expect(html).toContain(label);
 expect(html).toContain('Only checked items may be read; new items stay unselected.');
 expect(html).toContain('Reports include their named aggregate scope, not just checked accounts.');
});

test('unconnected setup stays open and a single item type does not add redundant filter controls',()=>{
 const disconnected=renderToStaticMarkup(<FinanceCoreFields busy={false} perform={async()=>{}} onChange={()=>{}}/>);
 expect(disconnected).toContain('<details class="fc-setup" open="">');
 expect(disconnected).toContain('Check the saved connection');
 const oneKind={...catalog,items:[catalog.items[0]]};
 const html=renderToStaticMarkup(<FinanceCoreFields catalog={oneKind} busy={false} perform={async()=>{}} onChange={()=>{}}/>);
 expect(html).not.toContain('aria-label="Item type"');
 expect(html).not.toContain('fc-report-scope');
});

test('an unrelated Vault selection is not silently rebound or displayed as authorized',()=>{
 const html=renderToStaticMarkup(<FinanceCoreFields catalog={catalog} selection={{workspaceId:'different-vault',recordIds:['finance-item:'+catalog.items[0].id]}} busy={false} perform={async()=>{}} onChange={()=>{}}/>);
 expect(html).toContain('role="alert"');expect(html).toContain('saved selection belongs to another Vault');
 expect(html).toContain('0 / 10 selected');expect(html).not.toContain('checked=""');
});

test('economic and monthly reports retain explicit required dates and whole-Vault scope',()=>{
 const reports:FcCatalog={...catalog,items:[
  {id:'report:economic-evidence',label:'Economic evidence',kind:'report',segment:null},
  {id:'report:monthly-review',label:'Monthly review',kind:'report',segment:null}]};
 const html=renderToStaticMarkup(<FinanceCoreFields catalog={reports} selection={{workspaceId:'synthetic',recordIds:['economic-evidence:2026-08-18:2026-12-31','monthly-review:2026-07']}} busy={false} perform={async()=>{}} onChange={()=>{}}/>);
 for(const label of ['Whole Vault','Balances as of','Obligations through','Final completed month','value="2026-08-18"','min="2026-08-18"','value="2026-12-31"','type="month"','value="2026-07"']) expect(html).toContain(label);
 expect(html.match(/required=""/g)).toHaveLength(3);
});

test('selection cap blocks only new selections while busy disables all financial controls',()=>{
 const items=Array.from({length:11},(_,index)=>({id:`account:${index}`,label:`Synthetic item ${index}`,kind:'account',segment:'living' as const}));
 const bounded:FcCatalog={...catalog,items};
 const selection={workspaceId:'synthetic',recordIds:items.slice(0,10).map(item=>'finance-item:'+item.id)};
 const html=renderToStaticMarkup(<FinanceCoreFields catalog={bounded} selection={selection} busy={false} perform={async()=>{}} onChange={()=>{}}/>);
 expect(html.match(/type="checkbox"/g)).toHaveLength(11);
 expect(html.match(/disabled=""/g)).toHaveLength(1);
 expect(html.match(/checked=""/g)).toHaveLength(10);expect(html).toContain('Selection limit reached');
 const paused=renderToStaticMarkup(<FinanceCoreFields catalog={bounded} selection={selection} busy={true} perform={async()=>{}} onChange={()=>{}}/>);
 expect(paused.match(/disabled=""/g)).toHaveLength(13);
});

test('rendering names and selections never prefetches financial evidence or changes authorization',()=>{
 const perform=()=>{throw new Error('Unexpected fetch');}, onChange=()=>{throw new Error('Unexpected selection change');};
 expect(()=>renderToStaticMarkup(<FinanceCoreFields catalog={catalog} busy={false} perform={perform} onChange={onChange}/>)).not.toThrow();
});

const validationCatalog:FcCatalog={...catalog,items:[...catalog.items,
 {id:'report:monthly-review',label:'Monthly review',kind:'report',segment:null},
 {id:'report:economic-evidence',label:'Economic evidence',kind:'report',segment:null}]};
const validate=(recordIds:string[],workspaceId='synthetic')=>validateFcSelection({workspaceId,recordIds},validationCatalog,'2026-10-19');

test('complete selection validation rejects missing report dates independently of filtered or unmounted controls',()=>{
 // The form validates the draft, not rendered inputs: a type/search/selected filter cannot hide these failures.
 for(const report of ['monthly-review:','month-to-date:','economic-evidence::','economic-evidence:2026-10-19:']) {
  expect(validate(['finance-item:'+catalog.items[0].id,report])).toBeTypeOf('string');
 }
 expect(validate(['finance-item:'+catalog.items[0].id,'monthly-review:2026-09','month-to-date:2026-10-19','economic-evidence:2026-10-19:2026-12-31'])).toBeUndefined();
});

test('economic report validation checks real dates and the exact positive 366-day maximum horizon',()=>{
 for(const record of ['economic-evidence:2026-02-30:2026-03-31','economic-evidence:2026-02-28:2026-02-30',
  'economic-evidence:2026-10-19:2026-10-19','economic-evidence:2026-10-19:2026-10-18',
  'economic-evidence:2026-10-19:2027-10-21','economic-evidence:2026-10-19:2026-12-31:extra']) expect(validate([record])).toBeTypeOf('string');
 for(const record of ['economic-evidence:2026-10-19:2026-10-20','economic-evidence:2026-10-19:2027-10-20',
  'economic-evidence:2024-02-29:2024-03-01']) expect(validate([record])).toBeUndefined();
});

test('report validation does not infer missing dates, accept invalid months or authorize future Journal activity',()=>{
 for(const record of ['monthly-review:2026-00','monthly-review:2026-13','monthly-review:2026-10','monthly-review:2026-09:extra',
  'month-to-date:2026-10-20','month-to-date:2026-02-30','month-to-date:2026-10-19:extra',
  'month-to-date:0000-01-01']) expect(validate([record])).toBeTypeOf('string');
 expect(validate(['monthly-review:2026-09'])).toBeUndefined();expect(validate(['month-to-date:2026-10-19'])).toBeUndefined();
});

test('full selection validation preserves grant, Vault, uniqueness and count boundaries',()=>{
 expect(validateFcSelection()).toBeTypeOf('string');expect(validate([])).toBeTypeOf('string');
 expect(validate(['month-to-date:2026-10-19'],'other-vault')).toBeTypeOf('string');
 expect(validate(['finance-item:account:'+'b'.repeat(32)])).toBeTypeOf('string');
 expect(validate(['month-to-date:2026-10-19','month-to-date:2026-10-19'])).toBeTypeOf('string');
 expect(validate(Array.from({length:11},(_,index)=>`month-to-date:2026-10-${String(index+1).padStart(2,'0')}`))).toBeTypeOf('string');
 expect(validateFcSelection({workspaceId:'synthetic',recordIds:['entry:outside']})).toBeTypeOf('string');
});
