'use strict';
function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + canonical(value[key])).join(',') + '}';
  return JSON.stringify(value);
}
function omit(pack, ids) {
  const evidence = pack.evidence.filter(item => !ids.includes(item.evidenceId));
  const kept = new Set(evidence.map(item => item.evidenceId));
  return { ...pack, evidence, sourceBindings: pack.sourceBindings.filter(item => item.evidenceIds.some(id => kept.has(id)))
    .map(item => ({ ...item, evidenceIds: item.evidenceIds.filter(id => kept.has(id)) })),
    budget: { maxBytes: pack.budget.maxBytes, omittedEvidenceIds: [...new Set([...pack.budget.omittedEvidenceIds, ...ids])].sort() } };
}
async function fitPack(pack, tokenizer, cancellation) {
  const omitted = [];
  let value = pack, tokens = null;
  if (tokenizer) {
    if (!Number.isInteger(tokenizer.tokenBudget) || tokenizer.tokenBudget < 1) throw new Error('TOOL_TOKEN_BUDGET_INVALID');
    for (;;) {
      if (cancellation.isCancellationRequested) throw new Error('TOOL_CANCELLED');
      tokens = await tokenizer.countTokens(canonical(value), cancellation);
      if (tokens <= tokenizer.tokenBudget) break;
      if (!value.evidence.length) throw new Error('TOOL_TOKEN_BUDGET_TOO_SMALL_FOR_METADATA_AND_MEMORY');
      omitted.push(value.evidence[value.evidence.length - 1].evidenceId);
      value = omit(pack, omitted);
    }
  }
  return { omitted, tokens };
}
module.exports = { canonical, omit, fitPack };
