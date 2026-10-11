import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, ArrowRight, FlaskConical, LoaderCircle, ShieldCheck, Trash2 } from 'lucide-react';
import { useState } from 'react';
import type { FormEvent } from 'react';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useToast } from '../components/Toast';
import { EmptyState, ErrorState, LoadingCard, PageTitle, Pagination, StatusBadge } from '../components/ui';
import { api, BenchmarkRun, ExperimentInput, ExperimentSummary, Retriever } from '../lib/api';
import { ENGINE_COLORS, ENGINE_LABELS, formatDate, formatMs } from '../lib/format';

const ENGINES: Retriever[] = ['bm25', 'dense', 'hybrid'];
const PAGE_SIZE = 10;

/** Parse "query || DOC1, DOC2" lines into experiment queries. */
export function parseQueries(text: string): ExperimentInput['queries'] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [query, judgments = ''] = line.split('||');
      return {
        query: query.trim(),
        relevant_doc_ids: judgments.split(/[,\s]+/).map((id) => id.trim()).filter(Boolean),
      };
    })
    .filter((item) => item.query.length > 0);
}

function statusTone(status: string): 'ok' | 'warn' | 'error' {
  return status === 'completed' ? 'ok' : status === 'partial' ? 'warn' : 'error';
}

function MetricChart({ systems }: { systems: ExperimentSummary['summary']['systems'] | BenchmarkRun['systems'] }) {
  const engines = ENGINES.filter((engine) => {
    const value = systems?.[engine] as { metrics?: Record<string, number> } | Record<string, number> | undefined;
    return value !== undefined;
  });
  const metricsFor = (engine: Retriever): Record<string, number> => {
    const value = systems?.[engine] as { metrics?: Record<string, number> } & Record<string, unknown>;
    return (value?.metrics ?? value ?? {}) as Record<string, number>;
  };
  const keys = Array.from(new Set(engines.flatMap((engine) => Object.keys(metricsFor(engine)))))
    .filter((key) => ['map', 'mrr', 'ndcg@10'].includes(key) || key.startsWith('precision@') || key.startsWith('recall@'));
  if (!keys.length) return <div className="chart-empty"><FlaskConical size={22} /><span>No metrics were computed.</span><small>Add relevance judgments (document IDs after “||”) to compute MAP, MRR, and nDCG.</small></div>;
  const data = keys.map((metric) => ({
    metric: metric.toUpperCase(),
    ...Object.fromEntries(engines.flatMap((engine) => {
      const score = metricsFor(engine)[metric];
      return typeof score === 'number' ? [[ENGINE_LABELS[engine], score]] : [];
    })),
  }));
  return (
    <div role="img" aria-label="Bar chart of retrieval metrics by engine">
      <ResponsiveContainer width="100%" height={268}>
        <BarChart data={data} margin={{ top: 10, right: 12, left: -18, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e9e6df" />
          <XAxis dataKey="metric" axisLine={false} tickLine={false} tick={{ fill: '#758078', fontSize: 11 }} />
          <YAxis axisLine={false} tickLine={false} tick={{ fill: '#758078', fontSize: 11 }} domain={[0, 1]} />
          <Tooltip formatter={(value) => Number(value).toFixed(3)} contentStyle={{ borderRadius: 12, borderColor: '#e8e4dc', fontSize: 12 }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {engines.map((engine) => <Bar key={engine} dataKey={ENGINE_LABELS[engine]} fill={ENGINE_COLORS[engine]} radius={[4, 4, 0, 0]} maxBarSize={27} />)}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function CreateExperiment({ available }: { available: Retriever[] }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const notify = useToast();
  const [name, setName] = useState('');
  const [engines, setEngines] = useState<Retriever[]>(['bm25']);
  const [k, setK] = useState(10);
  const [queries, setQueries] = useState('');
  const [error, setError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: api.createExperiment,
    onSuccess: (experiment) => {
      void queryClient.invalidateQueries({ queryKey: ['experiments'] });
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      notify(`Experiment “${experiment.name}” saved (${experiment.status}).`);
      navigate(`/experiments/${experiment.experiment_id}`);
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const parsed = parseQueries(queries);
    if (!name.trim()) return setError('Give the experiment a name.');
    if (!engines.length) return setError('Select at least one retrieval engine.');
    if (!parsed.length) return setError('Enter at least one query.');
    if (parsed.length > 25) return setError('Experiments are limited to 25 queries.');
    setError(null);
    create.mutate({ name: name.trim(), retrievers: engines, k, queries: parsed });
  };
  const toggle = (engine: Retriever) =>
    setEngines((current) => (current.includes(engine) ? current.filter((item) => item !== engine) : [...current, engine]));
  return (
    <form className="panel experiment-form" onSubmit={submit}>
      <div className="panel-heading"><div><span className="section-kicker">NEW EXPERIMENT</span><h2>Run a retrieval experiment</h2></div></div>
      <label>Name<input value={name} maxLength={120} onChange={(event) => setName(event.target.value)} placeholder="e.g. Murder appeals — BM25 vs hybrid" required /></label>
      <fieldset>
        <legend>Engines</legend>
        {ENGINES.map((engine) => (
          <label key={engine} className="checkbox">
            <input type="checkbox" checked={engines.includes(engine)} disabled={!available.includes(engine)} onChange={() => toggle(engine)} />
            {ENGINE_LABELS[engine]}{!available.includes(engine) && ' (disabled)'}
          </label>
        ))}
      </fieldset>
      <label>Documents per query (k)<input type="number" min={1} max={50} value={k} onChange={(event) => setK(Math.max(1, Math.min(50, Number(event.target.value) || 10)))} /></label>
      <label>Queries — one per line; optionally add relevant document IDs after “||”
        <textarea rows={6} value={queries} onChange={(event) => setQueries(event.target.value)} placeholder={'Conviction under Section 302 IPC on circumstantial evidence || C1438, C2693\nQuashing of FIR under Section 482 CrPC'} required />
      </label>
      <small className="field-hint">Relevance judgments are your own; metrics are computed only for queries that include them. Document IDs appear on every result and in the corpus library.</small>
      {(error || create.isError) && <p className="auth-error" role="alert">{error ?? create.error?.message}</p>}
      <button className="primary-button" disabled={create.isPending}>{create.isPending ? <><LoaderCircle className="spin" size={15} /> Running searches…</> : <>Run and save <ArrowRight size={14} /></>}</button>
    </form>
  );
}

function Benchmark() {
  const { data: runs, isLoading, isError, error } = useQuery({ queryKey: ['benchmarks'], queryFn: api.benchmarks });
  const run = runs?.[0];
  if (isLoading) return <LoadingCard label="Loading benchmark runs…" />;
  if (isError) return <ErrorState message={error.message} />;
  if (!run) return <EmptyState icon={<FlaskConical size={22} />} title="No benchmark recorded"><p>Run <code>python -m evaluation.seed_aila_benchmark</code> after ingesting the AILA corpus.</p></EmptyState>;
  return (
    <section className="panel">
      <div className="panel-heading"><div><span className="section-kicker">OFFICIAL BENCHMARK</span><h2>{run.dataset_name ?? run.run_id}</h2></div><span className="run-label"><span /> {run.run_id}</span></div>
      {run.tasks ? (
        <div className="benchmark-task-grid">
          {Object.entries(run.tasks).map(([task, result]) => (
            <article className="benchmark-task-card" key={task}>
              <span className="section-kicker">{task === 'priorcases' ? 'PRIOR-CASE RETRIEVAL' : 'STATUTE RETRIEVAL'}</span>
              <strong>{result.query_count} queries · {result.document_count} candidates</strong>
              {Object.entries(result.systems).map(([system, metrics]) => (
                <div key={system}><span>{system.toUpperCase()} MAP</span><b>{metrics.map?.toFixed(3) ?? '—'}</b><span>MRR</span><b>{metrics.mrr?.toFixed(3) ?? '—'}</b><span>nDCG@10</span><b>{metrics['ndcg@10']?.toFixed(3) ?? '—'}</b></div>
              ))}
            </article>
          ))}
        </div>
      ) : <MetricChart systems={run.systems} />}
      {run.source_url && <div className="research-note"><ShieldCheck size={16} /><p>{run.attribution}. Licence: {run.license}. Protocol: {run.evaluation_protocol ?? 'not recorded'}. <a href={run.source_url} target="_blank" rel="noreferrer">Source record</a>.</p></div>}
    </section>
  );
}

export function ExperimentsPage() {
  const [page, setPage] = useState(1);
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, staleTime: 30_000 });
  const list = useQuery({
    queryKey: ['experiments', page],
    queryFn: () => api.experiments(PAGE_SIZE, (page - 1) * PAGE_SIZE),
  });
  return (
    <div className="subpage">
      <PageTitle eyebrow="RESEARCH EVIDENCE" title="Measure what matters." description="Run the same queries through each engine on the same corpus, record rankings and latency, and compute IR metrics against your relevance judgments." />
      <div className="two-column">
        <CreateExperiment available={health.data?.available_retrievers ?? ['bm25']} />
        <section className="panel">
          <div className="panel-heading"><div><span className="section-kicker">SAVED RUNS</span><h2>My experiments</h2></div></div>
          {list.isLoading && <LoadingCard label="Loading experiments…" />}
          {list.isError && <ErrorState message={list.error.message} onRetry={() => void list.refetch()} />}
          {list.data?.experiments.length === 0 && <EmptyState icon={<FlaskConical size={20} />} title="No saved experiments"><p>Results you run are saved to your account.</p></EmptyState>}
          <ul className="simple-list">
            {list.data?.experiments.map((experiment) => (
              <li key={experiment.experiment_id}>
                <Link to={`/experiments/${experiment.experiment_id}`}>{experiment.name}</Link>
                <span>{experiment.config.retrievers.map((engine) => ENGINE_LABELS[engine]).join(' · ')} · {experiment.summary.query_count} queries · {formatDate(experiment.created_at, true)}</span>
                <StatusBadge tone={statusTone(experiment.status)}>{experiment.status}</StatusBadge>
              </li>
            ))}
          </ul>
          {list.data && <Pagination page={page} pageSize={PAGE_SIZE} total={list.data.total} onPage={setPage} />}
        </section>
      </div>
      <Benchmark />
    </div>
  );
}

export function ExperimentDetailPage() {
  const { experimentId = '' } = useParams();
  const navigate = useNavigate();
  const notify = useToast();
  const queryClient = useQueryClient();
  const { data, isLoading, isError, error } = useQuery({ queryKey: ['experiment', experimentId], queryFn: () => api.experiment(experimentId) });
  const remove = useMutation({
    mutationFn: () => api.deleteExperiment(experimentId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['experiments'] });
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      notify('Experiment deleted.');
      navigate('/experiments');
    },
    onError: (caught: Error) => notify(caught.message, 'error'),
  });
  const engines = data ? ENGINES.filter((engine) => data.config.retrievers.includes(engine)) : [];
  return (
    <div className="subpage">
      <Link className="back-link" to="/experiments"><ArrowLeft size={15} /> All experiments</Link>
      {isLoading && <LoadingCard label="Loading experiment…" />}
      {isError && <ErrorState message={error.message} />}
      {data && (
        <>
          <PageTitle
            eyebrow={`EXPERIMENT · ${data.status.toUpperCase()}`}
            title={data.name}
            description={`${data.summary.query_count} queries (${data.summary.judged_query_count} with relevance judgments) · k = ${data.config.k} · ${formatDate(data.created_at, true)} · ${formatMs(data.duration_ms)} total`}
            actions={<button type="button" className="secondary-button danger" disabled={remove.isPending} onClick={() => { if (window.confirm('Delete this experiment permanently?')) remove.mutate(); }}><Trash2 size={14} /> Delete</button>}
          />
          <div className="experiment-summary-row">
            {engines.map((engine) => {
              const system = data.summary.systems[engine];
              return (
                <div className="experiment-summary" key={engine}>
                  <span>{ENGINE_LABELS[engine].toUpperCase()}</span>
                  {system?.status === 'ok' ? (
                    <>
                      <strong>{typeof system.metrics?.map === 'number' ? system.metrics.map.toFixed(3) : '—'}</strong>
                      <small>MAP · mean latency {formatMs(system.mean_latency_ms)}</small>
                    </>
                  ) : <><strong className="summary-word">Unavailable</strong><small>{system?.error}</small></>}
                </div>
              );
            })}
          </div>
          <section className="chart-panel"><div className="panel-heading"><div><span className="section-kicker">MEAN OVER JUDGED QUERIES</span><h2>Retrieval quality by engine</h2></div></div><MetricChart systems={data.summary.systems} /></section>
          {data.summary.notes.map((note) => <p className="comparison-note" key={note}><ShieldCheck size={14} /> {note}</p>)}
          {data.summary.unknown_relevant_doc_ids.length > 0 && <div className="audit-warning"><ShieldCheck size={15} /><span>These judged IDs are not in the corpus and still count as relevant: {data.summary.unknown_relevant_doc_ids.join(', ')}.</span></div>}
          <section className="panel">
            <div className="panel-heading"><div><span className="section-kicker">PER-QUERY RESULTS</span><h2>Rankings</h2></div></div>
            {data.results.queries.map((item) => (
              <details className="query-result" key={item.index} open={data.results.queries.length <= 3}>
                <summary><strong>Q{item.index}.</strong> {item.query} {item.relevant_doc_ids.length > 0 && <small>({item.relevant_doc_ids.length} judged relevant)</small>}</summary>
                <div className="table-scroll">
                  <table className="data-table">
                    <thead><tr><th scope="col">Rank</th>{engines.map((engine) => <th scope="col" key={engine}>{ENGINE_LABELS[engine]} {item.systems[engine]?.latency_ms !== undefined && <small>({formatMs(item.systems[engine]?.latency_ms)})</small>}</th>)}</tr></thead>
                    <tbody>
                      {Array.from({ length: data.config.k }, (_, row) => (
                        <tr key={row}>
                          <td>{row + 1}</td>
                          {engines.map((engine) => {
                            const system = item.systems[engine];
                            if (system?.error) return <td key={engine}>{row === 0 ? 'Unavailable' : ''}</td>;
                            const entry = system?.ranking?.[row];
                            return <td key={engine} className={entry && item.relevant_doc_ids.includes(entry.doc_id) ? 'relevant-cell' : ''}>{entry ? <Link to={`/documents/${encodeURIComponent(entry.doc_id)}`} title={entry.title}>{entry.doc_id}</Link> : '—'}</td>;
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {engines.some((engine) => item.systems[engine]?.metrics) && (
                  <p className="field-hint">{engines.map((engine) => { const metrics = item.systems[engine]?.metrics; return metrics ? `${ENGINE_LABELS[engine]}: AP ${metrics.map.toFixed(3)}, RR ${metrics.mrr.toFixed(3)}` : null; }).filter(Boolean).join(' · ')}</p>
                )}
              </details>
            ))}
          </section>
        </>
      )}
    </div>
  );
}
