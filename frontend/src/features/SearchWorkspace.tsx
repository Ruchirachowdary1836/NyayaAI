import { useMutation, useQuery } from '@tanstack/react-query';
import {
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  ChevronDown,
  CircleHelp,
  Copy,
  ExternalLink,
  FileText,
  LoaderCircle,
  Search,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ErrorState, Pagination } from '../components/ui';
import { api, Hit, QAResponse, Retriever, SearchParams } from '../lib/api';
import { ENGINE_DETAILS, ENGINE_LABELS, formatMs, formatScore, judgmentMeta } from '../lib/format';

const examples = [
  'Supreme Court judgments on right to privacy',
  'Section 482 CrPC and quashing of FIRs',
  'Principles of natural justice in administrative law',
];
const PAGE_SIZE = 10;
const ENGINES: Retriever[] = ['bm25', 'dense', 'hybrid'];
type Sort = NonNullable<SearchParams['sort']>;

const REFUSAL_TEXT: Record<string, string> = {
  no_evidence: 'No relevant passages were found in the corpus.',
  insufficient_evidence: 'The model reported that the retrieved passages do not support an answer.',
  invalid_citations: 'The answer cited passages that were not provided, so it was withheld.',
  uncited_answer: 'The answer did not cite any retrieved passage, so it was withheld.',
};

function HighlightedText({ text, query }: { text: string; query: string }) {
  const terms = query.toLowerCase().match(/[\p{L}\p{N}]+/gu)?.filter((term) => term.length > 2) ?? [];
  if (!terms.length) return <>{text}</>;
  const pattern = new RegExp(`(${terms.map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'giu');
  return (
    <>
      {text.split(pattern).map((part, index) =>
        terms.includes(part.toLowerCase()) ? <mark key={index}>{part}</mark> : part,
      )}
    </>
  );
}

function SourceScores({ hit, retriever }: { hit: Hit; retriever: Retriever }) {
  return (
    <details className="source-score-details">
      <summary><CircleHelp size={13} /> Why this source?</summary>
      <div className="source-score-grid">
        {(retriever === 'bm25' || retriever === 'hybrid') && <>
          <span>BM25 score</span><strong>{formatScore(hit.source_scores.bm25)}</strong>
          <span>BM25 rank</span><strong>{hit.source_scores.bm25_rank ?? (retriever === 'bm25' ? hit.rank : '—')}</strong>
        </>}
        {(retriever === 'dense' || retriever === 'hybrid') && <>
          <span>Dense score</span><strong>{formatScore(hit.source_scores.dense)}</strong>
          <span>Dense rank</span><strong>{hit.source_scores.dense_rank ?? (retriever === 'dense' ? hit.rank : '—')}</strong>
        </>}
        {retriever === 'hybrid' && <>
          <span>Fused score</span><strong>{formatScore(hit.source_scores.fused ?? hit.score, 4)}</strong>
        </>}
      </div>
    </details>
  );
}

function ResultCard({ hit, query, retriever, position }: { hit: Hit; query: string; retriever: Retriever; position: number }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(hit.text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1300);
    } catch {
      setCopied(false);
    }
  };
  const documentLink = `/documents/${encodeURIComponent(hit.doc_id)}#${encodeURIComponent(hit.chunk_id)}`;
  const meta = judgmentMeta(hit.metadata);
  return (
    <article className="result-card" id={`result-${hit.chunk_id}`}>
      <div className="result-card-top">
        <span className="result-rank">#{String(position).padStart(2, '0')}</span>
        <span className="result-court">{String(hit.metadata.document_type ?? 'document').toUpperCase()}</span>
        {meta.slice(1).map((value) => <span className="result-year" key={value}>{value}</span>)}
        <div className="result-score"><span>{ENGINE_LABELS[retriever]} score</span><strong>{formatScore(hit.score, retriever === 'hybrid' ? 4 : 3)}</strong></div>
      </div>
      <h3><Link to={documentLink}>{hit.title}</Link></h3>
      <p className="result-excerpt"><HighlightedText text={hit.excerpt} query={query} /></p>
      <div className="result-card-bottom">
        <div className="result-meta"><FileText size={13} /> {hit.doc_id} <span>·</span> passage {hit.chunk_id.split(':').pop()}</div>
        <div className="result-actions">
          <SourceScores hit={hit} retriever={retriever} />
          <button type="button" className="text-action" onClick={copy}>{copied ? <Check size={14} /> : <Copy size={14} />}{copied ? 'Copied' : 'Copy passage'}</button>
          <Link className="text-action" to={documentLink}>Open judgment <ExternalLink size={13} /></Link>
        </div>
      </div>
    </article>
  );
}

function AnswerText({ text }: { text: string }) {
  return (
    <p className="answer-text">
      {text.split(/(\[\d+\])/g).map((part, index) =>
        /^\[\d+\]$/.test(part)
          ? <a key={index} className="citation-chip" href={`#passage-${part.slice(1, -1)}`}>{part}</a>
          : part,
      )}
    </p>
  );
}

function AnswerPanel({ result, onFeedback, feedbackSent }: { result: QAResponse; onFeedback: (rating: 'up' | 'down') => void; feedbackSent: boolean }) {
  return (
    <section className="answer-layout">
      <article className="answer-card">
        <div className="answer-heading">
          <div className="answer-icon"><Sparkles size={16} /></div>
          <div><span className="section-kicker">GROUNDED RESPONSE</span><h2>Research answer</h2></div>
          <span className={result.refused ? 'confidence-pill confidence-low' : 'confidence-pill'}>
            {result.refused ? 'No grounded answer' : `Confidence ${Math.round(result.confidence * 100)}%`}
          </span>
        </div>
        {result.refused && result.refusal_reason && (
          <div className="audit-warning"><ShieldAlert size={15} /><span>{REFUSAL_TEXT[result.refusal_reason] ?? result.refusal_reason} Review the passages directly.</span></div>
        )}
        <AnswerText text={result.answer} />
        {result.interpretation && (
          <div className="interpretation-block">
            <span className="section-kicker">INTERPRETATION · NOT DIRECTLY SOURCED</span>
            <p>{result.interpretation}</p>
          </div>
        )}
        {result.unsupported_sentences.length > 0 && (
          <div className="audit-warning"><ShieldAlert size={15} /><span>{result.unsupported_sentences.length} sentence(s) carry no source citation. Verify them before relying on them.</span></div>
        )}
        <div className="answer-feedback">
          <span>Was this useful?</span>
          <button type="button" onClick={() => onFeedback('up')} aria-label="Helpful answer" disabled={feedbackSent}><ThumbsUp size={15} /></button>
          <button type="button" onClick={() => onFeedback('down')} aria-label="Unhelpful answer" disabled={feedbackSent}><ThumbsDown size={15} /></button>
          {feedbackSent && <small>Thank you — feedback recorded.</small>}
        </div>
        <div className="answer-disclaimer"><ShieldAlert size={15} /><span>{result.disclaimer}{result.model ? ` Generated by ${result.model} (${result.provider}).` : ''}</span></div>
      </article>
      <aside className="answer-sources">
        <div className="evidence-heading"><span className="evidence-icon"><BookOpen size={16} /></span><div><strong>Passages provided to the model</strong><span>{result.passages.length} sources · {result.citations.length} cited</span></div></div>
        {result.passages.map((passage) => (
          <article id={`passage-${passage.index}`} className={`passage-card ${result.citations.includes(passage.index) ? 'passage-cited' : ''}`} key={passage.chunk_id}>
            <div className="passage-meta">
              <span>[{passage.index}]</span>
              <Link to={`/documents/${encodeURIComponent(passage.doc_id)}#${encodeURIComponent(passage.chunk_id)}`}>{passage.title} <ExternalLink size={12} /></Link>
            </div>
            <small className="passage-source">{judgmentMeta(passage.metadata).join(' · ') || passage.doc_id}</small>
            <p>{passage.text}</p>
            <div className="passage-scores"><span>Score {formatScore(passage.score)}</span><span>{passage.doc_id}</span></div>
          </article>
        ))}
      </aside>
    </section>
  );
}

export function SearchWorkspace() {
  const [params, setParams] = useSearchParams();
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, staleTime: 30_000 });
  const dashboard = useQuery({ queryKey: ['dashboard'], queryFn: api.dashboard, staleTime: 60_000 });
  const available = health.data?.available_retrievers ?? ['bm25'];

  const mode = params.get('mode') === 'ask' ? 'ask' : 'search';
  const submittedQuery = params.get('q') ?? '';
  const engineParam = params.get('engine') as Retriever | null;
  const retriever: Retriever = engineParam && ENGINES.includes(engineParam) ? engineParam : 'bm25';
  const page = Math.max(1, Number(params.get('page')) || 1);
  const documentType = params.get('type') ?? '';
  const yearFrom = params.get('from') ?? '';
  const yearTo = params.get('to') ?? '';
  const sort = (params.get('sort') as Sort | null) ?? 'relevance';

  const [query, setQuery] = useState(submittedQuery);
  const [showFilters, setShowFilters] = useState(Boolean(documentType || yearFrom || yearTo || sort !== 'relevance'));
  const [streamedAnswer, setStreamedAnswer] = useState('');
  useEffect(() => setQuery(submittedQuery), [submittedQuery]);

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    Object.entries(changes).forEach(([key, value]) => (value ? next.set(key, value) : next.delete(key)));
    setParams(next);
  };

  const yearRangeInvalid = Boolean(yearFrom && yearTo && Number(yearFrom) > Number(yearTo));
  const search = useQuery({
    queryKey: ['search', submittedQuery, retriever, page, documentType, yearFrom, yearTo, sort],
    queryFn: () => api.search({
      query: submittedQuery,
      retriever,
      k: PAGE_SIZE,
      page,
      document_type: documentType || null,
      year_from: yearFrom ? Number(yearFrom) : null,
      year_to: yearTo ? Number(yearTo) : null,
      sort,
    }),
    enabled: mode === 'search' && Boolean(submittedQuery) && !yearRangeInvalid,
    retry: false,
    staleTime: 60_000,
  });

  const answer = useMutation({
    mutationFn: ({ text, engine }: { text: string; engine: Retriever }) =>
      api.streamAnswer(text, engine, (token) => setStreamedAnswer((current) => current + token)),
  });
  const feedback = useMutation({ mutationFn: (rating: 'up' | 'down') => api.feedback(answer.data?.query ?? submittedQuery, rating) });

  const submit = (event?: FormEvent, nextQuery = query) => {
    event?.preventDefault();
    const text = nextQuery.trim();
    if (!text || answer.isPending) return;
    setQuery(text);
    update({ q: text, page: null });
    if (mode === 'ask') {
      setStreamedAnswer('');
      feedback.reset();
      answer.mutate({ text, engine: retriever });
    }
  };

  const hits = search.data?.hits ?? [];
  const loading = search.isFetching || answer.isPending;
  const types = dashboard.data?.corpus.facets.document_types ?? [];

  return (
    <div className="workspace-page">
      <div className="page-heading-row">
        <div>
          <div className="eyebrow"><span className="eyebrow-line" /> Indian case law · Research workspace</div>
          <h1>Find the law.<br /><em>Follow the evidence.</em></h1>
          <p className="heading-description">Search precedents and statutes, or ask a question answered only from retrieved source passages.</p>
          <p className="corpus-attribution">Corpus: <a href="https://doi.org/10.5281/zenodo.4063986" target="_blank" rel="noreferrer">AILA 2019 cases and statutes</a> · <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">CC BY 4.0</a></p>
          <details className="corpus-attribution-details"><summary>Dataset attribution</summary><p>AILA 2019 Precedent &amp; Statute Retrieval Task by Paheli Bhattacharya, Kripabandhu Ghosh, Saptarshi Ghosh, Arindam Pal, Parth Mehta, Arnab Bhattacharya, and Prasenjit Majumder. The documents are normalized, cleaned, and chunked for retrieval.</p></details>
        </div>
      </div>

      <section className="search-console" aria-label="Legal search">
        <div className="search-mode-tabs" role="tablist" aria-label="Research mode">
          <button type="button" className={mode === 'search' ? 'mode-tab active' : 'mode-tab'} role="tab" aria-selected={mode === 'search'} onClick={() => update({ mode: null })}><Search size={15} /> Search cases</button>
          <button type="button" className={mode === 'ask' ? 'mode-tab active' : 'mode-tab'} role="tab" aria-selected={mode === 'ask'} onClick={() => update({ mode: 'ask', page: null })}><Sparkles size={15} /> Ask a question</button>
          <span className="search-mode-note">{mode === 'search' ? 'Explore judgments and provisions' : 'Answers cite retrieved passages only'}</span>
        </div>
        <form className="search-form" onSubmit={(event) => submit(event)}>
          <Search className="search-input-icon" size={20} aria-hidden />
          <input
            aria-label={mode === 'search' ? 'Search Indian law' : 'Ask a legal research question'}
            placeholder={mode === 'search' ? 'Try a legal issue, case name or section…' : 'Ask a question about Indian law…'}
            value={query}
            maxLength={2000}
            onChange={(event) => setQuery(event.target.value)}
          />
          <label className="engine-picker"><span>ENGINE</span>
            <select aria-label="Select retrieval engine" value={retriever} onChange={(event) => update({ engine: event.target.value, page: null })}>
              {ENGINES.filter((engine) => available.includes(engine)).map((engine) => <option key={engine} value={engine}>{ENGINE_LABELS[engine]}</option>)}
            </select><ChevronDown size={14} />
          </label>
          <button className="search-submit" disabled={!query.trim() || loading} type="submit">
            {loading ? <LoaderCircle className="spin" size={17} /> : mode === 'search' ? <Search size={16} /> : <Sparkles size={16} />}
            <span>{mode === 'search' ? 'Search' : 'Ask NyayaAI'}</span><ArrowRight size={15} />
          </button>
        </form>
        <div className="example-row"><span>TRY</span>{examples.map((example) => <button type="button" key={example} onClick={() => submit(undefined, example)}>{example}<ArrowUpRight size={12} /></button>)}</div>
        <div className="engine-caption">
          <CircleHelp size={13} /> {ENGINE_DETAILS[retriever]}
          {mode === 'search' && <button type="button" className="text-action filter-toggle" aria-expanded={showFilters} onClick={() => setShowFilters((value) => !value)}><SlidersHorizontal size={13} /> Filters & sorting</button>}
        </div>
        {mode === 'search' && showFilters && (
          <div className="filter-row">
            <label>Document type
              <select value={documentType} onChange={(event) => update({ type: event.target.value || null, page: null })}>
                <option value="">All types</option>
                {types.map((type) => <option key={type} value={type}>{type}</option>)}
              </select>
            </label>
            <label>Judgment year from<input type="number" inputMode="numeric" min={1900} max={2100} value={yearFrom} onChange={(event) => update({ from: event.target.value || null, page: null })} /></label>
            <label>to<input type="number" inputMode="numeric" min={1900} max={2100} value={yearTo} onChange={(event) => update({ to: event.target.value || null, page: null })} /></label>
            <label>Sort by
              <select value={sort} onChange={(event) => update({ sort: event.target.value === 'relevance' ? null : event.target.value, page: null })}>
                <option value="relevance">Relevance</option>
                <option value="newest">Newest judgment</option>
                <option value="oldest">Oldest judgment</option>
                <option value="title">Title (A–Z)</option>
              </select>
            </label>
            {(documentType || yearFrom || yearTo || sort !== 'relevance') && <button type="button" className="text-action" onClick={() => update({ type: null, from: null, to: null, sort: null, page: null })}>Clear filters</button>}
            {yearRangeInvalid && <span className="auth-error" role="alert">The start year must not be after the end year.</span>}
            {(yearFrom || yearTo) && <span className="field-hint">Year filters apply to judgments; statutes have no judgment date.</span>}
          </div>
        )}
        {available.length < ENGINES.length && <p className="comparison-note">Some retrieval engines are disabled on this deployment by its configuration.</p>}
      </section>

      {mode === 'search' && search.isError && <ErrorState title="Search couldn’t be completed" message={search.error.message} onRetry={() => void search.refetch()} />}
      {mode === 'ask' && answer.isError && <ErrorState title="Answer generation is unavailable" message={answer.error.message} onRetry={() => submit(undefined, submittedQuery)} />}
      {mode === 'ask' && answer.isPending && (
        <section className="answer-streaming-panel" aria-live="polite">
          <span className="streaming-indicator"><LoaderCircle className="spin" size={14} /> {streamedAnswer ? 'ANSWER STREAMING' : 'RETRIEVING PASSAGES AND GENERATING'}</span>
          {streamedAnswer && <p>{streamedAnswer}<i className="streaming-caret" /></p>}
          <small>Citations are checked against the retrieved passages when generation completes.</small>
        </section>
      )}

      {!submittedQuery && (
        <section className="welcome-grid">
          <div className="welcome-card welcome-primary">
            <span className="welcome-kicker"><Sparkles size={14} /> HOW IT WORKS</span>
            <h2>One question.<br />Evidence you can inspect.</h2>
            <p>Search the licensed legal corpus and follow each result back to its full judgment, court, date, and case number.</p>
          </div>
          <div className="welcome-card trust-card"><div className="trust-icon"><ShieldCheck size={19} /></div><span className="welcome-kicker">BUILT FOR CAREFUL RESEARCH</span><h3>Evidence, not assumptions.</h3><p>Answers cite numbered passages. Missing or weak evidence is shown plainly instead of filled in.</p><Link to="/compare">Explore the retrieval methods <ArrowRight size={14} /></Link></div>
        </section>
      )}

      {mode === 'search' && submittedQuery && (search.data || search.isFetching) && (
        <section className="results-layout" aria-live="polite">
          <div className="results-main">
            <div className="results-header">
              <div><span className="section-kicker">SEARCH RESULTS</span><h2>For “{submittedQuery}”</h2></div>
              {search.data && <span className="result-count">{search.data.total}{search.data.total_is_capped ? '+' : ''} matching documents · {formatMs(search.data.latency_ms)}</span>}
            </div>
            {search.isFetching && <div className="loading-card" role="status"><LoaderCircle className="spin" /> Searching the legal corpus…</div>}
            {search.data && !search.data.corpus_available && <div className="empty-corpus"><BookOpen size={20} /><div><strong>No legal documents are indexed</strong><p>Run the ingestion pipeline described in the README to add an authorized corpus.</p></div></div>}
            {search.data?.corpus_available && !hits.length && !search.isFetching && <div className="empty-corpus"><Search size={20} /><div><strong>No passages matched this query</strong><p>Try a broader legal concept, a case name, a statute section number, or remove filters.</p></div></div>}
            {!search.isFetching && hits.map((hit, index) => <ResultCard key={hit.chunk_id} hit={hit} query={submittedQuery} retriever={retriever} position={(page - 1) * PAGE_SIZE + index + 1} />)}
            {search.data && <Pagination page={page} pageSize={PAGE_SIZE} total={search.data.total} capped={search.data.total_is_capped} onPage={(next) => { update({ page: next > 1 ? String(next) : null }); window.scrollTo({ top: 0 }); }} />}
          </div>
          <aside className="evidence-aside">
            <div className="evidence-heading"><span className="evidence-icon"><FileText size={16} /></span><div><strong>Evidence panel</strong><span>Source attribution</span></div><span className="live-dot" /></div>
            <div className="evidence-summary"><span className="evidence-summary-label">ACTIVE RETRIEVER</span><strong>{ENGINE_LABELS[retriever]}</strong><p>{ENGINE_DETAILS[retriever]}</p></div>
            {hits.slice(0, 5).map((hit, index) => <a className="evidence-item" href={`#result-${hit.chunk_id}`} key={hit.chunk_id}><span className="evidence-rank">{String((page - 1) * PAGE_SIZE + index + 1).padStart(2, '0')}</span><span><strong>{hit.title}</strong><small>{judgmentMeta(hit.metadata).slice(1).join(' · ') || hit.doc_id}</small></span><ArrowUpRight size={14} /></a>)}
            {!hits.length && <p className="evidence-empty">{search.isFetching ? 'Gathering source passages…' : 'Run a search to see source passages.'}</p>}
            <div className="evidence-footnote"><ShieldCheck size={14} /><span>One passage per document is shown; open a judgment to read every indexed passage.</span></div>
          </aside>
        </section>
      )}

      {mode === 'ask' && answer.data && !answer.isPending && (
        <AnswerPanel result={answer.data} onFeedback={(rating) => feedback.mutate(rating)} feedbackSent={feedback.isSuccess} />
      )}
      {feedback.isError && <ErrorState title="Feedback was not saved" message={feedback.error.message} />}
    </div>
  );
}
