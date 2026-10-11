import { LoaderCircle } from 'lucide-react';
import { Navigate, Outlet, useLocation, useSearchParams } from 'react-router-dom';
import { useAuth } from '../lib/auth';

function SessionCheck() {
  return <div className="session-check" role="status"><LoaderCircle className="spin" /> Restoring your session…</div>;
}

/** Renders child routes only for signed-in users; others are sent to sign in and returned afterwards. */
export function RequireAuth() {
  const { status } = useAuth();
  const location = useLocation();
  if (status === 'loading') return <SessionCheck />;
  if (status === 'anonymous') {
    const next = `${location.pathname}${location.search}`;
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />;
  }
  return <Outlet />;
}

/** UI guard for admin pages. The API enforces the same rule independently. */
export function RequireAdmin() {
  const { user } = useAuth();
  if (user?.role !== 'admin') return <Navigate to="/dashboard" replace state={{ denied: true }} />;
  return <Outlet />;
}

/** Sign-in and registration pages redirect signed-in users to their dashboard. */
export function AnonymousOnly() {
  const { status } = useAuth();
  const [params] = useSearchParams();
  if (status === 'loading') return <SessionCheck />;
  // Honour ?next= here too: this guard re-renders as soon as sign-in succeeds.
  if (status === 'authenticated') return <Navigate to={safeNext(params.get('next'))} replace />;
  return <Outlet />;
}

export function safeNext(value: string | null): string {
  // Only allow same-app relative paths. Backslashes are rejected because browsers treat
  // "/\host" like "//host" (open redirect; see React Router advisory GHSA-wrjc-x8rr-h8h6).
  return value && /^\/(?![/\\])[^\\\s]*$/.test(value) ? value : '/dashboard';
}
