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
