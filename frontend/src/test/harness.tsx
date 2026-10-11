import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import App from '../App';
import { ToastProvider } from '../components/Toast';
import { AuthProvider } from '../lib/auth';
import { ThemeProvider } from '../lib/theme';

export type Route = (url: URL, init: RequestInit) => Response | Promise<Response> | undefined;

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

export const researcher = { username: 'researcher', role: 'user', is_active: true, created_at: '2026-10-01T00:00:00Z', last_login_at: null };

export const readyHealth = {
  status: 'ready',
  corpus_documents: 2,
  corpus_chunks: 3,
  available_retrievers: ['bm25', 'dense', 'hybrid'],
  generation_configured: true,
  generation_provider: 'ollama',
};

export const dashboard = {
  user: researcher,
  corpus: { documents: 2, chunks: 3, facets: { document_types: ['judgment', 'statute'], courts: ['Supreme Court of India'] } },
  retrievers: { bm25: { state: 'ready' }, dense: { state: 'not_loaded' }, hybrid: { state: 'not_loaded' } },
  generation: { provider: 'ollama', model: 'test-model', configured: true },
  library: { total: 0, by_status: {}, recent: [] },
  experiments: { total: 0, recent: [] },
  activity_last_30_days: {},
};

/** Installs a fetch mock. Unmatched requests fail the test loudly. */
export function mockApi(...routes: Route[]) {
  const calls: { url: URL; init: RequestInit }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(input.toString());
    calls.push({ url, init });
    for (const route of routes) {
      const response = await route(url, init);
      if (response) return response;
    }
    if (url.pathname === '/ready') return json(readyHealth);
    if (url.pathname === '/api/v1/auth/me') return json(researcher);
    if (url.pathname === '/api/v1/dashboard') return json(dashboard);
    throw new Error(`Unexpected request ${init.method ?? 'GET'} ${url.pathname}`);
  });
  vi.stubGlobal('fetch', fetchMock);
  return { fetchMock, calls };
}

export function renderApp(path: string, { signedIn = true } = {}) {
  if (signedIn) window.localStorage.setItem('nyayaai-token', 'test-token');
  else window.localStorage.removeItem('nyayaai-token');
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <ToastProvider>
            <AuthProvider>
              <App />
            </AuthProvider>
          </ToastProvider>
        </ThemeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}
