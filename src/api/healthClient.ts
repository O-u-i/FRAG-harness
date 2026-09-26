import { contextHealthSchema, type ContextHealth } from '../../shared/contracts/health';

export async function checkBackendHealth(): Promise<ContextHealth> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), 5_000);
  try {
    const response = await fetch('/api/health', { signal: controller.signal, headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error(`FRAG backend is unavailable (HTTP ${response.status}).`);
    return contextHealthSchema.parse(await response.json());
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw new Error('Backend health check timed out.');
    if (error instanceof Error) throw error;
    throw new Error('Backend health check failed.');
  } finally {
    globalThis.clearTimeout(timeout);
  }
}
