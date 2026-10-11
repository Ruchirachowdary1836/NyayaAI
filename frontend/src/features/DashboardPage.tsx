import { useQuery } from '@tanstack/react-query';
import { ArrowRight, BookOpenText, ChartNoAxesCombined, Database, FolderLock, Search, Sparkles } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { EmptyState, ErrorState, LoadingCard, PageTitle, StatCard, StatusBadge } from '../components/ui';
import { api, Retriever, RetrieverStatus } from '../lib/api';
import { ENGINE_LABELS, formatBytes, formatDate } from '../lib/format';

export function engineTone(status: RetrieverStatus | undefined): 'ok' | 'warn' | 'error' | 'muted' {
  if (!status || status.state === 'disabled') return 'muted';
  if (status.state === 'ready') return 'ok';
  if (status.state === 'failed') return 'error';
  return 'warn';
}

export const ENGINE_STATE_LABEL: Record<RetrieverStatus['state'], string> = {
  ready: 'Ready',
  not_loaded: 'Loads on first use',
  loading: 'Loading model…',
  failed: 'Unavailable',
  disabled: 'Disabled',
};

export function DashboardPage() {
  const location = useLocation();
  const denied = Boolean((location.state as { denied?: boolean } | null)?.denied);
  const { data, isLoading, isError, error, refetch } = useQuery({ queryKey: ['dashboard'], queryFn: api.dashboard });
  return (
    <div className="subpage">
      <PageTitle eyebrow="YOUR WORKSPACE" title={data ? `Welcome, ${data.user.username}.` : 'Your workspace.'} description="An overview of the corpus you search and the research you have saved." />
      {denied && <ErrorState title="Administrator access required" message="That page is only available to administrators." />}
      {isError && <ErrorState message={error.message} onRetry={() => void refetch()} />}
      {isLoading && <LoadingCard label="Loading your dashboard…" />}
      {data && (
        <>
          <div className="admin-metrics four">
            <StatCard icon={<Database size={18} />} label="Indexed corpus" value={data.corpus.documents.toLocaleString()} detail={`${data.corpus.chunks.toLocaleString()} searchable passages`} />
            <StatCard icon={<FolderLock size={18} />} label="My documents" value={data.library.total} detail={`${data.library.by_status.ready ?? 0} ready · ${data.library.by_status.failed ?? 0} failed`} />
            <StatCard icon={<ChartNoAxesCombined size={18} />} label="Saved experiments" value={data.experiments.total} detail="Stored in your account" />
            <StatCard icon={<Search size={18} />} label="Searches (30 days)" value={data.activity_last_30_days.search ?? 0} detail={`${data.activity_last_30_days.qa ?? 0} questions answered`} />
          </div>

          <div className="dashboard-grid">
            <section className="panel">
              <div className="panel-heading"><div><span className="section-kicker">SERVICES</span><h2>What’s available</h2></div></div>
              <ul className="service-list">
                {(Object.keys(ENGINE_LABELS) as Retriever[]).map((name) => {
                  const status = data.retrievers[name];
                  return (
                    <li key={name}>
                      <span>{ENGINE_LABELS[name]} retrieval</span>
                      <StatusBadge tone={engineTone(status)}>{status ? ENGINE_STATE_LABEL[status.state] : 'Unknown'}</StatusBadge>
                    </li>
                  );
                })}
                <li>
                  <span>Answer generation{data.generation.model ? ` · ${data.generation.model}` : ''}</span>
                  <StatusBadge tone={data.generation.configured ? 'ok' : 'error'}>{data.generation.configured ? 'Configured' : 'Not configured'}</StatusBadge>
                </li>
              </ul>
              {!data.generation.configured && <p className="panel-note">An administrator must set the AI provider key before questions can be answered. Search and document review work without it.</p>}
            </section>

            <section className="panel">
              <div className="panel-heading"><div><span className="section-kicker">START RESEARCHING</span><h2>Quick actions</h2></div></div>
              <div className="quick-actions">
                <Link to="/search"><Search size={16} /> Search the corpus <ArrowRight size={14} /></Link>
                <Link to="/search?mode=ask"><Sparkles size={16} /> Ask a grounded question <ArrowRight size={14} /></Link>
                <Link to="/library"><FolderLock size={16} /> Upload a document <ArrowRight size={14} /></Link>
                <Link to="/experiments"><ChartNoAxesCombined size={16} /> Run an experiment <ArrowRight size={14} /></Link>
              </div>
            </section>

            <section className="panel">
              <div className="panel-heading"><div><span className="section-kicker">RECENT UPLOADS</span><h2>My documents</h2></div><Link className="text-action" to="/library">View all <ArrowRight size={13} /></Link></div>
              {data.library.recent.length === 0 ? (
                <EmptyState icon={<FolderLock size={20} />} title="No uploads yet"><p>Upload PDFs or text files to search them privately.</p></EmptyState>
              ) : (
                <ul className="simple-list">
                  {data.library.recent.map((document) => (
                    <li key={document.document_id}>
                      <Link to={`/library/${document.document_id}`}>{document.title}</Link>
                      <span>{formatBytes(document.size_bytes)} · {formatDate(document.created_at)}</span>
                      <StatusBadge tone={document.status === 'ready' ? 'ok' : document.status === 'failed' ? 'error' : 'warn'}>{document.status}</StatusBadge>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="panel">
              <div className="panel-heading"><div><span className="section-kicker">RECENT EXPERIMENTS</span><h2>Saved runs</h2></div><Link className="text-action" to="/experiments">View all <ArrowRight size={13} /></Link></div>
              {data.experiments.recent.length === 0 ? (
                <EmptyState icon={<ChartNoAxesCombined size={20} />} title="No experiments yet"><p>Compare engines on your own queries and relevance judgments.</p></EmptyState>
              ) : (
                <ul className="simple-list">
                  {data.experiments.recent.map((experiment) => (
                    <li key={experiment.experiment_id}>
                      <Link to={`/experiments/${experiment.experiment_id}`}>{experiment.name}</Link>
                      <span>{formatDate(experiment.created_at, true)}</span>
                      <StatusBadge tone={experiment.status === 'completed' ? 'ok' : experiment.status === 'partial' ? 'warn' : 'error'}>{experiment.status}</StatusBadge>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
          <p className="comparison-note"><BookOpenText size={14} /> Corpus: AILA 2019 cases and statutes (CC BY 4.0). Counts are read live from the API and your account.</p>
        </>
      )}
    </div>
  );
}
