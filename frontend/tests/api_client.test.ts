import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiClient } from '../services/core/apiClient';

describe('apiClient', () => {
  afterEach(() => vi.restoreAllMocks());

  it('returns JSON and includes cookie credentials', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'content-type': 'application/json' } }));
    await expect(apiClient.get<{ ok: boolean }>('/health')).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/v1/health'), expect.objectContaining({ credentials: 'include', method: 'GET' }));
  });

  it('supports successful 204 responses', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }));
    await expect(apiClient.delete<void>('/resource/1')).resolves.toBeUndefined();
  });

  it('normalizes FastAPI validation errors', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: [{ msg: 'Field required' }] }), { status: 422, headers: { 'content-type': 'application/json' } }));
    const error = await apiClient.post('/runs', {}).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 422, message: 'Field required' });
  });

  it('rejects unexpected success response formats', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('<html />', { status: 200, headers: { 'content-type': 'text/html' } }));
    await expect(apiClient.get('/runs')).rejects.toMatchObject({ status: 200, message: 'The server returned an unexpected response format' });
  });
});
