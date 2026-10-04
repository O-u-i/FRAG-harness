/** Final SDK request guard; authentication is never included in receipts. */
import { isDeepStrictEqual } from 'node:util';

export class SafeFailure extends Error {
  constructor(code) { super(code); this.code = code; }
}
export const reject = (code = 'RAG_OUTPUT_INVALID') => { throw new SafeFailure(code); };

function boundedResponse(response, state) {
  if (!(response instanceof Response)) { state.failure = 'RAG_PROVIDER_ERROR'; reject(state.failure); }
  if (!response.body) return response;
  const reader = response.body.getReader();
  let bytes = 0;
  let cancelled = false;
  return new Response(new ReadableStream({
    async pull(controller) {
      try {
        const chunk = await reader.read();
        if (cancelled) return;
        if (chunk.done) { controller.close(); return; }
        bytes += chunk.value.byteLength;
        if (bytes > 1024 * 1024) {
          state.failure = state.terminal?.status === 'completed' ? 'RAG_OUTPUT_INVALID' : 'RAG_OUTCOME_UNKNOWN';
          await reader.cancel();
          controller.error(new SafeFailure(state.failure));
          return;
        }
        controller.enqueue(chunk.value);
      } catch {
        if (cancelled) return;
        state.failure ??= 'RAG_OUTCOME_UNKNOWN';
        controller.error(new SafeFailure(state.failure));
      }
    },
    cancel(reason) { cancelled = true; return reader.cancel(reason); },
  }), { status: response.status, statusText: response.statusText, headers: response.headers });
}

export function createGuardedFetch({ call, body, apiKey, state, signal, fetch, emit, checkIntegrity = async () => {} }) {
  return async (url, init) => {
    state.attempts += 1;
    if (state.attempts !== 1) { state.failure = 'RAG_PROVIDER_ERROR'; reject(state.failure); }
    let request, actualBody;
    try {
      request = new Request(url, init);
      const encoded = await request.clone().text();
      if (Buffer.byteLength(encoded) > 256 * 1024) reject();
      actualBody = JSON.parse(encoded);
    } catch { state.failure = 'RAG_OUTPUT_INVALID'; reject(state.failure); }
    if (request.method !== 'POST' || request.url !== call.endpoint || !isDeepStrictEqual(actualBody, body)
        || request.headers.get('authorization') !== `Bearer ${apiKey}`
        || !request.headers.get('content-type')?.startsWith('application/json')) {
      state.failure = 'RAG_OUTPUT_INVALID'; reject(state.failure);
    }
    try { await checkIntegrity(); } catch { state.failure = 'RAG_OUTPUT_INVALID'; reject(state.failure); }
    // Receipt flush must finish before crossing the outbound boundary.
    await emit({ protocolVersion: 1, event: 'dispatch', fingerprint: call.fingerprint });
    state.dispatched = true;
    let response;
    try {
      response = await fetch(call.endpoint, {
        method: 'POST', headers: request.headers, body: call.body, redirect: 'error', signal,
      });
    } catch { state.failure ??= 'RAG_OUTCOME_UNKNOWN'; reject(state.failure); }
    if (response.status < 200 || response.status >= 300) state.failure = 'RAG_PROVIDER_ERROR';
    return boundedResponse(response, state);
  };
}
