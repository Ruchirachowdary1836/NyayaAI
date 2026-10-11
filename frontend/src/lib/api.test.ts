import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchApi } from './api';

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('API startup recovery', () => {
  it('retries transient initialization responses until the API is ready', async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: 'initializing' }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    const responsePromise = fetchApi('https://nyayaai-api-k9l9.onrender.com/ready');
    await vi.advanceTimersByTimeAsync(1000);

    await expect(responsePromise).resolves.toHaveProperty('status', 200);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('retries transient network failures', async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('Network error'))
      .mockResolvedValueOnce(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    const responsePromise = fetchApi('https://nyayaai-api-k9l9.onrender.com/health');
    await vi.advanceTimersByTimeAsync(1000);

    await expect(responsePromise).resolves.toHaveProperty('status', 200);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('retries transient Render gateway errors', async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response('Bad Gateway', { status: 502 }))
      .mockResolvedValueOnce(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    const responsePromise = fetchApi('https://nyayaai-api-k9l9.onrender.com/health');
    await vi.advanceTimersByTimeAsync(1000);

    await expect(responsePromise).resolves.toHaveProperty('status', 200);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('does not retry a failed API initialization as if it were transient', async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: 'failed' }), {
        status: 503,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchApi('https://nyayaai-api-k9l9.onrender.com/ready')).resolves.toHaveProperty(
      'status',
      503,
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe('API client errors', () => {
  it('does not retry a non-idempotent request that timed out', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{"detail":"timed out"}', { status: 504 }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(fetchApi('http://localhost:8000/api/v1/qa', { method: 'POST' })).resolves.toHaveProperty('status', 504);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('turns validation errors into readable messages and reports expired sessions', async () => {
    const { api, onUnauthorized, tokenStore } = await import('./api');
    tokenStore.set('expired');
    const listener = vi.fn();
    const unsubscribe = onUnauthorized(listener);
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: [{ loc: ['body', 'query'], msg: 'Query must contain text' }] }), { status: 422 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Invalid or expired access token' }), { status: 401 })));
    await expect(api.search({ query: ' ', retriever: 'bm25' })).rejects.toThrow('query: Query must contain text');
    await expect(api.me()).rejects.toMatchObject({ status: 401, message: 'Invalid or expired access token' });
    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
    tokenStore.clear();
  });
});
