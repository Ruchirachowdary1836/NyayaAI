import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Activity,
  BookOpenText,
  Database,
  FlaskConical,
  FolderLock,
  Languages,
  LayoutDashboard,
  LoaderCircle,
  LockKeyhole,
  Search,
  Sparkles,
  UserRound,
  Users,
} from 'lucide-react';
import { useState } from 'react';
import type { FormEvent } from 'react';
import { useToast } from '../components/Toast';
import { ErrorState, LoadingCard, PageTitle, Pagination, StatCard, StatusBadge } from '../components/ui';
import { api, Retriever, UsageRow, UserProfile } from '../lib/api';
import { useAuth } from '../lib/auth';
import { ENGINE_LABELS, formatBytes, formatDate, formatMs } from '../lib/format';
import { ENGINE_STATE_LABEL, engineTone } from './DashboardPage';

export function ProfilePage() {
  const { user, applySession } = useAuth();
  const notify = useToast();
  const [username, setUsername] = useState(user?.username ?? '');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const update = useMutation({
    mutationFn: () => api.updateProfile({
      current_password: currentPassword,
      username: username.trim(),
      ...(newPassword ? { new_password: newPassword } : {}),
    }),
    onSuccess: async (session) => {
      await applySession(session);
      setCurrentPassword('');
      setNewPassword('');
      setConfirm('');
      notify(newPassword ? 'Profile and password updated. Other sessions were signed out.' : 'Profile updated.');
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!/^[A-Za-z0-9_.-]{3,80}$/.test(username.trim())) return setError('Usernames are 3–80 letters, numbers, dots, dashes, or underscores.');
    if (newPassword && newPassword.length < 8) return setError('New passwords must be at least 8 characters.');
    if (newPassword !== confirm) return setError('The new passwords do not match.');
    setError(null);
    update.mutate();
  };
  if (!user) return null;
  return (
    <div className="subpage">
      <PageTitle eyebrow="ACCOUNT SETTINGS" title="Your research profile." description="Update your username or password. Changes require your current password; changing your password signs out your other sessions." />
      <dl className="metadata-grid">
        <div><dt>Username</dt><dd>{user.username}</dd></div>
        <div><dt>Role</dt><dd>{user.role === 'admin' ? 'Administrator' : 'Researcher'}</dd></div>
        <div><dt>Member since</dt><dd>{formatDate(user.created_at)}</dd></div>
        <div><dt>Last sign-in</dt><dd>{formatDate(user.last_login_at, true)}</dd></div>
      </dl>
      <form className="auth-card wide" onSubmit={submit}>
        <div className="auth-card-heading"><span className="auth-icon"><UserRound size={18} /></span><div><h2>Edit profile</h2><p>Leave the new password blank to keep your current one.</p></div></div>
        <label>Username<input autoComplete="username" minLength={3} maxLength={80} value={username} onChange={(event) => setUsername(event.target.value)} required /></label>
        <label>Current password<input type="password" autoComplete="current-password" minLength={8} maxLength={256} value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required /></label>
        <label>New password (optional)<input type="password" autoComplete="new-password" minLength={8} maxLength={256} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} /></label>
        <label>Confirm new password<input type="password" autoComplete="new-password" maxLength={256} value={confirm} onChange={(event) => setConfirm(event.target.value)} disabled={!newPassword} /></label>
        {(error || update.isError) && <p className="auth-error" role="alert">{error ?? update.error?.message}</p>}
        <button className="primary-button" disabled={update.isPending}>{update.isPending && <LoaderCircle className="spin" size={14} />} Save changes</button>
      </form>
    </div>
  );
}

function UsageTable({ rows }: { rows: UsageRow[] }) {
  if (!rows.length) return <p className="field-hint">No recorded activity in this period.</p>;
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead><tr><th scope="col">Event</th><th scope="col">Engine</th><th scope="col">Outcome</th><th scope="col">Count</th><th scope="col">Avg latency</th></tr></thead>
        <tbody>{rows.map((row) => (
          <tr key={`${row.event_type}-${row.retriever}-${row.status}`}><td>{row.event_type}</td><td>{row.retriever ? ENGINE_LABELS[row.retriever as Retriever] ?? row.retriever : '—'}</td><td>{row.status}</td><td>{row.count}</td><td>{formatMs(row.avg_latency_ms)}</td></tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function UserManagement() {
  const { user: me } = useAuth();
  const notify = useToast();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState('');
  const users = useQuery({
    queryKey: ['admin-users', filter, page],
    queryFn: () => api.adminUsers({ q: filter || undefined, limit: 20, offset: (page - 1) * 20 }),
    placeholderData: keepPreviousData,
  });
  const change = useMutation({
    mutationFn: ({ target, payload }: { target: UserProfile; payload: { role?: 'user' | 'admin'; is_active?: boolean } }) => api.updateUser(target.username, payload),
    onSuccess: (updated) => {
      notify(`Updated ${updated.username}.`);
      void queryClient.invalidateQueries({ queryKey: ['admin-users'] });
      void queryClient.invalidateQueries({ queryKey: ['admin-overview'] });
    },
    onError: (caught: Error) => notify(caught.message, 'error'),
  });
  return (
    <section className="panel">
      <div className="panel-heading">
        <div><span className="section-kicker">ACCESS CONTROL</span><h2>Users</h2></div>
        <label className="inline-filter"><Search size={14} /><input aria-label="Filter users" placeholder="Filter by username" value={filter} maxLength={80} onChange={(event) => { setFilter(event.target.value); setPage(1); }} /></label>
      </div>
      {users.isError && <ErrorState message={users.error.message} />}
      {users.isLoading && <LoadingCard label="Loading users…" />}
      {users.data && (
        <div className="table-scroll">
          <table className="data-table">
            <thead><tr><th scope="col">Username</th><th scope="col">Role</th><th scope="col">Status</th><th scope="col">Created</th><th scope="col">Last sign-in</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>{users.data.users.map((account) => {
              const self = account.username === me?.username;
              return (
                <tr key={account.username}>
                  <td>{account.username}{self && ' (you)'}</td>
                  <td><StatusBadge tone={account.role === 'admin' ? 'warn' : 'muted'}>{account.role}</StatusBadge></td>
                  <td><StatusBadge tone={account.is_active ? 'ok' : 'error'}>{account.is_active ? 'active' : 'disabled'}</StatusBadge></td>
                  <td>{formatDate(account.created_at)}</td>
                  <td>{formatDate(account.last_login_at, true)}</td>
                  <td className="row-actions">
                    <button type="button" className="text-action" disabled={self || change.isPending} onClick={() => { if (window.confirm(`${account.role === 'admin' ? 'Remove administrator role from' : 'Grant administrator role to'} ${account.username}?`)) change.mutate({ target: account, payload: { role: account.role === 'admin' ? 'user' : 'admin' } }); }}>{account.role === 'admin' ? 'Make researcher' : 'Make admin'}</button>
                    <button type="button" className="text-action danger" disabled={self || change.isPending} onClick={() => { if (window.confirm(`${account.is_active ? 'Disable' : 'Re-enable'} ${account.username}? ${account.is_active ? 'Their sessions end immediately.' : ''}`)) change.mutate({ target: account, payload: { is_active: !account.is_active } }); }}>{account.is_active ? 'Disable' : 'Enable'}</button>
                  </td>
                </tr>
              );
            })}</tbody>
          </table>
        </div>
      )}
      {users.data && <Pagination page={page} pageSize={20} total={users.data.total} onPage={setPage} />}
    </section>
  );
}

export function AdminPage() {
  const overview = useQuery({ queryKey: ['admin-overview'], queryFn: api.adminOverview, refetchInterval: 30_000 });
  const data = overview.data;
  const report = data?.ingestion.ingestion_report as Record<string, unknown> | undefined;
  return (
    <div className="subpage">
      <PageTitle eyebrow="ADMINISTRATION" title="System health & usage." description="Live service status, corpus ingestion, anonymised usage counts, and account management. Figures are read from the running API and database." />
      {overview.isError && <ErrorState message={overview.error.message} onRetry={() => void overview.refetch()} />}
      {overview.isLoading && <LoadingCard label="Loading system overview…" />}
      {data && (
        <>
          <div className="admin-metrics four">
            <StatCard icon={<Database size={18} />} label="Indexed documents" value={data.corpus_documents.toLocaleString()} detail={`${data.corpus_chunks.toLocaleString()} passages`} />
            <StatCard icon={<Users size={18} />} label="Users" value={data.users} detail={`${data.active_users} active · ${data.users_active_last_7_days} used NyayaAI in 7 days`} />
            <StatCard icon={<FolderLock size={18} />} label="Uploaded documents" value={Object.values(data.uploaded_documents).reduce((sum, value) => sum + value, 0)} detail={`${formatBytes(data.uploaded_bytes)} · ${data.uploaded_documents.failed ?? 0} failed extraction`} />
            <StatCard icon={<FlaskConical size={18} />} label="Experiments" value={data.experiment_runs} detail={`${data.benchmark_runs} offline benchmark run(s)`} />
          </div>
          <div className="dashboard-grid">
            <section className="panel">
              <div className="panel-heading"><div><span className="section-kicker">SERVICES</span><h2>System health</h2></div></div>
              <ul className="service-list">
                <li><span>Database ({String(data.system.database_backend)}, schema {String(data.system.schema_revision)})</span><StatusBadge tone={data.system.database === 'ok' ? 'ok' : 'error'}>{String(data.system.database)}</StatusBadge></li>
                {(Object.keys(ENGINE_LABELS) as Retriever[]).map((name) => {
                  const status = data.retrievers[name];
                  return <li key={name}><span>{ENGINE_LABELS[name]}{status?.model ? ` · ${status.model}` : ''}</span><StatusBadge tone={engineTone(status)}>{status ? ENGINE_STATE_LABEL[status.state] : 'Unknown'}</StatusBadge></li>;
                })}
                <li><span>Generation · {String(data.system.generation_provider)} {String(data.system.generation_model ?? '')}</span><StatusBadge tone={data.system.generation_configured ? 'ok' : 'error'}>{data.system.generation_configured ? 'Configured' : 'Not configured'}</StatusBadge></li>
              </ul>
              {Object.entries(data.retrievers).filter(([, status]) => status?.error).map(([name, status]) => <p className="panel-note" key={name}>{ENGINE_LABELS[name as Retriever]} error: {status?.error}</p>)}
              <p className="panel-note">Environment: {String(data.system.environment)} · Python {String(data.system.python)} · Feedback: {data.feedback.up ?? 0} helpful / {data.feedback.down ?? 0} not helpful</p>
            </section>
            <section className="panel">
              <div className="panel-heading"><div><span className="section-kicker">INGESTION</span><h2>Corpus build</h2></div></div>
              {report ? (
                <dl className="metadata-grid compact">
                  <div><dt>Completed</dt><dd>{formatDate(String(report.completed_at), true)}</dd></div>
                  <div><dt>Input records</dt><dd>{String(report.input_records)}</dd></div>
                  <div><dt>Documents written</dt><dd>{String(report.documents_written)}</dd></div>
                  <div><dt>Chunks written</dt><dd>{String(report.chunks_written)}</dd></div>
                  <div><dt>Skipped (duplicate IDs / empty)</dt><dd>{String(report.skipped_duplicate_ids)} / {String(report.skipped_empty_documents)}</dd></div>
                  <div><dt>Duplicate texts removed</dt><dd>{String(report.removed_duplicate_texts)}</dd></div>
                  <div><dt>With judgment date / case number</dt><dd>{String(report.documents_with_judgment_date)} / {String(report.documents_with_case_number)}</dd></div>
                </dl>
              ) : <p className="field-hint">No ingestion report found. Re-run the ingestion CLI to produce one.</p>}
            </section>
          </div>
          <section className="panel"><div className="panel-heading"><div><span className="section-kicker">LAST 24 HOURS</span><h2>Usage</h2></div></div><UsageTable rows={data.usage_last_24h} /></section>
          <section className="panel"><div className="panel-heading"><div><span className="section-kicker">LAST 7 DAYS</span><h2>Usage</h2></div></div><UsageTable rows={data.usage_last_7d} /><p className="panel-note">Usage events record type, engine, outcome, and latency only — never query text.</p></section>
          <UserManagement />
        </>
      )}
    </div>
  );
}

const extensions = [
  { icon: BookOpenText, title: 'Judgment summarization', detail: 'Concise case briefs with paragraph-level citations.' },
  { icon: Activity, title: 'Case timeline', detail: 'Procedural history and event chronology across a matter.' },
  { icon: LockKeyhole, title: 'Document analyzer', detail: 'Structured clause, issue, and citation extraction.' },
  { icon: Languages, title: 'Multilingual research', detail: 'Hindi, Telugu, and Tamil query and corpus support.' },
  { icon: LayoutDashboard, title: 'Research analytics', detail: 'Additional analytics beyond the evaluation dashboard.' },
];

export function RoadmapPage() {
  return (
    <div className="subpage">
      <PageTitle eyebrow="ROADMAP" title="Future extensions." description="Ideas for future work. These are not implemented and are listed for transparency only." />
      <div className="roadmap-banner"><Sparkles size={18} /><span>Roadmap only</span><p>Nothing on this page is functional; it describes possible future work.</p></div>
      <div className="roadmap-grid">{extensions.map(({ icon: Icon, title, detail }, index) => <article className="roadmap-card" key={title}><div className="roadmap-card-top"><span className="roadmap-number">0{index + 1}</span><span className="roadmap-state">NOT BUILT</span></div><div className="roadmap-icon"><Icon size={20} /></div><h2>{title}</h2><p>{detail}</p></article>)}</div>
    </div>
  );
}
