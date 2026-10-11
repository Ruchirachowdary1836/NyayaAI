import { motion } from 'framer-motion';
import {
  BookOpenText,
  ChartNoAxesCombined,
  FolderLock,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  Scale,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Sun,
  UserRound,
  X,
} from 'lucide-react';
import { useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth';
import { useTheme } from '../lib/theme';

const researchLinks = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/search', label: 'Search & ask', icon: Search },
  { to: '/compare', label: 'Compare engines', icon: Scale },
  { to: '/experiments', label: 'Experiments', icon: ChartNoAxesCombined },
];

const libraryLinks = [
  { to: '/documents', label: 'Legal corpus', icon: BookOpenText },
  { to: '/library', label: 'My documents', icon: FolderLock },
];

const PAGE_NAMES: Record<string, string> = {
  dashboard: 'Dashboard',
  search: 'Search & ask',
  compare: 'Compare engines',
  experiments: 'Experiments',
  documents: 'Legal corpus',
  library: 'My documents',
  admin: 'Administration',
  profile: 'Profile',
  roadmap: 'Future extensions',
};

export function Shell() {
  const [menuOpen, setMenuOpen] = useState(false);
  const { dark, toggle } = useTheme();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const section = PAGE_NAMES[location.pathname.split('/')[1]] ?? 'Workspace';
  const close = () => setMenuOpen(false);

  const signOut = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  const link = ({ to, label, icon: Icon }: (typeof researchLinks)[number]) => (
    <NavLink
      key={to}
      to={to}
      className={({ isActive }) => `nav-link ${isActive ? 'nav-link-active' : ''}`}
      onClick={close}
    >
      <Icon size={17} strokeWidth={1.8} /><span>{label}</span>
    </NavLink>
  );

  return (
    <div className="app-frame">
      <button
        className="mobile-menu-button"
        aria-label={menuOpen ? 'Close navigation' : 'Open navigation'}
        aria-expanded={menuOpen}
        onClick={() => setMenuOpen((open) => !open)}
      >
        {menuOpen ? <X size={20} /> : <Menu size={20} />}
      </button>
      <aside className={`sidebar ${menuOpen ? 'sidebar-open' : ''}`}>
        <NavLink className="brand-lockup" to="/dashboard" onClick={close}>
          <span className="brand-mark"><Scale size={21} strokeWidth={1.7} /></span>
          <span className="brand-type">nyaya<span>ai</span></span>
        </NavLink>
        <div className="workspace-pill"><span className="workspace-dot" /> Legal research workspace</div>

        <nav aria-label="Main navigation">
          <p className="nav-eyebrow">Research</p>
          {researchLinks.map(link)}
          <p className="nav-eyebrow nav-eyebrow-spaced">Libraries</p>
          {libraryLinks.map(link)}
          <p className="nav-eyebrow nav-eyebrow-spaced">Account</p>
          {link({ to: '/profile', label: 'Profile & security', icon: UserRound })}
          {user?.role === 'admin' && link({ to: '/admin', label: 'Administration', icon: Settings2 })}
          {link({ to: '/roadmap', label: 'Future extensions', icon: Sparkles })}
        </nav>

        <div className="sidebar-bottom">
          <div className="sidebar-note">
            <ShieldCheck size={16} />
            <div><strong>Evidence first</strong><span>Every answer traces back to a source.</span></div>
          </div>
          <div className="sidebar-profile">
            <NavLink to="/profile" className="profile-identity" onClick={close}>
              <span className="avatar" aria-hidden>{user?.username.slice(0, 1).toUpperCase()}</span>
              <span className="profile-copy"><strong>{user?.username}</strong><span>{user?.role === 'admin' ? 'Administrator' : 'Researcher'}</span></span>
            </NavLink>
            <button className="icon-button" onClick={toggle} aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}>
              {dark ? <Sun size={17} /> : <Moon size={17} />}
            </button>
          </div>
        </div>
      </aside>

      {menuOpen && <button aria-label="Close menu overlay" className="mobile-scrim" onClick={close} />}

      <main className="main-panel">
        <header className="topbar">
          <div className="breadcrumb"><span>NyayaAI</span><span className="breadcrumb-slash">/</span><strong>{section}</strong></div>
          <div className="topbar-actions">
            <NavLink className="profile-link" to="/profile"><UserRound size={16} /><span>{user?.username}</span></NavLink>
            <button type="button" className="profile-link" onClick={signOut}><LogOut size={15} /><span>Sign out</span></button>
          </div>
        </header>
        <motion.div
          key={location.pathname}
          className="page-content"
          initial={{ opacity: 0, y: 7 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.22, ease: 'easeOut' }}
        >
          <Outlet />
        </motion.div>
        <footer className="global-disclaimer">
          <ShieldCheck size={14} />
          <span>NyayaAI supports legal research and is not a substitute for professional legal advice.</span>
          <span className="footer-separator">·</span><span>Built for transparent, reproducible research</span>
        </footer>
      </main>
    </div>
  );
}
