import { ChevronLeft, ChevronRight, LoaderCircle, TriangleAlert } from 'lucide-react';
import type { ReactNode } from 'react';

export function PageTitle({ eyebrow, title, description, actions }: { eyebrow: string; title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="subpage-heading">
      <div className="subpage-heading-row">
        <div>
          <div className="eyebrow"><span className="eyebrow-line" /> {eyebrow}</div>
          <h1>{title}</h1>
        </div>
        {actions && <div className="heading-actions">{actions}</div>}
      </div>
      {description && <p>{description}</p>}
    </div>
  );
}

export function ErrorState({ message, title = 'Couldn’t load this information', onRetry }: { message: string; title?: string; onRetry?: () => void }) {
  return (
    <div className="error-banner" role="alert">
      <TriangleAlert size={17} />
      <div>
        <strong>{title}</strong>
        <span>{message}</span>
        {onRetry && <button type="button" className="text-action" onClick={onRetry}>Try again</button>}
      </div>
    </div>
  );
}

export function LoadingCard({ label }: { label: string }) {
  return <div className="loading-card" role="status"><LoaderCircle className="spin" aria-hidden /> {label}</div>;
}

export function EmptyState({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return <div className="empty-state-card">{icon}<h2>{title}</h2>{children}</div>;
}

export function Pagination({ page, pageSize, total, onPage, capped = false }: { page: number; pageSize: number; total: number; onPage: (page: number) => void; capped?: boolean }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total <= pageSize && page === 1) return null;
  return (
    <nav className="pagination" aria-label="Pagination">
      <button type="button" className="secondary-button" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        <ChevronLeft size={14} /> Previous
      </button>
      <span>Page {page} of {pages}{capped ? '+' : ''}</span>
      <button type="button" className="secondary-button" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Next <ChevronRight size={14} />
      </button>
    </nav>
  );
}

export function StatusBadge({ tone, children }: { tone: 'ok' | 'warn' | 'error' | 'muted'; children: ReactNode }) {
  return <span className={`status-badge status-${tone}`}>{children}</span>;
}

export function StatCard({ icon, label, value, detail }: { icon: ReactNode; label: string; value: ReactNode; detail?: ReactNode }) {
  return <div className="admin-metric">{icon}<span>{label}</span><strong>{value}</strong>{detail && <small>{detail}</small>}</div>;
}
