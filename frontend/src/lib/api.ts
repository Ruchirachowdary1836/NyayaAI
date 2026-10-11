// Single source of truth for the API origin. Set VITE_API_BASE_URL at build time.
export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '');

export type Retriever = 'bm25' | 'dense' | 'hybrid';
export type Role = 'user' | 'admin';

export interface Hit {
  doc_id: string;
  chunk_id: string;
  title: string;
  text: string;
  excerpt: string;
  score: number;
  rank: number;
  source_scores: Record<string, number | null>;
  metadata: Record<string, unknown>;
}

export interface SearchParams {
  query: string;
  retriever: Retriever;
  k?: number;
  page?: number;
  document_type?: string | null;
  court?: string | null;
  year_from?: number | null;
  year_to?: number | null;
  group_by_document?: boolean;
  sort?: 'relevance' | 'title' | 'document' | 'newest' | 'oldest';
}

export interface SearchResponse {
  query: string;
  retriever: Retriever;
  hits: Hit[];
  corpus_available: boolean;
  page: number;
  page_size: number;
  total: number;
  total_is_capped: boolean;
  latency_ms: number;
  filters: Record<string, string | number | null>;
}

export interface Passage {
  index: number;
  doc_id: string;
  chunk_id: string;
  title: string;
  text: string;
  score: number;
  source_scores: Record<string, number | null>;
  metadata: Record<string, unknown>;
}

export interface QAResponse {
  query: string;
  answer: string;
  citations: number[];
  invalid_citations: number[];
  unsupported_sentences: string[];
  interpretation: string | null;
  passages: Passage[];
  confidence: number;
  disclaimer: string;
  refused: boolean;
  refusal_reason: string | null;
  model?: string | null;
  provider?: string | null;
}

export interface EngineResult { hits: Hit[]; latency_ms: number | null; error: string | null }

export interface CompareResponse {
  query: string;
  k: number;
  results: Partial<Record<Retriever, Hit[]>>;
  engines: Partial<Record<Retriever, EngineResult>>;
  overlap: Record<string, number>;
  unavailable: Partial<Record<Retriever, string>>;
}

export interface RetrieverStatus {
  state: 'ready' | 'not_loaded' | 'loading' | 'failed' | 'disabled';
  model?: string;
  error?: string;
  chunks?: number;
  fusion?: string;
  alpha?: number;
  rrf_k?: number;
}

export interface APIHealth {
  status: string;
  detail?: string;
  database?: string;
  corpus_documents?: number;
  corpus_chunks?: number;
  generation_configured?: boolean;
  generation_provider?: string;
  generation_model?: string | null;
  available_retrievers?: Retriever[];
  retrievers?: Partial<Record<Retriever, RetrieverStatus>>;
}

export interface BenchmarkRun {
  run_id: string;
  seed?: number;
  query_count?: number;
  document_count?: number;
  chunk_count?: number;
  dataset_name?: string;
  source_url?: string;
  license?: string;
  attribution?: string;
  evaluation_protocol?: string;
  tasks?: Record<string, {
    query_count: number;
    document_count: number;
    chunk_count: number;
    missing_judged_document_ids?: string[];
    systems: Record<string, Record<string, number>>;
  }>;
  systems?: Record<string, Record<string, number>>;
  comparisons?: Record<string, unknown>;
}

export interface ExperimentSystemSummary {
  status: 'ok' | 'unavailable';
  error?: string;
  evaluated_queries?: number;
  metrics?: Record<string, number>;
  mean_latency_ms?: number | null;
  median_latency_ms?: number | null;
}

export interface ExperimentSummary {
  experiment_id: string;
  name: string;
  status: 'completed' | 'partial' | 'failed';
  config: { retrievers: Retriever[]; k: number; query_count: number; hybrid?: Record<string, unknown>; embedding_model?: string };
  summary: {
    query_count: number;
    judged_query_count: number;
    cutoffs: number[];
    systems: Partial<Record<Retriever, ExperimentSystemSummary>>;
    unknown_relevant_doc_ids: string[];
    corpus: { documents: number; chunks: number };
    notes: string[];
  };
  duration_ms: number;
  created_at: string | null;
}

export interface RankingRow { rank: number; doc_id: string; chunk_id: string; title: string; score: number }

export interface ExperimentDetail extends ExperimentSummary {
  results: {
    queries: {
      index: number;
      query: string;
      relevant_doc_ids: string[];
      systems: Partial<Record<Retriever, {
        ranking?: RankingRow[];
        latency_ms?: number;
        metrics?: Record<string, number>;
        relevant_retrieved?: number;
        error?: string;
      }>>;
    }[];
  };
}

export interface ExperimentInput {
  name: string;
  retrievers: Retriever[];
  k: number;
  queries: { query: string; relevant_doc_ids: string[] }[];
}

export interface AuthSession {
  access_token: string;
  token_type: string;
  role: Role;
  username: string;
  expires_in: number;
}

export interface UserProfile {
  username: string;
  role: Role;
  is_active: boolean;
  created_at: string | null;
  last_login_at: string | null;
}

export interface CorpusDocumentSummary {
  doc_id: string;
  source: string;
  title: string;
  document_type: string | null;
  court: string | null;
  excerpt: string;
  char_count: number;
  metadata: Record<string, unknown>;
}

export interface CorpusDocumentList {
  documents: CorpusDocumentSummary[];
  total: number;
  limit: number;
  offset: number;
  facets: { document_types: string[]; courts: string[] };
}

export interface CorpusChunk { chunk_id: string; doc_id: string; text: string; start_char: number; end_char: number; token_count: number }

export interface CorpusDocument {
  document: { doc_id: string; text: string; source: string; metadata: Record<string, unknown> };
  chunks: CorpusChunk[];
}

export interface UserDocument {
  document_id: string;
  title: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  status: 'processing' | 'ready' | 'failed';
  error: string | null;
  page_count: number | null;
  char_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface UserDocumentDetail extends UserDocument { text: string | null }

export interface UserDocumentList { documents: UserDocument[]; total: number; limit: number; offset: number }

export interface LibrarySearchResponse {
  query: string;
  searched_documents: number;
  hits: { document_id: string; title: string; filename: string; chunk_index: number; excerpt: string; score: number; rank: number }[];
}

export interface UsageRow { event_type: string; retriever: string | null; status: string; count: number; avg_latency_ms: number | null }

export interface Dashboard {
  user: UserProfile;
  corpus: { documents: number; chunks: number; facets: { document_types: string[]; courts: string[] } };
  retrievers: Partial<Record<Retriever, RetrieverStatus>>;
  generation: { provider: string | null; model: string | null; configured: boolean };
  library: { total: number; by_status: Record<string, number>; recent: UserDocument[] };
  experiments: { total: number; recent: { experiment_id: string; name: string; status: string; created_at: string | null }[] };
  activity_last_30_days: Record<string, number>;
}

export interface AdminOverview {
  corpus_documents: number;
  corpus_chunks: number;
  experiment_runs: number;
  benchmark_runs: number;
  users: number;
  active_users: number;
  users_active_last_7_days: number;
  uploaded_documents: Record<string, number>;
  uploaded_bytes: number;
  feedback: Record<string, number>;
  usage_last_24h: UsageRow[];
  usage_last_7d: UsageRow[];
  retrievers: Partial<Record<Retriever, RetrieverStatus>>;
  ingestion: Record<string, unknown>;
  system: Record<string, string | boolean | null>;
}

export interface AdminUserList { users: UserProfile[]; total: number; limit: number; offset: number }

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'ApiError';
  }
}

// ----------------------------------------------------------------- session token

const TOKEN_KEY = 'nyayaai-token';
type Listener = () => void;
const unauthorizedListeners = new Set<Listener>();

export const tokenStore = {
  get(): string | null {
    try {
      return window.localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token: string) {
    try {
      window.localStorage.setItem(TOKEN_KEY, token);
    } catch {
      // Storage can be unavailable (private mode); the in-memory session still works.
    }
  },
  clear() {
    try {
      window.localStorage.removeItem(TOKEN_KEY);
    } catch {
      // Nothing to clear.
    }
  },
};

export function onUnauthorized(listener: Listener): () => void {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

// ------------------------------------------------------------------- transport

const transientRetryDelays = [1000, 1500, 2000, 2500, 3000, 4000, 5000, 6000, 8000, 10000, 10000, 10000];

function pause(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

/** fetch() that rides out API cold starts: retries network errors and 502/503/504 while initializing. */
export async function fetchApi(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = new URL(input instanceof Request ? input.url : input.toString(), window.location.origin);
  let lastNetworkError: TypeError | undefined;

  for (let attempt = 0; attempt <= transientRetryDelays.length; attempt += 1) {
    try {
      const response = await fetch(input, init);
      if ([502, 503, 504].includes(response.status)) {
        const body = (await response.clone().json().catch(() => null)) as { status?: string } | null;
        const retryableGateway = response.status !== 503 || !body?.status || body.status === 'initializing';
        const idempotent = !init?.method || init.method === 'GET';
        if (retryableGateway && (idempotent || body?.status === 'initializing') && attempt < transientRetryDelays.length) {
          await pause(transientRetryDelays[attempt]);
          continue;
        }
      }
      return response;
    } catch (error) {
      if (!(error instanceof TypeError)) throw error;
      lastNetworkError = error;
      if (attempt < transientRetryDelays.length) {
        await pause(transientRetryDelays[attempt]);
        continue;
      }
    }
  }

  const networkDetail = lastNetworkError?.message ? ` (${lastNetworkError.message})` : '';
  throw new Error(
    `Could not reach the NyayaAI API at ${url.origin} after several attempts${networkDetail}. Check the API service URL and deployment status.`,
  );
}

async function errorFrom(response: Response): Promise<ApiError> {
  let detail = `Request failed (${response.status})`;
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === 'string') detail = body.detail;
    else if (Array.isArray(body.detail)) {
      // FastAPI validation errors: [{loc, msg}, ...]
      detail = body.detail
        .map((item: { loc?: unknown[]; msg?: string }) => {
          const field = item.loc?.filter((part) => part !== 'body').join('.');
          return field ? `${field}: ${item.msg}` : item.msg;
        })
        .join('; ');
    }
  } catch {
    // Keep the HTTP status when a proxy returns a non-JSON error page.
  }
  return new ApiError(detail, response.status);
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  auth?: boolean;
  query?: Record<string, string | number | boolean | null | undefined>;
  headers?: Record<string, string>;
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = new URL(`${API_BASE}${path}`, window.location.origin);
  Object.entries(query ?? {}).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== '') url.searchParams.set(key, String(value));
  });
  return url.toString();
}

async function send(path: string, options: RequestOptions = {}): Promise<Response> {
  const { method = 'GET', body, auth = true, query, headers = {} } = options;
  const token = auth ? tokenStore.get() : null;
  const isForm = body instanceof FormData;
  const response = await fetchApi(buildUrl(path, query), {
    method,
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
    headers: {
      ...(body !== undefined && !isForm ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
  });
  if (!response.ok) {
    const error = await errorFrom(response);
    if (response.status === 401 && auth && token) unauthorizedListeners.forEach((listener) => listener());
    throw error;
  }
  return response;
}

async function request<T>(path: string, options?: RequestOptions): Promise<T> {
  const response = await send(path, options);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function streamAnswer(
  query: string,
  retriever: Retriever,
  onToken: (token: string) => void,
  k = 8,
): Promise<QAResponse> {
  const response = await send('/api/v1/qa/stream', {
    method: 'POST',
    body: { query, retriever, k },
    headers: { Accept: 'text/event-stream' },
  });
  if (!response.body) throw new Error('The answer stream could not be opened.');
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
    else if (event === 'error') throw new ApiError(payload.detail ?? 'Answer generation failed', 503);
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
  if (!result) throw new Error('The answer stream ended before a completed response was received.');
  return result;
}

export const api = {
  health: async (): Promise<APIHealth> => {
    const response = await fetchApi(`${API_BASE}/ready`);
    const health = (await response.json()) as APIHealth;
    if (!response.ok && health.status !== 'initializing' && health.status !== 'degraded') {
      throw new Error(health.detail ?? `Health check failed (${response.status})`);
    }
    return health;
  },

  // Authentication
  login: (username: string, password: string) =>
    request<AuthSession>('/api/v1/auth/token', { method: 'POST', body: { username, password }, auth: false }),
  register: (username: string, password: string) =>
    request<AuthSession>('/api/v1/auth/register', { method: 'POST', body: { username, password }, auth: false }),
  logout: () => request<void>('/api/v1/auth/logout', { method: 'POST' }),
  me: () => request<UserProfile>('/api/v1/auth/me'),
  updateProfile: (payload: { current_password: string; username: string; new_password?: string }) =>
    request<AuthSession>('/api/v1/auth/me', { method: 'PUT', body: payload }),

  dashboard: () => request<Dashboard>('/api/v1/dashboard'),

  // Retrieval and QA
  search: (params: SearchParams) => request<SearchResponse>('/api/v1/search', { method: 'POST', body: params }),
  compare: (query: string, k = 6, retrievers?: Retriever[]) =>
    request<CompareResponse>('/api/v1/compare', { method: 'POST', body: { query, k, retrievers } }),
  answer: (query: string, retriever: Retriever, k = 8) =>
    request<QAResponse>('/api/v1/qa', { method: 'POST', body: { query, retriever, k } }),
  streamAnswer,
  feedback: (query: string, rating: 'up' | 'down') =>
    request<{ accepted: boolean; feedback_id: string }>('/api/v1/feedback', { method: 'POST', body: { query, rating } }),

  // Corpus
  corpusDocuments: (params: { q?: string; document_type?: string; court?: string; sort?: 'id' | 'title'; limit?: number; offset?: number }) =>
    request<CorpusDocumentList>('/api/v1/documents', { query: params }),
  corpusDocument: (id: string) => request<CorpusDocument>(`/api/v1/documents/${encodeURIComponent(id)}`),

  // Private library
  libraryDocuments: (params: { q?: string; status?: string; limit?: number; offset?: number }) =>
    request<UserDocumentList>('/api/v1/library/documents', { query: params }),
  libraryDocument: (id: string) => request<UserDocumentDetail>(`/api/v1/library/documents/${encodeURIComponent(id)}`),
  uploadDocument: (file: File, title?: string) => {
    const form = new FormData();
    form.append('file', file);
    if (title?.trim()) form.append('title', title.trim());
    return request<UserDocument>('/api/v1/library/documents', { method: 'POST', body: form });
  },
  deleteDocument: (id: string) => request<void>(`/api/v1/library/documents/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  downloadDocument: async (id: string): Promise<{ blob: Blob; filename: string }> => {
    const response = await send(`/api/v1/library/documents/${encodeURIComponent(id)}/download`);
    const disposition = response.headers.get('Content-Disposition') ?? '';
    const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1];
    const plain = /filename="([^"]+)"/i.exec(disposition)?.[1];
    return { blob: await response.blob(), filename: encoded ? decodeURIComponent(encoded) : plain ?? 'document' };
  },
  searchLibrary: (query: string, k = 10) =>
    request<LibrarySearchResponse>('/api/v1/library/search', { method: 'POST', body: { query, k } }),

  // Experiments
  benchmarks: () => request<BenchmarkRun[]>('/api/v1/experiments/benchmarks'),
  experiments: (limit = 20, offset = 0) =>
    request<{ experiments: ExperimentSummary[]; total: number }>('/api/v1/experiments/runs', { query: { limit, offset } }),
  experiment: (id: string) => request<ExperimentDetail>(`/api/v1/experiments/runs/${encodeURIComponent(id)}`),
  createExperiment: (input: ExperimentInput) =>
    request<ExperimentDetail>('/api/v1/experiments/runs', { method: 'POST', body: input }),
  deleteExperiment: (id: string) =>
    request<void>(`/api/v1/experiments/runs/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  // Administration
  adminOverview: () => request<AdminOverview>('/api/v1/admin/overview'),
  adminUsers: (params: { q?: string; limit?: number; offset?: number }) =>
    request<AdminUserList>('/api/v1/admin/users', { query: params }),
  updateUser: (username: string, payload: { role?: Role; is_active?: boolean }) =>
    request<UserProfile>(`/api/v1/admin/users/${encodeURIComponent(username)}`, { method: 'PATCH', body: payload }),
};
