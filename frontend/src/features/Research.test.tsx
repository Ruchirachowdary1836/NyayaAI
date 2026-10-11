import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { json, mockApi, renderApp } from '../test/harness';
import { parseQueries } from './ExperimentsPage';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

const hit = {
  doc_id: 'C12',
  chunk_id: 'C12:0',
  title: 'State v Example',
  text: 'Section 482 CrPC permits the High Court to exercise inherent powers.',
  excerpt: 'Section 482 CrPC permits the High Court to exercise inherent powers.',
  score: 7.25,
  rank: 1,
  source_scores: { bm25: 7.25 },
  metadata: { court: 'Supreme Court of India', judgment_date: '1990-11-13', case_number: 'Cr.A. No. 716 of 1979', document_type: 'judgment' },
};

function searchResponse(body: Record<string, unknown>) {
  return json({
    query: body.query,
    retriever: body.retriever,
    hits: [hit],
    corpus_available: true,
    page: body.page ?? 1,
    page_size: body.k,
    total: 1,
    total_is_capped: false,
    latency_ms: 3.2,
    filters: {},
  });
}

describe('research workspace', () => {
  it('searches with the entered query and shows traceable judgment metadata', async () => {
    const { calls } = mockApi((url, init) => url.pathname === '/api/v1/search' ? searchResponse(JSON.parse(String(init.body))) : undefined);
    renderApp('/search');
    fireEvent.change(await screen.findByLabelText('Search Indian law'), { target: { value: 'Section 482 CrPC' } });
    fireEvent.click(screen.getByRole('button', { name: /^search$/i }));

    const result = await screen.findByRole('link', { name: 'State v Example' });
    expect(result).toHaveAttribute('href', '/documents/C12#C12%3A0');
    expect(screen.getByText('Cr.A. No. 716 of 1979')).toBeInTheDocument();
    const request = calls.find((call) => call.url.pathname === '/api/v1/search');
    expect(JSON.parse(String(request?.init.body))).toMatchObject({ query: 'Section 482 CrPC', retriever: 'bm25', page: 1 });
    expect((request?.init.headers as Record<string, string>).Authorization).toBe('Bearer test-token');
  });

  it('sends filters and sorting from the URL to the API', async () => {
    const { calls } = mockApi((url, init) => url.pathname === '/api/v1/search' ? searchResponse(JSON.parse(String(init.body))) : undefined);
    renderApp('/search?q=murder&type=judgment&from=2010&to=2012&sort=newest&page=2');
    await screen.findByRole('link', { name: 'State v Example' });
    const body = JSON.parse(String(calls.find((call) => call.url.pathname === '/api/v1/search')?.init.body));
    expect(body).toMatchObject({ query: 'murder', document_type: 'judgment', year_from: 2010, year_to: 2012, sort: 'newest', page: 2 });
  });

  it('shows the API error when an engine is unavailable', async () => {
    mockApi((url) => url.pathname === '/api/v1/search' ? json({ detail: 'Dense retrieval is unavailable: model could not be loaded.' }, 503) : undefined);
    renderApp('/search?q=privacy&engine=dense');
    expect(await screen.findByText(/Dense retrieval is unavailable/)).toBeInTheDocument();
  });

  it('renders a grounded answer with citations linked to passages and a separate interpretation', async () => {
    const stream = [
      'event: token\ndata: {"token": "Inherent powers apply [1]."}\n\n',
      `event: complete\ndata: ${JSON.stringify({
        query: 'q', answer: 'Inherent powers apply [1].', citations: [1], invalid_citations: [], unsupported_sentences: [],
        interpretation: 'This suggests broad discretion.', passages: [{ index: 1, doc_id: 'C12', chunk_id: 'C12:0', title: 'State v Example', text: hit.text, score: 7.25, source_scores: {}, metadata: hit.metadata }],
        confidence: 0.5, disclaimer: 'For informational purposes only; this is not legal advice.', refused: false, refusal_reason: null, model: 'test-model', provider: 'ollama',
      })}\n\n`,
    ].join('');
    const { calls } = mockApi((url) => url.pathname === '/api/v1/qa/stream' ? new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } }) : undefined);
    renderApp('/search?mode=ask');
    fireEvent.change(await screen.findByLabelText('Ask a legal research question'), { target: { value: 'What are inherent powers?' } });
    fireEvent.click(screen.getByRole('button', { name: /ask nyayaai/i }));

    expect(await screen.findByRole('link', { name: '[1]' })).toHaveAttribute('href', '#passage-1');
    expect(screen.getByText('This suggests broad discretion.')).toBeInTheDocument();
    expect(screen.getByText(/INTERPRETATION · NOT DIRECTLY SOURCED/)).toBeInTheDocument();
    const request = calls.find((call) => call.url.pathname === '/api/v1/qa/stream');
    expect(request?.init.method).toBe('POST');
    expect(request?.url.search).toBe('');
  });
});

describe('document library', () => {
  it('lists private documents and rejects oversized files before upload', async () => {
    const { calls } = mockApi(
      (url, init) => url.pathname === '/api/v1/library/documents' && (init.method ?? 'GET') === 'GET'
        ? json({ documents: [{ document_id: 'd1', title: 'Lease agreement', filename: 'lease.pdf', content_type: 'application/pdf', size_bytes: 2048, sha256: 'x', status: 'failed', error: 'No extractable text was found.', page_count: 1, char_count: 0, created_at: null, updated_at: null }], total: 1, limit: 20, offset: 0 })
        : undefined,
    );
    renderApp('/library');
    const row = (await screen.findByRole('link', { name: 'Lease agreement' })).closest('tr') as HTMLElement;
    expect(within(row).getByText('No extractable text was found.')).toBeInTheDocument();

    const big = new File([new Uint8Array(6 * 1024 * 1024)], 'big.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByText(/Choose a PDF/).parentElement?.querySelector('input') as HTMLInputElement, { target: { files: [big] } });
    expect(await screen.findByText('Files must be 5 MB or smaller.')).toBeInTheDocument();
    expect(calls.some((call) => call.init.method === 'POST')).toBe(false);
  });

  it('corpus library shows a loading state, not a zero count, while loading', async () => {
    let release: (value: Response) => void = () => undefined;
    mockApi((url) => url.pathname === '/api/v1/documents' ? new Promise<Response>((resolve) => { release = resolve; }) : undefined);
    renderApp('/documents');
    expect(await screen.findByText('Loading the source library…')).toBeInTheDocument();
    expect(screen.queryByText('0')).not.toBeInTheDocument();
    release(json({ documents: [], total: 0, limit: 20, offset: 0, facets: { document_types: [], courts: [] } }));
    expect(await screen.findByText('No documents in the index yet.')).toBeInTheDocument();
  });
});

describe('experiments', () => {
  it('parses queries and optional relevance judgments', () => {
    expect(parseQueries('first query || C1, C2\n\n second query \nthird||S5')).toEqual([
      { query: 'first query', relevant_doc_ids: ['C1', 'C2'] },
      { query: 'second query', relevant_doc_ids: [] },
      { query: 'third', relevant_doc_ids: ['S5'] },
    ]);
  });

  it('submits a new experiment to the API', async () => {
    const { calls } = mockApi(
      (url) => url.pathname === '/api/v1/experiments/benchmarks' ? json([]) : undefined,
      (url, init) => url.pathname === '/api/v1/experiments/runs' && init.method === 'POST'
        ? json({ detail: 'Not enabled on this deployment: dense.' }, 422)
        : undefined,
      (url) => url.pathname === '/api/v1/experiments/runs' ? json({ experiments: [], total: 0 }) : undefined,
    );
    renderApp('/experiments');
    fireEvent.change(await screen.findByLabelText('Name'), { target: { value: 'Trial' } });
    fireEvent.change(screen.getByLabelText(/Queries/), { target: { value: 'murder appeal || C1' } });
    fireEvent.click(screen.getByRole('button', { name: /run and save/i }));
    expect(await screen.findByText('Not enabled on this deployment: dense.')).toBeInTheDocument();
    await waitFor(() => {
      const body = JSON.parse(String(calls.find((call) => call.init.method === 'POST')?.init.body));
      expect(body).toEqual({ name: 'Trial', retrievers: ['bm25'], k: 10, queries: [{ query: 'murder appeal', relevant_doc_ids: ['C1'] }] });
    });
  });
});

describe('engine status labels', () => {
  it('shows index build progress and retry state', async () => {
    const { engineStateLabel } = await import('./DashboardPage');
    expect(engineStateLabel({ state: 'building', progress: { embedded: 12089, total: 24178 } })).toBe('Building index · 50%');
    expect(engineStateLabel({ state: 'building' })).toBe('Building index…');
    expect(engineStateLabel({ state: 'failed', retrying: true })).toBe('Retrying soon');
    expect(engineStateLabel({ state: 'failed' })).toBe('Unavailable');
    expect(engineStateLabel(undefined)).toBe('Unknown');
  });
});
