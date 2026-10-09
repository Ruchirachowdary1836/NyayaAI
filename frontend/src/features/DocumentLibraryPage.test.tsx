import '@testing-library/jest-dom/vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DocumentLibraryPage } from './ResearchPages';

const { fetchApi } = vi.hoisted(() => ({ fetchApi: vi.fn() }));

vi.mock('../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/api')>();
  return { ...actual, fetchApi };
});

function renderLibrary() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <DocumentLibraryPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('document library availability', () => {
  afterEach(cleanup);
  beforeEach(() => vi.clearAllMocks());

  it('does not present a zero document count while the library is loading', () => {
    vi.mocked(fetchApi).mockReturnValue(new Promise(() => {}));
    renderLibrary();

    expect(screen.getByText('…')).toBeInTheDocument();
    expect(screen.queryByText('0')).not.toBeInTheDocument();
  });

  it('reports an unavailable count instead of an empty corpus after a fetch error', async () => {
    vi.mocked(fetchApi).mockRejectedValue(new Error('API unavailable'));
    renderLibrary();

    expect(await screen.findByText('document count unavailable')).toBeInTheDocument();
    expect(screen.queryByText('0')).not.toBeInTheDocument();
    expect(screen.queryByText('No documents in the index yet.')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry loading documents' })).toBeInTheDocument();
    await waitFor(() => expect(fetchApi).toHaveBeenCalledTimes(1));
  });
});
