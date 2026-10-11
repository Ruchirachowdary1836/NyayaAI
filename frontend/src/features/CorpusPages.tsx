import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ArrowLeft, ArrowRight, BookOpenText, Database, Search, ShieldCheck } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom';
import { EmptyState, ErrorState, LoadingCard, PageTitle, Pagination } from '../components/ui';
import { api } from '../lib/api';
import { formatDate, judgmentMeta } from '../lib/format';

const PAGE_SIZE = 20;

export function DocumentLibraryPage() {
  const [params, setParams] = useSearchParams();
  const q = params.get('q') ?? '';
  const type = params.get('type') ?? '';
  const page = Math.max(1, Number(params.get('page')) || 1);
  const [filter, setFilter] = useState(q);
  // Sync from the URL (back/forward navigation) without clobbering in-progress typing.
  useEffect(() => setFilter((current) => (current.trim() === q ? current : q)), [q]);
  // Debounce the text filter so typing does not issue a request per keystroke.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (filter.trim() !== q) {
        const next = new URLSearchParams(params);
        if (filter.trim()) next.set('q', filter.trim());
        else next.delete('q');
        next.delete('page');
        setParams(next, { replace: true });
      }
    }, 300);
    return () => window.clearTimeout(timer);
  }, [filter, q, params, setParams]);

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['corpus', q, type, page],
    queryFn: () => api.corpusDocuments({ q, document_type: type || undefined, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }),
    placeholderData: keepPreviousData,
  });
  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== 'page') next.delete('page');
    setParams(next);
  };
  return (
    <div className="subpage">
      <PageTitle eyebrow="LEGAL CORPUS" title="The corpus, in context." description="Browse the attributed judgments and statutes that power retrieval. Open a document to read its full text, metadata, and indexed passages." />
      <div className="library-toolbar">
        <div><Database size={16} /><strong>{isLoading ? '…' : isError ? '—' : data?.total.toLocaleString()}</strong><span>{isError ? 'document count unavailable' : q || type ? 'matching documents' : 'indexed documents'}</span></div>
        <label className="toolbar-select"><span className="sr-only">Document type</span>
          <select aria-label="Filter by document type" value={type} onChange={(event) => setParam('type', event.target.value || null)}>
            <option value="">All types</option>
            {data?.facets.document_types.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <label><Search size={15} /><input aria-label="Filter documents" placeholder="Filter by title, ID, or text…" value={filter} maxLength={200} onChange={(event) => setFilter(event.target.value)} /></label>
      </div>
      {isError && <ErrorState message={error.message} onRetry={() => void refetch()} />}
      {isLoading && <LoadingCard label="Loading the source library…" />}
      {!isLoading && !isError && data?.documents.length === 0 && (
        <EmptyState icon={<BookOpenText size={23} />} title={q || type ? 'No documents match these filters.' : 'No documents in the index yet.'}>
          <p>{q || type ? 'Try a different title, document ID, or type.' : 'Run the ingestion pipeline described in the README to add an authorized corpus.'}</p>
        </EmptyState>
      )}
      <div className={`document-list ${isFetching ? 'is-refreshing' : ''}`}>
        {data?.documents.map((document) => (
          <Link className="document-list-item" key={document.doc_id} to={`/documents/${encodeURIComponent(document.doc_id)}`}>
            <span className="document-list-icon"><BookOpenText size={17} /></span>
            <span className="document-list-copy">
              <strong>{document.title}</strong>
              <small>{[document.doc_id, (document.document_type ?? document.source).toUpperCase(), ...judgmentMeta(document.metadata)].join(' · ')}</small>
              <p>{document.excerpt}</p>
            </span>
            <ArrowRight size={16} />
          </Link>
        ))}
      </div>
      {data && <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onPage={(next) => setParam('page', next > 1 ? String(next) : null)} />}
    </div>
  );
}

const METADATA_LABELS: [string, string][] = [
  ['document_type', 'Type'],
  ['court', 'Court'],
  ['judgment_date', 'Judgment date'],
  ['case_number', 'Case number'],
  ['source_name', 'Source'],
  ['license', 'Licence'],
];

export function DocumentPage() {
  const { documentId = '' } = useParams();
  const { hash } = useLocation();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['document', documentId],
    queryFn: () => api.corpusDocument(documentId),
  });
  useEffect(() => {
    if (!data || !hash) return;
    const target = document.getElementById(`chunk-${decodeURIComponent(hash.slice(1))}`);
    target?.scrollIntoView({ block: 'start' });
    target?.classList.add('passage-highlight');
  }, [data, hash]);
  const metadata = data?.document.metadata ?? {};
  return (
    <div className="subpage document-page">
      <Link className="back-link" to="/documents"><ArrowLeft size={15} /> Back to the legal corpus</Link>
      {isError && <ErrorState message={error.message} />}
      {isLoading && <LoadingCard label="Opening source document…" />}
      {data && (
        <>
          <PageTitle eyebrow={`SOURCE DOCUMENT · ${data.document.doc_id}`} title={String(metadata.title ?? data.document.doc_id)} description={`${data.chunks.length} indexed passages · ${data.document.text.length.toLocaleString()} characters`} />
          <dl className="metadata-grid">
            {METADATA_LABELS.filter(([key]) => metadata[key]).map(([key, label]) => (
              <div key={key}><dt>{label}</dt><dd>{key === 'judgment_date' ? formatDate(String(metadata[key])) : String(metadata[key])}</dd></div>
            ))}
          </dl>
          <div className="research-note"><ShieldCheck size={16} /><p>{String(metadata.attribution ?? metadata.source_name ?? 'Source attribution unavailable')}. Licence: {String(metadata.license ?? 'not specified')}. {typeof metadata.source_url === 'string' && <a href={metadata.source_url} target="_blank" rel="noreferrer">View source record</a>}</p></div>
          <section className="document-reader"><div className="document-reader-heading"><BookOpenText size={17} /><span>Full source text</span><span>{data.document.doc_id}</span></div><article>{data.document.text}</article></section>
          <section className="document-chunks">
            <span className="section-kicker">INDEXED EVIDENCE</span><h2>Retrieved passage boundaries</h2>
            {data.chunks.map((chunk) => (
              <article className="passage-card" id={`chunk-${chunk.chunk_id}`} key={chunk.chunk_id}>
                <div className="passage-meta"><span>{chunk.chunk_id}</span><span>characters {chunk.start_char}–{chunk.end_char} · {chunk.token_count} tokens</span></div>
                <p>{chunk.text}</p>
              </article>
            ))}
          </section>
        </>
      )}
    </div>
  );
}
