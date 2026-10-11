import { useMutation, useQuery } from '@tanstack/react-query';
import { ArrowRight, ArrowUp, Layers3, LoaderCircle, Search, ShieldCheck, TriangleAlert } from 'lucide-react';
import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { EmptyState, ErrorState, LoadingCard, PageTitle } from '../components/ui';
import { api, CompareResponse, Hit, Retriever } from '../lib/api';
import { ENGINE_COLORS, ENGINE_LABELS, formatMs, formatScore } from '../lib/format';

const ENGINES: Retriever[] = ['bm25', 'dense', 'hybrid'];
const ROLE: Record<Retriever, string> = { bm25: 'Lexical baseline', dense: 'Semantic baseline', hybrid: 'Rank fusion' };

function CompareColumn({ name, hits, latency, baseline }: { name: Retriever; hits: Hit[]; latency: number | null; baseline: Set<string> }) {
  return (
    <section className={`compare-column compare-${name}`}>
      <div className="compare-column-heading">
        <span className="engine-color-mark" style={{ backgroundColor: ENGINE_COLORS[name] }} />
        <div><h2>{ENGINE_LABELS[name]}</h2><p>{ROLE[name]} · {formatMs(latency)}</p></div>
        <span className="compare-count">{hits.length}</span>
      </div>
      {!hits.length && <div className="small-empty">No ranked passages for this query.</div>}
      {hits.map((hit) => (
        <Link to={`/documents/${encodeURIComponent(hit.doc_id)}#${encodeURIComponent(hit.chunk_id)}`} className="compare-hit" key={hit.chunk_id}>
          <div className="compare-hit-top"><span className="compare-rank">#{hit.rank}</span><span className="compare-doc">{hit.title}</span><span className="compare-score">{formatScore(hit.score, name === 'hybrid' ? 4 : 3)}</span></div>
          <p>{hit.excerpt}</p>
          <div className="compare-hit-footer"><span>{hit.chunk_id}</span>{name !== 'bm25' && baseline.size > 0 && !baseline.has(hit.doc_id) && <span className="promoted"><ArrowUp size={12} /> Not in BM25 top {hits.length}</span>}</div>
        </Link>
      ))}
    </section>
  );
}

function CompareResults({ result }: { result: CompareResponse }) {
  const baseline = new Set(result.results.bm25?.map((hit) => hit.doc_id) ?? []);
  const engines = ENGINES.filter((engine) => result.results[engine] !== undefined);
  return (
    <>
      <div className="compare-query-label"><span className="section-kicker">QUERY UNDER TEST · TOP {result.k} PASSAGES</span><strong>“{result.query}”</strong></div>
      {Object.entries(result.unavailable).map(([engine, reason]) => (
        <div className="audit-warning" key={engine}><TriangleAlert size={15} /><span><strong>{ENGINE_LABELS[engine as Retriever]}</strong> was not run: {reason}</span></div>
      ))}
      {Object.keys(result.overlap).length > 0 && (
        <div className="overlap-strip">
          <div className="overlap-title"><Layers3 size={16} /><span>Document overlap (Jaccard)</span></div>
          {Object.entries(result.overlap).map(([pair, score]) => <div className="overlap-stat" key={pair}><span>{pair.replace('-', ' / ').toUpperCase()}</span><strong>{Math.round(score * 100)}%</strong><div className="overlap-track"><i style={{ width: `${score * 100}%` }} /></div></div>)}
        </div>
      )}
      <div className="compare-columns">{engines.map((name) => <CompareColumn key={name} name={name} hits={result.results[name] ?? []} latency={result.engines[name]?.latency_ms ?? null} baseline={baseline} />)}</div>
      <p className="comparison-note"><ShieldCheck size={14} /> All engines searched the same corpus with the same query. Scores are not comparable across engines; compare ranks and overlap instead.</p>
    </>
  );
}

export function ComparePage() {
  const [query, setQuery] = useState('');
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, staleTime: 30_000 });
  const compare = useMutation({ mutationFn: (text: string) => api.compare(text, 6) });
  const available = ENGINES.filter((engine) => (health.data?.available_retrievers ?? []).includes(engine));
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (query.trim()) compare.mutate(query.trim());
  };
  return (
    <div className="subpage">
      <PageTitle eyebrow="CONTROLLED COMPARISON" title="Compare retrieval methods." description="Run one query through every enabled engine. The corpus and query stay fixed; only the retriever changes. Dense and hybrid load an embedding model on first use, which can take a while." />
      {health.data && available.length < 2 && <div className="audit-warning"><TriangleAlert size={15} /><span>Only {available.map((engine) => ENGINE_LABELS[engine]).join(', ') || 'no engine'} is enabled on this deployment, so there is nothing to compare against. Enable dense and hybrid with <code>ENABLED_RETRIEVERS</code>.</span></div>}
      <form className="compare-query-form" onSubmit={submit}>
        <Search size={18} aria-hidden />
        <input aria-label="Comparison query" placeholder="Enter a legal query to compare retrieval engines…" value={query} maxLength={2000} onChange={(event) => setQuery(event.target.value)} />
        <button className="primary-button" disabled={!query.trim() || compare.isPending}>{compare.isPending && <LoaderCircle className="spin" size={16} />} Compare engines <ArrowRight size={15} /></button>
      </form>
      {compare.isError && <ErrorState title="Comparison failed" message={compare.error.message} />}
      {!compare.data && !compare.isPending && <EmptyState icon={<Layers3 size={23} />} title="Same question. Side-by-side evidence."><p>See which passages each method surfaces and how much their result sets overlap.</p></EmptyState>}
      {compare.isPending && <LoadingCard label="Running each enabled retrieval engine…" />}
      {compare.data && !compare.isPending && <CompareResults result={compare.data} />}
    </div>
  );
}
