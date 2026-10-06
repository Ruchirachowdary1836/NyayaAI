const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

export type Retriever = 'bm25' | 'dense' | 'hybrid';

export interface Hit {
  doc_id: string;
  chunk_id: string;
  text: string;
  score: number;
  rank: number;
  source_scores: Record<string, number | null>;
  metadata: Record<string, unknown>;
}

export interface SearchResponse {
  query: string;
  retriever: Retriever;
  hits: Hit[];
  corpus_available: boolean;
}

export interface Passage {
  index: number;
  doc_id: string;
  chunk_id: string;
  text: string;
  score: number;
  source_scores: Record<string, number | null>;
}

export interface QAResponse {
  query: string;
  answer: string;
  citations: number[];
  invalid_citations: number[];
  unsupported_sentences: string[];
  passages: Passage[];
  confidence: number;
  disclaimer: string;
  refused: boolean;
}

export interface CompareResponse {
  query: string;
  results: Record<Retriever, Hit[]>;
  overlap: Record<string, number>;
}

export interface ExperimentRun {
  run_id: string;
  seed?: number;
  query_count?: number;
  document_count?: number;
  chunk_count?: number;
  systems?: Record<string, Record<string, number>>;
}

export interface AuthSession { access_token: string; token_type: string; role: 'user' | 'admin' }
export interface AdminOverview { corpus_documents: number; corpus_chunks: number; experiment_runs: number; users: number }
export interface AdminUser { username: string; role: string; created_at: string }

async function request<T>(path: string, init?: RequestInit, token?: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // Keep the useful HTTP status when a proxy returns a non-JSON error page.
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<{ status: string; corpus_documents?: number; corpus_chunks?: number }>('/ready'),
  search: (query: string, retriever: Retriever, k = 10) =>
    request<SearchResponse>('/api/v1/search', {
      method: 'POST',
      body: JSON.stringify({ query, retriever, k }),
    }),
  answer: (query: string, retriever: Retriever, k = 8) =>
    request<QAResponse>('/api/v1/qa', {
      method: 'POST',
      body: JSON.stringify({ query, retriever, k }),
    }),
  streamAnswer: async (
    query: string,
    retriever: Retriever,
    onToken: (token: string) => void,
    k = 8,
  ): Promise<QAResponse> => {
    const url = new URL(`${API_BASE}/api/v1/qa/stream`);
    url.searchParams.set('query', query);
    url.searchParams.set('retriever', retriever);
    url.searchParams.set('k', String(k));
    const response = await fetch(url, { headers: { Accept: 'text/event-stream' } });
    if (!response.ok || !response.body) {
      let detail = `Answer stream failed (${response.status})`;
      try {
        const body = (await response.json()) as { detail?: string };
        if (body.detail) detail = body.detail;
      } catch {
        // Preserve the transport error if the server returned non-JSON content.
      }
      throw new Error(detail);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let result: QAResponse | undefined;
    const consume = (block: string) => {
      const lines = block.split(/\r?\n/);
      const event = lines.find((line) => line.startsWith('event:'))?.slice(6).trim();
      const data = lines.find((line) => line.startsWith('data:'))?.slice(5).trim();
      if (!event || !data) return;
      const payload = JSON.parse(data) as QAResponse & { token?: string; detail?: string };
      if (event === 'token' && typeof payload.token === 'string') onToken(payload.token);
      else if (event === 'complete' || event === 'refusal') result = payload;
      else if (event === 'error') throw new Error(payload.detail ?? 'Answer stream failed');
    };
    try {
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value, { stream: !done });
        const blocks = buffer.split(/\r?\n\r?\n/);
        buffer = blocks.pop() ?? '';
        blocks.forEach(consume);
        if (done) break;
      }
    } finally {
      reader.releaseLock();
    }
    if (!result) throw new Error('Answer stream ended before a completed response was received');
    return result;
  },
  compare: (query: string, k = 5) =>
    request<CompareResponse>('/api/v1/compare', {
      method: 'POST',
      body: JSON.stringify({ query, retriever: 'hybrid', k }),
    }),
  experiments: () => request<ExperimentRun[]>('/api/v1/experiments'),
  document: (id: string) =>
    request<{ document: { doc_id: string; text: string; source: string; metadata: Record<string, unknown> }; chunks: Hit[] }>(
      `/api/v1/documents/${encodeURIComponent(id)}`,
    ),
  feedback: (query: string, rating: 'up' | 'down') =>
    request<{ accepted: boolean }>('/api/v1/feedback', {
      method: 'POST',
      body: JSON.stringify({ query, rating }),
    }),
  authenticate: (username: string, password: string, createAccount = false) =>
    request<AuthSession>(`/api/v1/auth/${createAccount ? 'register' : 'token'}`, {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  adminOverview: (token: string) =>
    request<AdminOverview>('/api/v1/admin/overview', undefined, token),
  adminUsers: (token: string) =>
    request<AdminUser[]>('/api/v1/admin/users', undefined, token),
};
