import { useMutation, useQuery } from '@tanstack/react-query';
import {
  Activity,
  ArrowDown,
  ArrowRight,
  ArrowUp,
  BookOpenText,
  CheckCircle2,
  Database,
  FlaskConical,
  Layers3,
  Languages,
  LayoutDashboard,
  LoaderCircle,
  LockKeyhole,
  Search,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from 'lucide-react';
import { useState } from 'react';
import type { FormEvent } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Link, useParams } from 'react-router-dom';
import { api, CompareResponse, ExperimentRun, Hit, Retriever } from '../lib/api';

const ENGINE_NAMES: Retriever[] = ['bm25', 'dense', 'hybrid'];
const ENGINE_LABELS: Record<Retriever, string> = { bm25: 'BM25', dense: 'Dense', hybrid: 'Hybrid' };
const ENGINE_COLORS: Record<Retriever, string> = { bm25: '#26385e', dense: '#6f927e', hybrid: '#ba8a3c' };

function ErrorState({ message }: { message: string }) {
  return <div className="error-banner" role="alert"><TriangleAlert size={17} /><div><strong>Couldn’t load this information</strong><span>{message}</span></div></div>;
}

function PageTitle({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return <div className="subpage-heading"><div className="eyebrow"><span className="eyebrow-line" /> {eyebrow}</div><h1>{title}</h1><p>{description}</p></div>;
}

function CompareColumn({ name, hits, baseline }: { name: Retriever; hits: Hit[]; baseline: Set<string> }) {
  return (
    <section className={`compare-column compare-${name}`}>
      <div className="compare-column-heading"><span className="engine-color-mark" style={{ backgroundColor: ENGINE_COLORS[name] }} /><div><h2>{ENGINE_LABELS[name]}</h2><p>{name === 'bm25' ? 'Lexical baseline' : name === 'dense' ? 'Semantic baseline' : 'Proposed fusion'}</p></div><span className="compare-count">{hits.length}</span></div>
      {!hits.length && <div className="small-empty">No ranked passages for this query.</div>}
      {hits.map((hit) => (
        <Link to={`/documents/${encodeURIComponent(hit.doc_id)}`} className="compare-hit" key={hit.chunk_id}>
          <div className="compare-hit-top"><span className="compare-rank">#{hit.rank}</span><span className="compare-doc">{String(hit.metadata.citation ?? hit.doc_id)}</span><span className="compare-score">{hit.score.toFixed(3)}</span></div>
          <p>{hit.text}</p>
          <div className="compare-hit-footer"><span>{hit.chunk_id}</span>{name === 'hybrid' && !baseline.has(hit.doc_id) && <span className="promoted"><ArrowUp size={12} /> Newly surfaced</span>}</div>
        </Link>
      ))}
    </section>
  );
}

export function ComparePage() {
  const [query, setQuery] = useState('');
  const compare = useMutation({ mutationFn: (text: string) => api.compare(text, 6) });
  const submit = (event: FormEvent) => { event.preventDefault(); if (query.trim()) compare.mutate(query.trim()); };
  const result = compare.data;
  const baseline = new Set(result?.results.bm25.map((hit) => hit.doc_id) ?? []);
  return (
    <div className="subpage">
      <PageTitle eyebrow="CONTROLLED COMPARISON" title="Three retrieval lenses." description="Run one query through BM25, dense semantic search, and hybrid fusion. The corpus and query stay fixed; only the retriever changes." />
      <form className="compare-query-form" onSubmit={submit}><Search size={18} /><input aria-label="Comparison query" placeholder="Enter a legal query to compare retrieval engines…" value={query} onChange={(event) => setQuery(event.target.value)} /><button className="primary-button" disabled={!query.trim() || compare.isPending}>{compare.isPending ? <LoaderCircle className="spin" size={16} /> : null} Compare engines <ArrowRight size={15} /></button></form>
      {compare.isError && <ErrorState message={compare.error.message} />}
      {!result && !compare.isPending && <div className="empty-state-card"><Layers3 size={23} /><h2>Same question. Side-by-side evidence.</h2><p>See which passages each method surfaces, inspect rank shifts, and compare the overlap between retrieval strategies.</p></div>}
      {compare.isPending && <div className="loading-card"><LoaderCircle className="spin" /> Running all three retrieval methods…</div>}
      {result && <CompareResults result={result} baseline={baseline} />}
    </div>
  );
}

function CompareResults({ result, baseline }: { result: CompareResponse; baseline: Set<string> }) {
  const overlapEntries = Object.entries(result.overlap);
  return (
    <>
      <div className="compare-query-label"><span className="section-kicker">QUERY UNDER TEST</span><strong>“{result.query}”</strong></div>
      <div className="overlap-strip"><div className="overlap-title"><Layers3 size={16} /><span>Result-set overlap</span></div>{overlapEntries.map(([pair, score]) => <div className="overlap-stat" key={pair}><span>{pair.replace('-', ' / ').toUpperCase()}</span><strong>{Math.round(score * 100)}%</strong><div className="overlap-track"><i style={{ width: `${score * 100}%` }} /></div></div>)}</div>
      <div className="compare-columns">{ENGINE_NAMES.map((name) => <CompareColumn key={name} name={name} hits={result.results[name]} baseline={baseline} />)}</div>
      <p className="comparison-note"><ShieldCheck size={14} /> The hybrid column marks documents absent from the BM25 baseline. Document-level overlap is calculated from the top six hits.</p>
    </>
  );
}

function MetricChart({ runs }: { runs: ExperimentRun[] }) {
  const latest = runs[0]?.systems;
  if (!latest) return <div className="chart-empty"><FlaskConical size={22} /><span>No completed experiment metrics yet.</span></div>;
  const keys = ['map', 'mrr', 'ndcg@10', 'precision@5'];
  const data = keys.map((metric) => ({
    metric: metric.toUpperCase(),
    ...Object.fromEntries(ENGINE_NAMES.map((engine) => [ENGINE_LABELS[engine], latest[engine]?.[metric] ?? 0])),
  }));
  return (
    <ResponsiveContainer width="100%" height={268}>
      <BarChart data={data} margin={{ top: 10, right: 12, left: -18, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e9e6df" />
        <XAxis dataKey="metric" axisLine={false} tickLine={false} tick={{ fill: '#758078', fontSize: 11 }} />
        <YAxis axisLine={false} tickLine={false} tick={{ fill: '#758078', fontSize: 11 }} domain={[0, 1]} />
        <Tooltip formatter={(value) => Number(value).toFixed(3)} contentStyle={{ borderRadius: 12, borderColor: '#e8e4dc', fontSize: 12 }} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {ENGINE_NAMES.map((engine) => <Bar key={engine} dataKey={ENGINE_LABELS[engine]} fill={ENGINE_COLORS[engine]} radius={[4, 4, 0, 0]} maxBarSize={27}><Cell fill={ENGINE_COLORS[engine]} /></Bar>)}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function ExperimentsPage() {
  const { data: runs, isLoading, isError, error } = useQuery({ queryKey: ['experiments'], queryFn: api.experiments });
  return (
    <div className="subpage">
      <PageTitle eyebrow="RESEARCH EVIDENCE" title="Measure what matters." description="A reproducible evaluation dashboard for retrieval quality, paired comparisons, and the evidence behind each reported metric." />
      {isError && <ErrorState message={error.message} />}
      <div className="experiment-summary-row">
        <div className="experiment-summary"><span>EXPERIMENT RUNS</span><strong>{isLoading ? '—' : runs?.length ?? 0}</strong><small>Recorded local evaluations</small></div>
        <div className="experiment-summary"><span>RETRIEVAL SYSTEMS</span><strong>03</strong><small>Same corpus · same queries</small></div>
        <div className="experiment-summary"><span>PRIMARY METRIC</span><strong className="summary-word">MAP</strong><small>Mean average precision</small></div>
        <div className="experiment-summary"><span>STATISTICAL TEST</span><strong className="summary-word">Paired</strong><small>Wilcoxon + t-test</small></div>
      </div>
      <section className="chart-panel"><div className="panel-heading"><div><span className="section-kicker">LATEST REPRODUCIBLE RUN</span><h2>Retrieval quality by system</h2></div>{runs?.[0] && <span className="run-label"><span /> {runs[0].run_id}</span>}</div>{isLoading ? <div className="loading-card"><LoaderCircle className="spin" /> Loading experiment runs…</div> : runs?.length ? <MetricChart runs={runs} /> : <div className="chart-empty"><FlaskConical size={22} /><span>No completed metrics to visualize yet.</span><small>Prepare authorized corpus, query, and relevance-judgment files, then run <code>make experiment</code>.</small></div>}</section>
      {runs?.[0] && <div className="experiment-run-details"><div><span className="section-kicker">RUN METADATA</span><h2>Reproducibility record</h2></div><div className="run-detail-grid"><span>Run identifier</span><strong>{runs[0].run_id}</strong><span>Queries evaluated</span><strong>{runs[0].query_count ?? '—'}</strong><span>Documents / chunks</span><strong>{runs[0].document_count ?? '—'} / {runs[0].chunk_count ?? '—'}</strong><span>Fixed random seed</span><strong>{runs[0].seed ?? '—'}</strong></div></div>}
      <div className="research-note"><ShieldCheck size={16} /><p>Metrics remain blank until an evaluation is actually run. NyayaAI does not fabricate or prefill benchmark scores.</p></div>
    </div>
  );
}

interface DocumentSummary { doc_id: string; source: string; metadata: Record<string, unknown>; excerpt: string }
interface DocumentChunk extends Hit { start_char: number; end_char: number; token_count: number }
interface DocumentResponse { document: { doc_id: string; text: string; source: string; metadata: Record<string, unknown> }; chunks: DocumentChunk[] }

export function DocumentLibraryPage() {
  const [filter, setFilter] = useState('');
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['documents'],
    queryFn: async () => {
      const response = await fetch(`${import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'}/api/v1/documents`);
      if (!response.ok) throw new Error(`Document listing failed (${response.status})`);
      return (await response.json()) as { documents: DocumentSummary[]; total: number };
    },
  });
  const documents = (data?.documents ?? []).filter((document) => `${document.doc_id} ${document.source} ${JSON.stringify(document.metadata)}`.toLowerCase().includes(filter.toLowerCase()));
  return (
    <div className="subpage">
      <PageTitle eyebrow="SOURCE LIBRARY" title="The corpus, in context." description="Browse the authorized source documents that power retrieval. Open a document to review its full text and chunk boundaries." />
      <div className="library-toolbar"><div><Database size={16} /><strong>{data?.total ?? 0}</strong><span>indexed documents</span></div><label><Search size={15} /><input aria-label="Filter documents" placeholder="Filter by case, source or court…" value={filter} onChange={(event) => setFilter(event.target.value)} /></label></div>
      {isError && <ErrorState message={error.message} />}
      {isLoading && <div className="loading-card"><LoaderCircle className="spin" /> Loading the source library…</div>}
      {!isLoading && documents.length === 0 && <div className="empty-state-card"><BookOpenText size={23} /><h2>{filter ? 'No documents match that filter.' : 'No documents in the index yet.'}</h2><p>After adding authorized data, run the ingestion pipeline to prepare documents for source review.</p><code>make ingest</code></div>}
      <div className="document-list">{documents.map((document) => <Link className="document-list-item" key={document.doc_id} to={`/documents/${encodeURIComponent(document.doc_id)}`}><span className="document-list-icon"><BookOpenText size={17} /></span><span className="document-list-copy"><strong>{String(document.metadata.citation ?? document.metadata.title ?? document.doc_id)}</strong><small>{document.source.toUpperCase()} {document.metadata.court ? `· ${document.metadata.court}` : ''} {document.metadata.year ? `· ${document.metadata.year}` : ''}</small><p>{document.excerpt}</p></span><ArrowRight size={16} /></Link>)}</div>
    </div>
  );
}

export function DocumentPage() {
  const { documentId = '' } = useParams();
  const decodedId = decodeURIComponent(documentId);
  const { data, isLoading, isError, error } = useQuery<DocumentResponse>({
    queryKey: ['document', decodedId],
    queryFn: async () => {
      const base = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
      const response = await fetch(`${base}/api/v1/documents/${encodeURIComponent(decodedId)}`);
      if (!response.ok) {
        const detail = (await response.json().catch(() => ({}))) as { detail?: string };
        throw new Error(detail.detail ?? `Document request failed (${response.status})`);
      }
      return (await response.json()) as DocumentResponse;
    },
  });
  return (
    <div className="subpage document-page">
      <Link className="back-link" to="/documents"><ArrowDown className="back-arrow" size={15} /> Back to document library</Link>
      {isError && <ErrorState message={error.message} />}
      {isLoading && <div className="loading-card"><LoaderCircle className="spin" /> Opening source document…</div>}
      {data && <><PageTitle eyebrow={`SOURCE DOCUMENT · ${data.document.source.toUpperCase()}`} title={String(data.document.metadata.citation ?? data.document.metadata.title ?? data.document.doc_id)} description={`${data.document.metadata.court ?? 'Legal corpus document'} ${data.document.metadata.year ? `· ${data.document.metadata.year}` : ''} · ${data.chunks.length} indexed passages`} /><section className="document-reader"><div className="document-reader-heading"><BookOpenText size={17} /><span>Full source text</span><span>{data.document.doc_id}</span></div><article>{data.document.text}</article></section><section className="document-chunks"><span className="section-kicker">INDEXED EVIDENCE</span><h2>Retrieved passage boundaries</h2>{data.chunks.map((chunk) => <article className="passage-card" key={chunk.chunk_id}><div className="passage-meta"><span>{chunk.chunk_id}</span><span>characters {chunk.start_char}–{chunk.end_char} · {chunk.token_count} tokens</span></div><p>{chunk.text}</p></article>)}</section></>}
    </div>
  );
}

export function AdminPage() {
  const [token, setToken] = useState(() => localStorage.getItem('nyayaai-token') ?? '');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [register, setRegister] = useState(false);
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 30000 });
  const authenticate = useMutation({
    mutationFn: () => api.authenticate(username, password, register),
    onSuccess: (session) => {
      localStorage.setItem('nyayaai-token', session.access_token);
      setToken(session.access_token);
      setPassword('');
    },
  });
  const overview = useQuery({
    queryKey: ['admin-overview', token],
    queryFn: () => api.adminOverview(token),
    enabled: Boolean(token),
  });
  const users = useQuery({
    queryKey: ['admin-users', token],
    queryFn: () => api.adminUsers(token),
    enabled: Boolean(token) && overview.isSuccess,
  });
  const status = health.isError ? 'Unavailable' : health.isLoading ? 'Checking' : 'Operational';
  const logout = () => {
    localStorage.removeItem('nyayaai-token');
    setToken('');
  };
  return (
    <div className="subpage">
      <PageTitle eyebrow="LOCAL ADMINISTRATION" title="System health & data readiness." description="A transparent view of the local research services. Corpus and model availability are reported as observed, not assumed." />
      <div className="admin-status-banner"><div className={`status-emblem ${health.isError ? 'status-emblem-error' : ''}`}>{health.isError ? <TriangleAlert size={21} /> : <Activity size={21} />}</div><div><span>API SERVICE</span><strong>{status}</strong><small>{health.isError ? health.error.message : 'Health checks refresh every 30 seconds.'}</small></div><span className={health.isError ? 'service-status failed' : 'service-status'}><i /> {status}</span></div>
      {!token && <form className="admin-login-card" onSubmit={(event) => { event.preventDefault(); authenticate.mutate(); }}>
        <div><LockKeyhole size={18} /><h2>{register ? 'Create a researcher account' : 'Administrator sign-in'}</h2><p>Admin access requires credentials bootstrapped with <code>INITIAL_ADMIN_USERNAME</code> and <code>INITIAL_ADMIN_PASSWORD</code>. New accounts have the user role.</p></div>
        <label>Username<input autoComplete="username" minLength={3} value={username} onChange={(event) => setUsername(event.target.value)} required /></label>
        <label>Password<input type="password" autoComplete={register ? 'new-password' : 'current-password'} minLength={8} value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
        {authenticate.isError && <span className="auth-error" role="alert">{authenticate.error.message}</span>}
        <div className="auth-actions"><button className="primary-button" disabled={authenticate.isPending}>{authenticate.isPending ? <LoaderCircle className="spin" size={14} /> : null}{register ? 'Create account' : 'Sign in'} <ArrowRight size={14} /></button><button className="text-action" type="button" onClick={() => { setRegister((value) => !value); authenticate.reset(); }}>{register ? 'Sign in instead' : 'Create user account'}</button></div>
      </form>}
      {token && overview.isError && <div className="admin-access-warning"><LockKeyhole size={17} /><div><strong>Administrator access required</strong><p>{overview.error.message}. This account has no admin privileges, or its token has expired.</p></div><button className="text-action" onClick={logout}>Sign out</button></div>}
      {token && overview.isLoading && <div className="loading-card"><LoaderCircle className="spin" /> Verifying your administrator role…</div>}
      {token && overview.data && <>
        <div className="admin-access-bar"><span><ShieldCheck size={15} /> Signed in with administrator access</span><button className="text-action" onClick={logout}>Sign out</button></div>
        <div className="admin-metrics"><div className="admin-metric"><Database size={18} /><span>Indexed documents</span><strong>{overview.data.corpus_documents}</strong><small>{overview.data.corpus_chunks} indexed passages</small></div><div className="admin-metric"><FlaskConical size={18} /><span>Recorded evaluations</span><strong>{overview.data.experiment_runs}</strong><small>Stored under evaluation/results</small></div><div className="admin-metric"><LockKeyhole size={18} /><span>Registered users</span><strong>{overview.data.users}</strong><small>Role-based authentication enabled</small></div></div>
        {users.data && <section className="admin-user-list"><div><span className="section-kicker">ACCESS CONTROL</span><h2>Workspace users</h2></div>{users.data.map((user) => <div key={user.username}><span>{user.username}</span><strong className={`user-role role-${user.role}`}>{user.role}</strong><small>{user.created_at}</small></div>)}</section>}
      </>}
      <section className="admin-checklist"><div><span className="section-kicker">SERVICE CHECKLIST</span><h2>What is connected</h2></div><p><CheckCircle2 size={16} /> API and health probes</p><p><CheckCircle2 size={16} /> JWT access tokens with user/admin roles</p><p><CheckCircle2 size={16} /> Rate-limited requests with request IDs</p><p><CheckCircle2 size={16} /> File-backed local corpus index</p><p><TriangleAlert size={16} /> Never ingest or publish data unless its license permits it.</p></section>
    </div>
  );
}

const extensions = [
  { icon: BookOpenText, title: 'Judgment summarization', detail: 'Concise case briefs with paragraph-level citations.' },
  { icon: Activity, title: 'Case timeline', detail: 'Procedural history and event chronology across a matter.' },
  { icon: Search, title: 'Document analyzer', detail: 'Structured clause, issue, and citation extraction.' },
  { icon: Languages, title: 'Multilingual research', detail: 'Future Hindi, Telugu, and Tamil query and corpus support.' },
  { icon: LayoutDashboard, title: 'Research analytics', detail: 'Additional analytics beyond the core evaluation dashboard.' },
];

export function RoadmapPage() {
  return (
    <div className="subpage">
      <PageTitle eyebrow="SEPARATE FROM THE CORE" title="Future extensions." description="Ideas for future work, explicitly outside NyayaAI’s three research modules: hybrid retrieval, cited legal QA, and explainable source attribution." />
      <div className="roadmap-banner"><Sparkles size={18} /><span>Roadmap only</span><p>These cards are non-functional by design and are not part of the evaluated system.</p></div>
      <div className="roadmap-grid">{extensions.map(({ icon: Icon, title, detail }, index) => <article className="roadmap-card" key={title}><div className="roadmap-card-top"><span className="roadmap-number">0{index + 1}</span><span className="roadmap-state">FUTURE</span></div><div className="roadmap-icon"><Icon size={20} /></div><h2>{title}</h2><p>{detail}</p><span className="roadmap-availability">Not in current scope <ArrowRight size={13} /></span></article>)}</div>
    </div>
  );
}
