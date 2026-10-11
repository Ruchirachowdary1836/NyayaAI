import { Moon, Scale, ShieldCheck, Sun } from 'lucide-react';
import { Link, Outlet } from 'react-router-dom';
import { useAuth } from '../lib/auth';
import { useTheme } from '../lib/theme';

export function PublicLayout() {
  const { status } = useAuth();
  const { dark, toggle } = useTheme();
  return (
    <div className="public-frame">
      <header className="public-header">
        <Link className="brand-lockup" to="/">
          <span className="brand-mark"><Scale size={21} strokeWidth={1.7} /></span>
          <span className="brand-type">nyaya<span>ai</span></span>
        </Link>
        <nav className="public-nav" aria-label="Site">
          {status === 'authenticated' ? (
            <Link className="primary-button" to="/dashboard">Open workspace</Link>
          ) : (
            <>
              <Link className="text-link" to="/login">Sign in</Link>
              <Link className="primary-button" to="/register">Create account</Link>
            </>
          )}
          <button className="icon-button" onClick={toggle} aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}>
            {dark ? <Sun size={17} /> : <Moon size={17} />}
          </button>
        </nav>
      </header>
      <main className="public-main"><Outlet /></main>
      <footer className="global-disclaimer">
        <ShieldCheck size={14} />
        <span>NyayaAI supports legal research and is not a substitute for professional legal advice.</span>
      </footer>
    </div>
  );
}
