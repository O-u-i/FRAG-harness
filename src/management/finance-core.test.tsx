import { expect, test } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { FinanceCoreFields, type FcCatalog } from './finance-core';

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
