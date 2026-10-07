import '@testing-library/jest-dom/vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../lib/api';
import { SearchWorkspace } from './SearchWorkspace';

vi.mock('../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/api')>();
  return {
    ...actual,
    api: {
      ...actual.api,
      health: vi.fn().mockResolvedValue({
        status: 'ready',
        available_retrievers: ['bm25'],
      }),
      search: vi.fn(),
      answer: vi.fn(),
      streamAnswer: vi.fn(),
      feedback: vi.fn(),
    },
  };
});

function renderWorkspace() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}><SearchWorkspace /></QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('research workspace', () => {
  afterEach(cleanup);
  beforeEach(() => vi.clearAllMocks());

  it('searches with the query entered and shows source evidence', async () => {
    vi.mocked(api.search).mockResolvedValue({
      query: 'Section 482 CrPC',
      retriever: 'hybrid',
      corpus_available: true,
      hits: [{
        doc_id: 'judgment-1',
        chunk_id: 'judgment-1:0',
        text: 'Section 482 CrPC passage.',
        score: 0.04,
        rank: 1,
        source_scores: { fused: 0.04, bm25: 2.2 },
        metadata: { court: 'Supreme Court', year: 2020 },
      }],
    });

    const { container } = renderWorkspace();
    fireEvent.change(screen.getByRole('textbox', { name: 'Search Indian law' }), {
      target: { value: 'Section 482 CrPC' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Search$/ }));

    await waitFor(() => expect(api.search).toHaveBeenCalledWith('Section 482 CrPC', 'bm25'));
    await waitFor(() =>
      expect(container.querySelector('.result-excerpt')).toHaveTextContent('Section 482 CrPC passage.'),
    );
    expect(screen.getByText('Supreme Court')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'AILA 2019 cases and statutes' })).toHaveAttribute(
      'href',
      'https://doi.org/10.5281/zenodo.4063986',
    );
  });

  it('switches to grounded answer mode and displays its disclaimer', async () => {
    vi.mocked(api.streamAnswer).mockImplementation(async (_query, _retriever, onToken) => {
      onToken('A supported statement [1].');
      return {
      query: 'legal query',
      answer: 'A supported statement [1].',
      citations: [1],
      invalid_citations: [],
      unsupported_sentences: [],
      passages: [{ index: 1, doc_id: 'case-1', chunk_id: 'case-1:0', text: 'Supporting passage.', score: 0.02, source_scores: {} }],
      confidence: 0.75,
      disclaimer: 'Not legal advice.',
      refused: false,
      };
    });

    const { container } = renderWorkspace();
    fireEvent.click(screen.getByRole('tab', { name: /Ask a question/ }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Search Indian law' }), {
      target: { value: 'legal query' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Ask NyayaAI/ }));

    await waitFor(() =>
      expect(api.streamAnswer).toHaveBeenCalledWith('legal query', 'bm25', expect.any(Function)),
    );
    await waitFor(() =>
      expect(container.querySelector('.answer-text')).toHaveTextContent('A supported statement'),
    );
    expect(screen.getByText('Not legal advice.')).toBeInTheDocument();
  });
});
