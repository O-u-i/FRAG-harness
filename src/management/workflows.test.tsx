import { expect, test } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { WorkflowReceipts, type WorkflowReceipt } from './workflows';

const receipt:WorkflowReceipt = {id:'a'.repeat(32),kind:'recommendation_workflow',mode:'synthetic',ruleVersion:'recommendation-synthetic-v1',revision:2,
  createdAt:'2026-10-10T04:00:00+00:00',updatedAt:'2026-10-10T04:01:00+00:00',stage:'finished',status:'refused',reasonCode:'PLAN_MISSING',
  evidence:[{runId:'b'.repeat(32),resultDigest:'c'.repeat(64),requiredEvidenceIds:['d'.repeat(24)]}],planRevision:null,constraintsRevision:null,
  budget:{inputTokens:1000,outputTokens:500,liabilityMicroCny:7000,pendingRequests:0,usageUnknown:false,attempts:1,remediationRounds:0}};

test('workflow diagnostics remain separate from evidence, advice and human decisions',()=>{
  const html = renderToStaticMarkup(<WorkflowReceipts receipts={[receipt]}/>);
  for(const text of ['Production recommendations are unavailable','not evidence ToolRuns','does not filter native chat','Synthetic · refused','PLAN_MISSING','not correct, optimal, adopted or executed','not a provider billing guarantee','0.007000 CNY']) expect(html).toContain(text);
  expect(html).not.toContain('<details open');
});

test('workflow rendering uses allowlisted fields, never arbitrary JSON, draft or exception',()=>{
  const sentinel = 'synthetic-unchecked-private-body';
  const poisoned = {...receipt,draft:sentinel,summary:sentinel,exception:sentinel,nativeTranscript:sentinel};
  const html = renderToStaticMarkup(<WorkflowReceipts receipts={[poisoned]}/>);
  expect(html).not.toContain(sentinel);
  expect(html).not.toContain('complete audit JSON');
  expect(html).toContain('No recommendation body is stored or exported');
});

test('empty workflow panel is explicit without adding a native recommendation control',()=>{
  const html = renderToStaticMarkup(<WorkflowReceipts receipts={[]}/>);
  expect(html).toContain('No synthetic workflow receipts');
  expect(html).not.toContain('<button');
});
