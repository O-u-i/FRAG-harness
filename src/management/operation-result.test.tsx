import {expect,test} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {OperationResult} from './operation-result';
test('ordinary index and Memory responses remain visible without developer JSON',()=>{
  expect(renderToStaticMarkup(<OperationResult result={{action:'source-status',label:'acceptance',value:{state:'ready',documentCount:2,chunkCount:3}}}/>)).toContain('2 documents');
  expect(renderToStaticMarkup(<OperationResult result={{action:'memory-recommend',value:[]}}/>)).toContain('No records found');
  const html=renderToStaticMarkup(<OperationResult result={{action:'memory-versions',value:[{id:'m1',version:2,contentVersion:1,status:'active',text:'Reviewed background',general:false,provenanceRunId:'run-1'}]}}/>);
  for(const text of ['Memory audit history','Source-scoped','Reviewed background','run-1']) expect(html).toContain(text);
  expect(renderToStaticMarkup(<OperationResult result={{action:'unrecognized',value:{private:'unexposed'}}}/>)).toBe('');
});
