const test = require('node:test');
const assert = require('node:assert/strict');
const { canonical, fitPack, omit } = require('../tool-result.cjs');
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
