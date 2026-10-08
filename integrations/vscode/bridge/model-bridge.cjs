'use strict';
// Original code; node built-ins and the stable VS Code API only.
const http = require('node:http');
const { createHash, randomBytes, timingSafeEqual } = require('node:crypto');
const { readFileSync } = require('node:fs');

const hash = value => createHash('sha256').update(value).digest('hex');
const keys = (value, expected) => value && typeof value === 'object' && !Array.isArray(value)
  && Object.keys(value).sort().join(',') === [...expected].sort().join(',');

function validateRequest(value) {
  if (!keys(value, ['modelId', 'revision', 'requestId', 'body']) || typeof value.modelId !== 'string'
      || !/^[a-f0-9]{64}$/.test(value.revision) || !/^[a-f0-9]{64}$/.test(value.requestId)) return false;
  const body = value.body;
  return keys(body, ['messages', 'options']) && Array.isArray(body.messages) && body.messages.length === 2
    && body.messages.every(row => keys(row, ['role', 'content']) && row.role === 'user' && typeof row.content === 'string')
    && keys(body.options, ['modelOptions']) && keys(body.options.modelOptions, ['max_tokens'])
    && Number.isInteger(body.options.modelOptions.max_tokens) && body.options.modelOptions.max_tokens > 0
    && body.options.modelOptions.max_tokens <= 2000;
}

async function startBridge(vscode, configFile) {
  const key = randomBytes(32).toString('hex'), consumed = new Set(), active = new Set();
  let closed = false;
  async function catalog() {
    // Fail closed on missing/invalid active-profile configuration. No key or URL leaves this process.
    const raw = readFileSync(configFile);
    const config = JSON.parse(raw.toString('utf8'));
    if (!Array.isArray(config)) throw new Error('Invalid model configuration.');
    // Empty configuration is an explicit model-free installation check. Do not
    // activate providers or wait for signed-out provider discovery in this mode.
    if (config.length === 0) return new Map();
    let timer;
    let models;
    try {
      models = await Promise.race([vscode.lm.selectChatModels(), new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error('Model discovery timed out')), 10000);
      })]);
    } finally { clearTimeout(timer); }
    const result = new Map();
    for (const model of models) {
      if (!model.id || model.id === 'auto' || !model.vendor || !Number.isInteger(model.maxInputTokens) || model.maxInputTokens <= 0) continue;
      const id = hash(JSON.stringify([model.vendor, model.id, model.version]));
      if (result.has(id)) throw new Error('Ambiguous model registration.');
      const groups = config.filter(group => group.vendor === model.vendor
        && Array.isArray(group.models) && group.models.some(row => row.id === model.id));
      // Stable API does not expose a group identifier. Multiple identical registrations are unsafe.
      if (groups.length > 1) throw new Error('Ambiguous model configuration.');
      if (groups.length === 0) continue; // Never expose models from an unbound provider/profile.
      const effort = groups[0]?.settings?.[model.id]?.reasoningEffort;
      const info = { id, name: model.name, vendor: model.vendor,
        revision: hash(Buffer.concat([raw, Buffer.from(JSON.stringify([model.id, model.name, model.vendor, model.version, model.maxInputTokens]))])),
        effort: typeof effort === 'string' ? effort : null, maxInputTokens: model.maxInputTokens };
      result.set(id, { model, info });
    }
    if (result.size > 200) throw new Error('Model catalog exceeds limit.');
    return result;
  }
  await catalog(); // Trigger model access from an explicit Start command, before exposing the bridge.
  const server = http.createServer(async (request, response) => {
    const reply = (status, value) => {
      if (!response.destroyed) { response.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }); response.end(JSON.stringify(value)); }
    };
    const supplied = Buffer.from(request.headers.authorization || '');
    const expected = Buffer.from('Bearer ' + key);
    if (closed || request.socket.remoteAddress !== '127.0.0.1' || request.headers.origin
        || request.headers.host !== `127.0.0.1:${server.address().port}`
        || supplied.length !== expected.length || !timingSafeEqual(supplied, expected)) return reply(403, { error: 'Rejected' });
    try {
      if (request.method === 'GET' && request.url === '/models') return reply(200, [...(await catalog()).values()].map(row => row.info));
      if (request.method !== 'POST' || request.url !== '/execute') return reply(404, { error: 'Not found' });
      const chunks = []; let size = 0;
      for await (const chunk of request) {
        size += chunk.length;
        if (size > 512 * 1024) { reply(413, { error: 'Request limit' }); request.destroy(); return; }
        chunks.push(chunk);
      }
      const value = JSON.parse(Buffer.concat(chunks).toString('utf8'));
      if (!validateRequest(value)) return reply(422, { error: 'Invalid request' });
      const entry = (await catalog()).get(value.modelId);
      if (!entry || entry.info.revision !== value.revision || consumed.has(value.requestId)) return reply(409, { error: 'Changed or consumed' });
      if (active.size) return reply(409, { error: 'A stage is active' });
      // Consume before any provider access. Never retry, including after an uncertain outcome.
      consumed.add(value.requestId);
      if (consumed.size > 10000) return reply(503, { error: 'Restart bridge and prepare a fresh request' });
      const cancel = new vscode.CancellationTokenSource();
      active.add(cancel);
      response.on('close', () => cancel.cancel());
      let timer;
      const work = (async () => {
        try {
          const messages = value.body.messages.map(row => vscode.LanguageModelChatMessage.User(row.content));
          const result = await entry.model.sendRequest(messages, value.body.options, cancel.token);
          let text = '';
          for await (const part of result.text) {
            text += part;
            if (cancel.token.isCancellationRequested || Buffer.byteLength(text) > 256 * 1024) throw new Error('Cancelled or over limit');
          }
          if (cancel.token.isCancellationRequested || (await catalog()).get(value.modelId)?.info.revision !== value.revision) throw new Error('Configuration changed');
          return text;
        } finally { active.delete(cancel); cancel.dispose(); }
      })();
      try {
        const deadline = new Promise((_, reject) => {
          timer = setTimeout(() => { cancel.cancel(); reject(new Error('Deadline')); }, 120000);
        });
        const text = await Promise.race([work, deadline]);
        reply(200, { text });
      } catch { reply(502, { error: 'Provider outcome unknown' }); }
      // An uncooperative provider keeps the active lease until its request settles. No overlapping resend.
      finally { clearTimeout(timer); }
    } catch { reply(503, { error: 'Model bridge unavailable' }); }
  });
  server.requestTimeout = 125000;
  server.headersTimeout = 10000;
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  let closing;
  return { key, address: `http://127.0.0.1:${server.address().port}`, close: () => {
    if (closing) return closing;
    closed = true; for (const cancel of active) cancel.cancel();
    server.closeAllConnections();
    closing = new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
    return closing;
  } };
}
module.exports = { startBridge, validateRequest };
