import { useMutation, useQuery } from '@tanstack/react-query';
import {
  ArrowDownRight,
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
  Scale,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
} from 'lucide-react';
import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { api, Hit, Retriever } from '../lib/api';

const examples = [
  'Supreme Court judgments on right to privacy',
  'Section 482 CrPC and quashing of FIRs',
  'Principles of natural justice in administrative law',
];

const engineOptions: { value: Retriever; label: string; detail: string }[] = [
  { value: 'hybrid', label: 'Hybrid', detail: 'Rank fusion of lexical and semantic evidence' },
  { value: 'bm25', label: 'BM25', detail: 'Lexical match for exact terms and provisions' },
  { value: 'dense', label: 'Dense', detail: 'Semantic similarity from a sentence-embedding model' },
];

function formatScore(score: number | null | undefined): string {
  return typeof score === 'number' ? score.toFixed(3) : '—';
}

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
          <span>Dense rank</span><strong>{hit.source_scores.dense_rank ?? '—'}</strong>
        </>}
        {retriever === 'hybrid' && <>
          <span>Hybrid score</span><strong>{formatScore(hit.source_scores.fused ?? hit.score)}</strong>
        </>}
      </div>
    </details>
  );
}

function ResultCard({ hit, query, retriever }: { hit: Hit; query: string; retriever: Retriever }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(hit.text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1300);
  };
  const source = String(hit.metadata.citation ?? hit.metadata.title ?? hit.doc_id);
  return (
    <article className="result-card" id={hit.chunk_id}>
      <div className="result-card-top">
        <span className="result-rank">#{String(hit.rank).padStart(2, '0')}</span>
        <span className="result-court">{String(hit.metadata.court ?? 'Case document')}</span>
        <span className="result-year">{String(hit.metadata.year ?? 'Source')}</span>
        <div className="result-score"><span>Relevance</span><strong>{Math.round(Math.max(0, Math.min(1, hit.score)) * 100)}%</strong></div>
      </div>
      <h3><Link to={`/documents/${encodeURIComponent(hit.doc_id)}`}>{source}</Link></h3>
      <p className="result-excerpt"><HighlightedText text={hit.text} query={query} /></p>
      <div className="result-card-bottom">
        <div className="result-meta"><FileText size={13} /> {hit.doc_id} <span>·</span> {hit.chunk_id}</div>
        <div className="result-actions">
          <SourceScores hit={hit} retriever={retriever} />
          <button className="text-action" onClick={copy}>{copied ? <Check size={14} /> : <Copy size={14} />}{copied ? 'Copied' : 'Copy excerpt'}</button>
          <Link className="text-action" to={`/documents/${encodeURIComponent(hit.doc_id)}`}>Open <ExternalLink size={13} /></Link>
        </div>
      </div>
    </article>
  );
}

export function SearchWorkspace() {
  const health = useQuery({ queryKey: ['health'], queryFn: api.health });
  const availableEngines = engineOptions.filter((engine) =>
    (health.data?.available_retrievers ?? ['bm25']).includes(engine.value),
  );
  const [query, setQuery] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [mode, setMode] = useState<'search' | 'ask'>('search');
  const [retriever, setRetriever] = useState<Retriever>('bm25');
  const selectedRetriever = availableEngines.some((engine) => engine.value === retriever)
    ? retriever
    : 'bm25';
  const [streamedAnswer, setStreamedAnswer] = useState('');
  const search = useMutation({
    mutationFn: ({ text, engine }: { text: string; engine: Retriever }) => api.search(text, engine),
  });
  const answer = useMutation({
    mutationFn: ({ text, engine }: { text: string; engine: Retriever }) =>
      api.streamAnswer(text, engine, (token) => setStreamedAnswer((current) => current + token)),
  });
  const feedback = useMutation({ mutationFn: (rating: 'up' | 'down') => api.feedback(submittedQuery, rating) });
  const loading = search.isPending || answer.isPending;

  const submit = (event?: FormEvent, nextQuery = query) => {
    event?.preventDefault();
    if (!nextQuery.trim() || loading) return;
    setQuery(nextQuery);
    setSubmittedQuery(nextQuery.trim());
    if (mode === 'search') search.mutate({ text: nextQuery.trim(), engine: selectedRetriever });
    else {
      setStreamedAnswer('');
      answer.mutate({ text: nextQuery.trim(), engine: selectedRetriever });
    }
  };

  const searchResult = search.data;
  const qaResult = answer.data;
  const hits = searchResult?.hits ?? [];

  return (
    <div className="workspace-page">
      <div className="page-heading-row">
        <div>
          <div className="eyebrow"><span className="eyebrow-line" /> Indian case law · Research workspace</div>
          <h1>Find the law.<br /><em>Follow the evidence.</em></h1>
          <p className="heading-description">Search precedents and statutes, or ask a question grounded in source passages.</p>
          <p className="corpus-attribution">Corpus: <a href="https://doi.org/10.5281/zenodo.4063986" target="_blank" rel="noreferrer">AILA 2019 cases and statutes</a> · <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">CC BY 4.0</a> · BM25 works without a hosted language model.</p>
          <details className="corpus-attribution-details"><summary>Dataset attribution</summary><p>AILA 2019 Precedent &amp; Statute Retrieval Task by Paheli Bhattacharya, Kripabandhu Ghosh, Saptarshi Ghosh, Arindam Pal, Parth Mehta, Arnab Bhattacharya, and Prasenjit Majumder. <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">CC BY 4.0</a>. The documents are normalized, cleaned, and chunked for retrieval.</p></details>
        </div>
        <div className="heading-metric"><span className="metric-orbit"><Scale size={21} /></span><span>Research built on<br /><strong>transparent evidence</strong></span></div>
      </div>

      <section className="search-console" aria-label="Legal search">
        <div className="search-mode-tabs" role="tablist" aria-label="Research mode">
          <button className={mode === 'search' ? 'mode-tab active' : 'mode-tab'} role="tab" aria-selected={mode === 'search'} onClick={() => setMode('search')}><Search size={15} /> Search cases</button>
          <button className={mode === 'ask' ? 'mode-tab active' : 'mode-tab'} role="tab" aria-selected={mode === 'ask'} onClick={() => setMode('ask')}><Sparkles size={15} /> Ask a question</button>
          <span className="search-mode-note">{mode === 'search' ? 'Explore judgments and provisions' : 'Answers are grounded in retrieved passages'}</span>
        </div>
        <form className="search-form" onSubmit={(event) => submit(event)}>
          <Search className="search-input-icon" size={20} />
          <input
            aria-label="Search Indian law"
            placeholder="Try a legal issue, case name or section…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <label className="engine-picker"><span>ENGINE</span>
          <select aria-label="Select retrieval engine" value={selectedRetriever} onChange={(event) => setRetriever(event.target.value as Retriever)}>
            {availableEngines.map((engine) => <option key={engine.value} value={engine.value}>{engine.label}</option>)}
            </select><ChevronDown size={14} />
          </label>
          <button className="search-submit" disabled={!query.trim() || loading} type="submit">
            {loading ? <LoaderCircle className="spin" size={17} /> : mode === 'search' ? <Search size={16} /> : <Sparkles size={16} />}
            <span>{mode === 'search' ? 'Search' : 'Ask NyayaAI'}</span><ArrowRight size={15} />
          </button>
        </form>
        <div className="example-row"><span>TRY</span>{examples.map((example) => <button key={example} onClick={() => submit(undefined, example)}>{example}<ArrowUpRight size={12} /></button>)}</div>
        <div className="engine-caption"><CircleHelp size={13} /> {engineOptions.find((engine) => engine.value === selectedRetriever)?.detail}
          <span className="engine-explainer">{selectedRetriever === 'hybrid' ? 'BM25 + Dense' : selectedRetriever === 'bm25' ? 'Term matching' : 'Semantic matching'}</span>
        </div>
        {availableEngines.length < engineOptions.length && <p className="comparison-note">Dense and hybrid are disabled on this deployment to keep retrieval within its configured memory budget.</p>}
      </section>

      {search.isError && <div className="error-banner" role="alert"><ShieldAlert size={17} /><div><strong>Search couldn’t be completed</strong><span>{search.error.message}</span></div></div>}
      {answer.isError && <div className="error-banner" role="alert"><ShieldAlert size={17} /><div><strong>Answer generation is unavailable</strong><span>{answer.error.message}. Configure the selected {health.data?.generation_provider ?? 'AI'} provider in the API service before NyayaAI can generate answers.</span></div></div>}
      {answer.isPending && streamedAnswer && <section className="answer-streaming-panel" aria-live="polite"><span className="streaming-indicator"><LoaderCircle className="spin" size={14} /> ANSWER STREAMING</span><p>{streamedAnswer}<i className="streaming-caret" /></p><small>Checking passage citations when generation completes…</small></section>}

      {!submittedQuery && (
        <section className="welcome-grid">
          <div className="welcome-card welcome-primary">
            <span className="welcome-kicker"><Sparkles size={14} /> HOW IT WORKS</span>
            <h2>One question.<br />Evidence you can inspect.</h2>
            <p>Search the licensed legal corpus and follow each result back to its source passage.</p>
            <div className="retriever-strip">{availableEngines.map((engine) => <span key={engine.value}><i className={`legend-dot dot-${engine.value === 'bm25' ? 'navy' : engine.value === 'dense' ? 'sage' : 'gold'}`} /> {engine.label}</span>)}</div>
          </div>
          <div className="welcome-card trust-card"><div className="trust-icon"><ShieldCheck size={19} /></div><span className="welcome-kicker">BUILT FOR CAREFUL RESEARCH</span><h3>Evidence, not assumptions.</h3><p>Answers cite numbered passages. Missing or weak evidence is shown plainly instead of filled in.</p><Link to="/compare">Explore the retrieval methods <ArrowRight size={14} /></Link></div>
        </section>
      )}

      {(searchResult || search.isPending) && (
        <section className="results-layout" aria-live="polite">
          <div className="results-main">
            <div className="results-header">
              <div><span className="section-kicker">SEARCH RESULTS</span><h2>For “{searchResult?.query ?? submittedQuery}”</h2></div>
              {searchResult && <span className="result-count">{searchResult.hits.length} passages</span>}
            </div>
            {search.isPending && <div className="loading-card"><LoaderCircle className="spin" /> Searching the legal corpus…</div>}
            {searchResult && !searchResult.corpus_available && <div className="empty-corpus"><BookOpen size={20} /><div><strong>No legal documents are indexed</strong><p>For local development, add an authorized dataset under <code>data/raw/</code>, configure <code>configs/data.yaml</code>, and run <code>make ingest</code>. The hosted deployment includes the attributed AILA 2019 corpus.</p></div></div>}
            {searchResult?.corpus_available && !hits.length && <div className="empty-corpus"><Search size={20} /><div><strong>No passages matched this query</strong><p>Try a broader legal concept, a case name, or a statute section number.</p></div></div>}
            {hits.map((hit) => <ResultCard key={hit.chunk_id} hit={hit} query={submittedQuery} retriever={selectedRetriever} />)}
          </div>
          <aside className="evidence-aside">
            <div className="evidence-heading"><span className="evidence-icon"><FileText size={16} /></span><div><strong>Evidence panel</strong><span>Source attribution</span></div><span className="live-dot" /></div>
            <div className="evidence-summary"><span className="evidence-summary-label">ACTIVE RETRIEVER</span><strong>{engineOptions.find((engine) => engine.value === selectedRetriever)?.label}</strong><p>{engineOptions.find((engine) => engine.value === selectedRetriever)?.detail}</p></div>
            <div className="evidence-legend"><span><i className="legend-dot dot-navy" /> Lexical</span><span><i className="legend-dot dot-sage" /> Semantic</span></div>
            {hits.slice(0, 4).map((hit) => <a className="evidence-item" href={`#${encodeURIComponent(hit.chunk_id)}`} key={hit.chunk_id}><span className="evidence-rank">{String(hit.rank).padStart(2, '0')}</span><span><strong>{String(hit.metadata.citation ?? hit.doc_id)}</strong><small>{hit.chunk_id}</small></span><ArrowUpRight size={14} /></a>)}
            {!hits.length && <p className="evidence-empty">{search.isPending ? 'Gathering source passages…' : 'Run a search to see source passages and ranking scores.'}</p>}
            <div className="evidence-footnote"><ShieldCheck size={14} /><span>Every source can be opened and independently reviewed.</span></div>
          </aside>
        </section>
      )}

      {qaResult && (
        <section className="answer-layout">
          <article className="answer-card">
            <div className="answer-heading"><div className="answer-icon"><Sparkles size={16} /></div><div><span className="section-kicker">GROUNDED RESPONSE</span><h2>Your research answer</h2></div><span className={qaResult.refused ? 'confidence-pill confidence-low' : 'confidence-pill'}>{qaResult.refused ? 'Evidence insufficient' : `Confidence ${Math.round(qaResult.confidence * 100)}%`}</span></div>
            <p className="answer-text">{qaResult.answer.split(/(\[\d+\])/g).map((part, index) => /^\[\d+\]$/.test(part) ? <a key={index} className="citation-chip" href={`#passage-${part.slice(1, -1)}`}>{part}</a> : part)}</p>
            {qaResult.unsupported_sentences.length > 0 && <div className="audit-warning"><ShieldAlert size={15} /><span>{qaResult.unsupported_sentences.length} sentence(s) did not contain an inline source citation. Review before relying on them.</span></div>}
            <div className="answer-feedback"><span>Was this useful?</span><button onClick={() => feedback.mutate('up')} aria-label="Helpful answer"><ThumbsUp size={15} /></button><button onClick={() => feedback.mutate('down')} aria-label="Unhelpful answer"><ThumbsDown size={15} /></button>{feedback.isSuccess && <small>Thank you for your feedback.</small>}</div>
            <div className="answer-disclaimer"><ShieldAlert size={15} /><span>{qaResult.disclaimer}</span></div>
          </article>
          <aside className="answer-sources"><div className="evidence-heading"><span className="evidence-icon"><BookOpen size={16} /></span><div><strong>Passages used</strong><span>{qaResult.passages.length} cited sources</span></div></div>
            {qaResult.passages.map((passage) => <article id={`passage-${passage.index}`} className="passage-card" key={passage.chunk_id}><div className="passage-meta"><span>[{passage.index}]</span><Link to={`/documents/${encodeURIComponent(passage.doc_id)}`}>{passage.doc_id} <ExternalLink size={12} /></Link></div><p>{passage.text}</p><div className="passage-scores"><span>{selectedRetriever.toUpperCase()} {formatScore(passage.score)}</span><span>Rank {passage.index}</span></div></article>)}
          </aside>
        </section>
      )}
    </div>
  );
}
