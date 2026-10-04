/** One host-approved Pi Responses request. The worker never executes tools. */
import { isDeepStrictEqual } from 'node:util';
import { pathToFileURL } from 'node:url';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { verifyPackage } from './verify-package.mjs';
import { createGuardedFetch, reject, SafeFailure } from './wire.mjs';

const PI_COMMIT = 'a13d35a742c6ef8462812a28fbe1d8c8b7431c32';
const MAX_INPUT_BYTES = 256 * 1024;
const MAX_RESULT_BYTES = 256 * 1024;
const TOOL_NAMES = new Set(['kb_read', 'kb_search']);
const MODEL = /^gpt-4\.1(?:-mini|-nano)?(?:-2025-04-14)?$/;
const SOL = 'gpt-6.1-sol';
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const ADAPTER_KEYS = ['name', 'version', 'piCommit', 'protocolVersion', 'wireVersion',
  'selectionManifestHash', 'workerFiles', 'hostAdapterHash'];
const WORKER_FILES = ['worker.mjs', 'wire.mjs', 'verify-package.mjs'];
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
const exactKeys = (value, required, optional = []) => record(value)
  && required.every(key => own(value, key)) && Object.keys(value).every(key => [...required, ...optional].includes(key));
const identifier = value => typeof value === 'string' && value.length > 0 && value.length <= 256;

function canonicalEndpoint(value) {
  if (typeof value !== 'string' || !/^https:\/\/[a-z0-9][a-z0-9.-]*\/v1\/responses$/.test(value)) return false;
  const url = new URL(value);
  return url.href === value && !url.port && url.hostname.length <= 253
    && url.hostname.split('.').every(label => /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label));
}

export async function adapterIntegrity() {
  const files = await Promise.all(WORKER_FILES.map(async name => [name, sha256(await readFile(new URL(name, import.meta.url)))]));
  return { name: 'pi-openai-responses', version: '1.0.0', piCommit: PI_COMMIT, protocolVersion: 1, wireVersion: 1,
    selectionManifestHash: sha256(await readFile(new URL('./vendor/pi-ai/selection-manifest.json', import.meta.url))),
    workerFiles: Object.fromEntries(files) };
}

async function validateAdapter(adapter) {
  if (!record(adapter) || !isDeepStrictEqual(Object.keys(adapter).sort(), [...ADAPTER_KEYS].sort())
      || !/^[a-f0-9]{64}$/.test(adapter.hostAdapterHash)
      || !/^[a-f0-9]{64}$/.test(adapter.selectionManifestHash) || !record(adapter.workerFiles)
      || !isDeepStrictEqual(Object.keys(adapter.workerFiles).sort(), [...WORKER_FILES].sort())
      || Object.values(adapter.workerFiles).some(value => typeof value !== 'string' || !/^[a-f0-9]{64}$/.test(value))) reject();
  const { hostAdapterHash: _hostHash, ...workerBinding } = adapter;
  if (!isDeepStrictEqual(workerBinding, await adapterIntegrity())) reject();
}
let piModule;
async function loadPi() {
  piModule ??= verifyPackage().then(() => import('./vendor/pi-ai/dist/api/openai-responses.js'));
  return piModule;
}

function validateInput(input, testing) {
  if (!record(input) || input.protocolVersion !== 1 || !record(input.preparedCall)
      || typeof input.apiKey !== 'string' || !input.apiKey.startsWith('sk-')
      || /\s/.test(input.apiKey) || input.apiKey.length > 4096) reject();
  const call = input.preparedCall;
  if (call.schemaVersion !== 1 || call.provider !== 'openai' || call.transport !== 'pi-responses-v1'
      || !['research', 'context', 'inference'].includes(call.purpose)
      || typeof call.model !== 'string' || (call.model !== SOL && !MODEL.test(call.model))
      || !/^[a-f0-9]{64}$/.test(call.fingerprint)
      || !Number.isFinite(call.timeoutSeconds) || call.timeoutSeconds <= 0 || call.timeoutSeconds > 120
      || call.maxRetries !== 0 || typeof call.body !== 'string' || typeof call.binding !== 'string'
      || Buffer.byteLength(call.body) > MAX_INPUT_BYTES || call.body.includes(input.apiKey)
      || call.binding.includes(input.apiKey)) reject();
  const endpoint = new URL(call.endpoint);
  const loopback = testing && ['127.0.0.1', 'localhost', '[::1]'].includes(endpoint.hostname)
    && endpoint.protocol === 'http:' && endpoint.pathname === '/v1/responses'
    && !endpoint.username && !endpoint.password && !endpoint.search && !endpoint.hash;
  if (!canonicalEndpoint(call.endpoint) && !loopback) reject();
  const binding = JSON.parse(call.binding);
  if (!record(binding) || !record(binding.adapter)) reject();
  const sol = call.model === SOL;
  if (sol && binding.nativeReplayVersion !== 2) reject();
  const body = JSON.parse(call.body);
  if (!record(body) || body.model !== call.model || body.stream !== true || body.store !== false
      || !Array.isArray(body.tools) || !Number.isInteger(body.max_output_tokens)
      || body.max_output_tokens < 16 || body.max_output_tokens > { research: 800, context: 1500, inference: 2000 }[call.purpose]
      || !record(body.text) || !record(body.text.format) || body.text.format.type !== 'json_schema'
      || body.text.format.strict !== true || !record(body.text.format.schema)
      || own(body, 'previous_response_id') || own(body, 'conversation') || own(body, 'background')
      || own(body, 'prompt_cache_key')) reject();
  if (sol ? !isDeepStrictEqual(body.reasoning, { effort: 'low' })
      || !isDeepStrictEqual(body.include, ['reasoning.encrypted_content'])
    : own(body, 'reasoning') || own(body, 'include')) reject();
  if (call.purpose !== 'research' && body.tools.length !== 0) reject();
  if (body.tools.length > 2 || new Set(body.tools.map(tool => tool.name)).size !== body.tools.length) reject();
  for (const tool of body.tools) {
    if (!record(tool) || tool.type !== 'function' || !TOOL_NAMES.has(tool.name)
        || tool.strict !== true || !record(tool.parameters) || own(tool, 'namespace')
        || own(tool, 'defer_loading')) reject();
  }
  return { call, body, adapter: binding.adapter, sol };
}

function validSolItem(item) {
  if (!identifier(item.id)) reject();
  if (item.type === 'reasoning') {
    if (!exactKeys(item, ['id', 'type', 'summary'], ['status', 'encrypted_content', 'content'])
        || (own(item, 'status') && item.status !== 'completed')
        || (own(item, 'encrypted_content') && item.encrypted_content !== null && typeof item.encrypted_content !== 'string')
        || !Array.isArray(item.summary) || item.summary.some(part => !exactKeys(part, ['type', 'text'])
          || part.type !== 'summary_text' || typeof part.text !== 'string')
        || (own(item, 'content') && (!Array.isArray(item.content) || item.content.some(part =>
          !exactKeys(part, ['type', 'text']) || part.type !== 'reasoning_text' || typeof part.text !== 'string')))) reject();
  } else if (item.type === 'message') {
    if (!exactKeys(item, ['type', 'id', 'role', 'status', 'content'], ['phase'])
        || (own(item, 'phase') && ![null, 'commentary', 'final_answer'].includes(item.phase))) reject();
    for (const part of item.content ?? []) {
      if (part.type === 'refusal') {
        if (!exactKeys(part, ['type', 'refusal']) || typeof part.refusal !== 'string') reject();
      } else if (!exactKeys(part, ['type', 'text', 'annotations'], ['logprobs'])
          || part.type !== 'output_text' || typeof part.text !== 'string'
          || !Array.isArray(part.annotations) || part.annotations.length
          || (own(part, 'logprobs') && (!Array.isArray(part.logprobs) || part.logprobs.length))) reject();
    }
  } else if (item.type === 'function_call') {
    if (!exactKeys(item, ['type', 'id', 'call_id', 'name', 'arguments'], ['status'])
        || (own(item, 'status') && item.status !== 'completed')
        || !identifier(item.call_id) || typeof item.arguments !== 'string'
        || !item.arguments || Buffer.byteLength(item.arguments) > 16 * 1024) reject();
  } else reject();
}

function completedItemMatches(observed, item, index, sol) {
  if (!observed || observed.index !== index) return false;
  if (isDeepStrictEqual(observed.item, item)) return true;
  if (!sol || item.type !== 'reasoning' || observed.item.type !== 'reasoning'
      || (observed.item.encrypted_content !== undefined && observed.item.encrypted_content !== null)
      || typeof item.encrypted_content !== 'string' || !item.encrypted_content) return false;
  const { encrypted_content: _before, ...before } = observed.item;
  const { encrypted_content: _after, ...after } = item;
  return isDeepStrictEqual(before, after);
}

function normalizeCompleted(terminal, doneItems, piMessage, purpose, sol) {
  if (!record(terminal) || terminal.status !== 'completed' || !Array.isArray(terminal.output)) reject('RAG_INCOMPLETE');
  if (!record(piMessage) || !['stop', 'toolUse'].includes(piMessage.stopReason)
      || piMessage.rawStopReason !== 'completed') reject();
  const calls = [];
  let outputText = '';
  const ids = new Set();
  if (terminal.output.length > 64) reject();
  for (const [index, item] of terminal.output.entries()) {
    if (!record(item) || (item.status !== 'completed' && !(sol
      && ['reasoning', 'function_call'].includes(item.type) && !own(item, 'status')))
        || typeof item.id !== 'string' || ids.has(item.id)) reject();
    if (sol) validSolItem(item);
    ids.add(item.id);
    const observed = doneItems.get(item.id);
    if (!completedItemMatches(observed, item, index, sol)) reject();
    if (item.type === 'message') {
      if (item.role !== 'assistant' || !Array.isArray(item.content)) reject();
      for (const content of item.content) {
        if (content.type === 'refusal') reject('RAG_REFUSAL');
        if (content.type !== 'output_text' || typeof content.text !== 'string') reject();
        if (!sol || item.phase !== 'commentary') outputText += content.text;
      }
    } else if (item.type === 'function_call') {
      if (purpose !== 'research' || !TOOL_NAMES.has(item.name) || typeof item.call_id !== 'string'
          || !item.call_id || typeof item.arguments !== 'string' || !item.arguments
          || own(item, 'namespace') || calls.some(call => call.callId === item.call_id)) reject();
      calls.push({ callId: item.call_id, itemId: item.id, name: item.name, argumentsText: item.arguments });
    } else if (!sol || item.type !== 'reasoning') reject();
  }
  if (doneItems.size !== terminal.output.length || calls.length > 6
      || (calls.length > 0 && outputText.trim())
      || (sol && calls.length === 0 && !outputText.trim())
      || piMessage.stopReason !== (calls.length ? 'toolUse' : 'stop')) reject();
  if (sol && calls.length && terminal.output.some(item => item.type === 'reasoning'
      && (typeof item.encrypted_content !== 'string' || !item.encrypted_content))) reject();
  const usage = terminal.usage;
  if (!record(usage) || !Number.isSafeInteger(usage.input_tokens) || usage.input_tokens < 0
      || !Number.isSafeInteger(usage.output_tokens) || usage.output_tokens < 0) reject();
  return { status: 'completed', outputText, calls,
    usage: { inputTokens: usage.input_tokens, outputTokens: usage.output_tokens },
    ...(sol ? { outputItems: structuredClone(terminal.output) } : {}) };
}

/** Test fetch injection never changes the production entry's fixed destination. */
export async function execute(input, { fetch: testFetch, emit = () => {} } = {}) {
  const state = { dispatched: false, attempts: 0, failure: null, terminal: null, refusal: false };
  const fingerprint = typeof input?.preparedCall?.fingerprint === 'string' && /^[a-f0-9]{64}$/.test(input.preparedCall.fingerprint)
    ? input.preparedCall.fingerprint : '';
  const envelope = { protocolVersion: 1, event: 'result', fingerprint };
  let timer;
  try {
    const { call, body, adapter, sol } = validateInput(input, typeof testFetch === 'function');
    await validateAdapter(adapter);
    let piResponses;
    try { ({ stream: piResponses } = await loadPi()); } catch { reject('RAG_PROVIDER_ERROR'); }
    const controller = new AbortController();
    timer = setTimeout(() => { state.failure = 'RAG_OUTCOME_UNKNOWN'; controller.abort(); }, call.timeoutSeconds * 1000);
    const doneItems = new Map();
    const doneIndices = new Set();
    const model = { id: call.model, name: call.model, api: 'openai-responses', provider: 'openai',
      baseUrl: call.endpoint.slice(0, -'/responses'.length), reasoning: sol, input: ['text'],
      contextWindow: 1_000_000, maxTokens: body.max_output_tokens,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }, compat: { supportsStrictMode: true } };
    const guardedFetch = createGuardedFetch({ call, body, apiKey: input.apiKey, state,
      signal: controller.signal, fetch: testFetch ?? globalThis.fetch, emit,
      checkIntegrity: () => validateAdapter(adapter) });
    const stream = piResponses(model, { messages: [] }, {
      apiKey: input.apiKey, fetch: guardedFetch, signal: controller.signal,
      timeoutMs: call.timeoutSeconds * 1000, maxRetries: 0, maxRetryDelayMs: 1,
      transport: 'sse', cacheRetention: 'none', maxTokens: body.max_output_tokens,
      ...(sol ? { reasoningEffort: 'low' } : {}),
      onPayload: () => JSON.parse(call.body),
      onProviderStreamEvent(event) {
        if (event.type === 'response.refusal.delta' || event.type === 'response.refusal.done') state.refusal = true;
        if (event.type === 'response.output_item.done') {
          if (!record(event.item) || typeof event.item.id !== 'string' || doneItems.has(event.item.id)
              || !Number.isInteger(event.output_index) || event.output_index < 0 || doneIndices.has(event.output_index)) reject();
          doneIndices.add(event.output_index);
          doneItems.set(event.item.id, { index: event.output_index, item: structuredClone(event.item) });
          if (event.item.type === 'message' && event.item.content?.some(content => content.type === 'refusal')) state.refusal = true;
        }
        if (event.type === 'response.completed' || event.type === 'response.incomplete' || event.type === 'response.failed') {
          if (state.terminal !== null) reject();
          state.terminal = structuredClone(event.response);
          if (event.type === 'response.incomplete') state.failure = 'RAG_INCOMPLETE';
          if (event.type === 'response.failed') state.failure = 'RAG_PROVIDER_ERROR';
        }
      },
    });
    for await (const _event of stream) { /* Fragments are never executable protocol messages. */ }
    const message = await stream.result();
    if (state.refusal) reject('RAG_REFUSAL');
    if (state.failure) reject(state.failure);
    if (!state.terminal) reject(state.dispatched ? 'RAG_OUTCOME_UNKNOWN' : 'RAG_PROVIDER_ERROR');
    const result = { ...envelope, ok: true, response: normalizeCompleted(state.terminal, doneItems, message, call.purpose, sol) };
    const encoded = JSON.stringify(result);
    if (Buffer.byteLength(encoded) > MAX_RESULT_BYTES || encoded.includes(input.apiKey)) reject();
    return result;
  } catch (error) {
    return { ...envelope, ok: false, errorCode: state.refusal ? 'RAG_REFUSAL'
      : state.failure ?? (error instanceof SafeFailure ? error.code : 'RAG_OUTPUT_INVALID'), dispatched: state.dispatched };
  } finally { if (timer) clearTimeout(timer); }
}

async function main() {
  // The dependency's default SDK logger must never write provider diagnostics.
  for (const name of ['log', 'debug', 'info', 'warn', 'error']) console[name] = () => {};
  let input;
  try {
    if (['NODE_OPTIONS', 'NODE_USE_ENV_PROXY', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
      'http_proxy', 'https_proxy', 'all_proxy', 'GLOBAL_AGENT_HTTP_PROXY'].some(name => process.env[name])) reject();
    const chunks = [];
    let bytes = 0;
    for await (const chunk of process.stdin) {
      bytes += chunk.length;
      if (bytes > MAX_INPUT_BYTES) reject();
      chunks.push(chunk);
    }
    input = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    const write = value => new Promise((resolve, rejectWrite) => {
      process.stdout.write(`${JSON.stringify(value)}\n`, error => error ? rejectWrite(error) : resolve());
    });
    const result = await execute(input, { emit: write });
    await write(result);
  } catch {
    process.stdout.write(`${JSON.stringify({ protocolVersion: 1, event: 'result', fingerprint: '',
      ok: false, errorCode: 'RAG_OUTPUT_INVALID', dispatched: false })}\n`);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(() => { process.exitCode = 1; });
}
