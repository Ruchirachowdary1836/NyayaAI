import { motion } from 'framer-motion';
import {
  Activity,
  ArrowUpRight,
  BookOpenText,
  ChartNoAxesCombined,
  Command,
  FileSearch,
  FlaskConical,
  Gavel,
  Github,
  Languages,
  LayoutDashboard,
  Menu,
  Moon,
  Scale,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Sun,
  X,
} from 'lucide-react';
import { useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';

const mainLinks = [
  { to: '/', label: 'Research workspace', icon: Search },
  { to: '/compare', label: 'Compare engines', icon: Scale },
  { to: '/experiments', label: 'Experiments', icon: ChartNoAxesCombined },
];

const otherLinks = [
  { to: '/documents', label: 'Document library', icon: BookOpenText },
  { to: '/admin', label: 'System health', icon: Settings2 },
  { to: '/roadmap', label: 'Future extensions', icon: Sparkles },
];

export function Shell() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [dark, setDark] = useState(() => localStorage.getItem('nyaya-theme') === 'dark');

  const toggleTheme = () => {
    const next = !dark;
    setDark(next);
    localStorage.setItem('nyaya-theme', next ? 'dark' : 'light');
    document.documentElement.dataset.theme = next ? 'dark' : 'light';
  };

  return (
    <div className={`app-frame ${dark ? 'dark-mode' : ''}`}>
      <button
        className="mobile-menu-button"
        aria-label={menuOpen ? 'Close navigation' : 'Open navigation'}
        onClick={() => setMenuOpen((open) => !open)}
      >
        {menuOpen ? <X size={20} /> : <Menu size={20} />}
      </button>
      <aside className={`sidebar ${menuOpen ? 'sidebar-open' : ''}`}>
        <NavLink className="brand-lockup" to="/" onClick={() => setMenuOpen(false)}>
          <span className="brand-mark"><Scale size={21} strokeWidth={1.7} /></span>
          <span className="brand-type">nyaya<span>ai</span></span>
        </NavLink>
        <div className="workspace-pill"><span className="workspace-dot" /> Legal research workspace</div>

        <nav aria-label="Main navigation">
          <p className="nav-eyebrow">Research</p>
          {mainLinks.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) => `nav-link ${isActive ? 'nav-link-active' : ''}`}
              onClick={() => setMenuOpen(false)}
            >
              <Icon size={17} strokeWidth={1.8} /><span>{label}</span>
              {label === 'Research workspace' && <span className="shortcut">⌘ K</span>}
            </NavLink>
          ))}
          <p className="nav-eyebrow nav-eyebrow-spaced">Workspace</p>
          {otherLinks.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) => `nav-link ${isActive ? 'nav-link-active' : ''}`}
              onClick={() => setMenuOpen(false)}
            >
              <Icon size={17} strokeWidth={1.8} /><span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="sidebar-note">
            <ShieldCheck size={16} />
            <div><strong>Evidence first</strong><span>Every answer traces back to a source.</span></div>
          </div>
          <div className="sidebar-profile">
            <div className="avatar">R</div>
            <div className="profile-copy"><strong>Researcher</strong><span>Local workspace</span></div>
            <button className="icon-button" onClick={toggleTheme} aria-label="Toggle color theme">
              {dark ? <Sun size={17} /> : <Moon size={17} />}
            </button>
          </div>
        </div>
      </aside>

      {menuOpen && <button aria-label="Close menu overlay" className="mobile-scrim" onClick={() => setMenuOpen(false)} />}

      <main className="main-panel">
        <header className="topbar">
          <div className="breadcrumb"><span>NyayaAI</span><span className="breadcrumb-slash">/</span><strong>Research & discovery</strong></div>
          <div className="topbar-actions">
            <div className="environment-badge"><span /> Research environment</div>
            <a className="icon-button github-link" href="https://github.com/Ruchirachowdary1836/NyayaAI" target="_blank" rel="noreferrer" aria-label="Open GitHub repository">
              <Github size={18} />
            </a>
            <div className="avatar avatar-small">R</div>
          </div>
        </header>
        <motion.div
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
