/** Fixed synthetic stdin fixture; real Pi/SDK parsing with an in-memory fetch. */
import { execute } from '../worker.mjs';

const SYNTHETIC_KEY = 'sk-synthetic-worker-key';
const write = value => new Promise((resolve, reject) => {
  process.stdout.write(`${JSON.stringify(value)}\n`, error => error ? reject(error) : resolve());
});

function responseItems(call) {
  const body = JSON.parse(call.body);
  const user = body.input.find(item => item.role === 'user');
  const payload = JSON.parse(user.content.find(content => content.type === 'input_text').text);
  let output;
  if (call.purpose === 'research') {
    const observations = body.input.filter(item => item.type === 'function_call_output')
      .map(item => JSON.parse(item.output));
    if (!observations.length) {
      const source = payload.manifest[0];
      const argumentsText = JSON.stringify({ identity: { ...source.identity, workspaceId: null },
        revision: source.revision, locatorIds: source.locatorIds, evidenceIds: source.evidenceIds.slice(0, 1) });
      return [{ type: 'function_call', id: `fc_fixture_${call.fingerprint.slice(0, 20)}`,
        call_id: `call_fixture_${call.fingerprint.slice(0, 20)}`, name: 'kb_read',
        arguments: argumentsText, status: 'completed' }];
    }
    output = { action: 'finish', evidenceIds: [...new Set(observations.flatMap(item =>
      item.status === 'completed' ? item.result.evidence.map(row => row.evidenceId) : []))], missingInformation: [] };
  } else if (call.purpose === 'context') {
    output = { evidence: payload.evidence.map(row => ({ evidenceId: row.evidenceId, summary: row.text,
      preservedFacts: [row.text], uncertainty: [] })), missingInformation: payload.researchMissingInformation ?? [] };
  } else {
    const evidence = payload.context.evidence;
    output = { answer: evidence.map(row => row.summary).join(' '),
      claims: evidence.map(row => ({ text: row.summary, evidenceIds: [row.evidenceId] })),
      missingInformation: payload.context.missingInformation ?? [], disclaimer: 'Synthetic fixture; human review required.' };
  }
  return [{ type: 'message', id: `msg_fixture_${call.fingerprint.slice(0, 20)}`, role: 'assistant', status: 'completed',
    content: [{ type: 'output_text', text: JSON.stringify(output), annotations: [] }] }];
}

function syntheticSse(items) {
  const events = [{ type: 'response.created', response: { id: 'resp_fixture' } }];
  for (const [output_index, item] of items.entries()) {
    events.push({ type: 'response.output_item.added', output_index,
      item: item.type === 'function_call' ? { ...item, arguments: '' } : { ...item, content: [] } });
    if (item.type === 'function_call') events.push({ type: 'response.function_call_arguments.delta', output_index,
      delta: item.arguments.slice(0, 7) });
    events.push({ type: 'response.output_item.done', output_index, item });
  }
  events.push({ type: 'response.completed', response: { id: 'resp_fixture', status: 'completed', output: items,
    usage: { input_tokens: 40, output_tokens: 20, total_tokens: 60 } } });
  return new Response(events.map(event => `data: ${JSON.stringify(event)}\n\n`).join('') + 'data: [DONE]\n\n',
    { headers: { 'content-type': 'text/event-stream' } });
}

function solItems(call, items) {
  if (call.model !== 'gpt-6.1-sol') return items;
  const reasoning = { type: 'reasoning', id: `rs_fixture_${call.fingerprint.slice(0, 20)}`,
    summary: [], encrypted_content: `synthetic-opaque-ciphertext-${call.fingerprint}` };
  if (items.some(item => item.type === 'function_call')) {
    return [reasoning, { type: 'message', id: `msg_commentary_${call.fingerprint.slice(0, 20)}`,
      role: 'assistant', status: 'completed', phase: 'commentary',
      content: [{ type: 'output_text', text: 'Reading selected synthetic evidence.', annotations: [] }] },
      ...items.map(({ status: _completed, ...item }) => item)];
  }
  return [reasoning, ...items.map(item => ({ ...item, phase: 'final_answer' }))];
}

async function main() {
  for (const name of ['log', 'debug', 'info', 'warn', 'error']) console[name] = () => {};
  const chunks = [];
  let bytes = 0;
  for await (const chunk of process.stdin) {
    bytes += chunk.length;
    if (bytes > 256 * 1024) throw new Error('INPUT_LIMIT');
    chunks.push(chunk);
  }
  const input = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  if (input.apiKey !== SYNTHETIC_KEY) {
    await write({ protocolVersion: 1, event: 'result', fingerprint: input.preparedCall?.fingerprint ?? '',
      ok: false, errorCode: 'RAG_OUTPUT_INVALID', dispatched: false });
    return;
  }
  const result = await execute(input, { emit: write,
    fetch: async () => syntheticSse(solItems(input.preparedCall, responseItems(input.preparedCall))) });
  await write(result);
}

main().catch(async () => {
  await write({ protocolVersion: 1, event: 'result', fingerprint: '', ok: false,
    errorCode: 'RAG_OUTPUT_INVALID', dispatched: false });
});
