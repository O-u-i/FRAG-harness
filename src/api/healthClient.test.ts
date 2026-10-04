import { afterEach, describe, expect, it, vi } from 'vitest';
import { checkBackendHealth } from './healthClient';

afterEach(() => vi.unstubAllGlobals());

const context = { status: 'ok', service: 'frag-harness', serviceVersion: '1.6.0' };

function healthFetch(payload: unknown = context) {
  return vi.fn(async () => new Response(
    JSON.stringify(payload),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  ));
}

describe('checkBackendHealth', () => {
  it('reports an empty proxy failure without a JSON parser error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 500 })));
    await expect(checkBackendHealth()).rejects.toThrow('FRAG backend is unavailable (HTTP 500)');
  });

  it('reports malformed successful responses without exposing their body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>private diagnostic</html>')));
    await expect(checkBackendHealth()).rejects.toThrow();
  });

  it('validates the independent FRAG backend', async () => {
    vi.stubGlobal('fetch', healthFetch());
    await expect(checkBackendHealth()).resolves.toEqual(context);
  });

  it('rejects an invalid response contract', async () => {
    vi.stubGlobal('fetch', healthFetch({ status: 'ok' }));
    await expect(checkBackendHealth()).rejects.toThrow();
  });

  it('preserves a network failure message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Failed to fetch')));
    await expect(checkBackendHealth()).rejects.toThrow('Failed to fetch');
  });
});
