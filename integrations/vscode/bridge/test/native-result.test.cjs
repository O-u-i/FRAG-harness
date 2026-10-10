const test = require('node:test');
const assert = require('node:assert/strict');
const { canonical, fitPack, omit } = require('../tool-result.cjs');

test('invalid native budgets fail before tokenization or evidence omission', async () => {
  const pack = {evidence:[{evidenceId:'report',text:'synthetic report'}],requiredEvidenceIds:['report'],sourceBindings:[{evidenceIds:['report']}],memoryBackground:[{text:'retained'}],budget:{maxBytes:16384,omittedEvidenceIds:[]}};
  const original = structuredClone(pack);
  let counts = 0;
  for (const tokenBudget of [NaN, undefined, Infinity, 0, -1, '2048']) {
    await assert.rejects(fitPack(pack,{tokenBudget,countTokens:async () => { counts++; return 1; }},{isCancellationRequested:false}),/TOOL_TOKEN_BUDGET_INVALID/);
  }
  assert.equal(counts,0);
  assert.deepEqual(pack,original);
});

test('required monthly report survives optional omissions and fails a smaller budget atomically', async () => {
  const pack = {evidence:[{evidenceId:'optional',text:'long text'},{evidenceId:'report',text:'all three months and coverage'}],requiredEvidenceIds:['report'],sourceBindings:[{evidenceIds:['optional','report']}],memoryBackground:[{text:'retained'}],budget:{maxBytes:16384,omittedEvidenceIds:[]}};
  const budget=canonical(omit(pack,['optional'])).length;
  const fitted=await fitPack(pack,{tokenBudget:budget,countTokens:async text=>text.length},{isCancellationRequested:false});
  assert.deepEqual(fitted.omitted,['optional']);
  assert.throws(()=>omit(pack,['report']),/REQUIRED_EVIDENCE/);
  await assert.rejects(fitPack(pack,{tokenBudget:budget-1,countTokens:async text=>text.length},{isCancellationRequested:false}),/REQUIRED_EVIDENCE/);
  assert.equal(pack.evidence.length,2);
});
test('canonical JSON and whole-evidence token budget preserve Memory', async () => {
  const pack = {runId:'synthetic',evidence:[{evidenceId:'a',text:'long text'},{evidenceId:'b',text:'more text'}],sourceBindings:[{evidenceIds:['a','b']}],memoryBackground:[{text:'retained reviewed background'}],budget:{maxBytes:16384,omittedEvidenceIds:[]}};
  assert.equal(canonical({z:1,a:['中',{b:true,a:null}]}), '{"a":["中",{"a":null,"b":true}],"z":1}');
  const budget = canonical(omit(pack,['b'])).length;
  const fitted = await fitPack(pack,{tokenBudget:budget,countTokens:async text=>text.length},{isCancellationRequested:false});
  assert.deepEqual(fitted.omitted,['b']);
  assert.deepEqual(omit(pack,fitted.omitted).memoryBackground,pack.memoryBackground);
  assert.deepEqual(omit(pack,fitted.omitted).sourceBindings,[{evidenceIds:['a']}]);
  await assert.rejects(fitPack(pack,{tokenBudget:1,countTokens:async text=>text.length},{isCancellationRequested:false}),/METADATA_AND_MEMORY/);
  assert.equal((await fitPack(pack,undefined,{isCancellationRequested:false})).tokens,null);
});
