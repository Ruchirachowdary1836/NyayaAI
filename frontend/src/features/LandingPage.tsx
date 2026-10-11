import { useQuery } from '@tanstack/react-query';
import { ArrowRight, BookOpenText, ChartNoAxesCombined, FileSearch, FolderLock, Layers3, ShieldCheck, Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';
import { api } from '../lib/api';
import { useAuth } from '../lib/auth';
import { ENGINE_LABELS } from '../lib/format';

const features = [
  { icon: FileSearch, title: 'Search judgments and statutes', text: 'BM25, dense, and hybrid retrieval over an attributed Indian legal corpus, with filters by type and year.' },
  { icon: Sparkles, title: 'Grounded answers', text: 'Answers cite numbered source passages. Uncited or invalid citations are withheld, never filled in.' },
  { icon: Layers3, title: 'Compare retrieval methods', text: 'Run one query through every enabled engine and inspect rankings, latency, and overlap side by side.' },
  { icon: ChartNoAxesCombined, title: 'Reproducible experiments', text: 'Save retrieval experiments with your own relevance judgments and review MAP, MRR, and nDCG.' },
  { icon: FolderLock, title: 'Private document library', text: 'Upload PDFs and text files, search them, and keep them visible only to your account.' },
  { icon: BookOpenText, title: 'Traceable sources', text: 'Every result links to the full judgment with court, date, case number, and licence.' },
];

export function LandingPage() {
  const { status } = useAuth();
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, retry: false });
  const ready = health.data?.status === 'ready';
  return (
    <div className="landing">
      <section className="landing-hero">
        <div className="eyebrow"><span className="eyebrow-line" /> INDIAN LEGAL RESEARCH</div>
        <h1>Find the law.<br /><em>Follow the evidence.</em></h1>
        <p>NyayaAI is an evidence-first research workspace for Indian case law and statutes. Every result and every answer traces back to a source you can open and check.</p>
        <div className="landing-actions">
          {status === 'authenticated' ? (
            <Link className="primary-button large" to="/dashboard">Open your workspace <ArrowRight size={16} /></Link>
          ) : (
            <>
              <Link className="primary-button large" to="/register">Create a free account <ArrowRight size={16} /></Link>
              <Link className="secondary-button large" to="/login">Sign in</Link>
            </>
          )}
        </div>
        <div className="landing-status" aria-live="polite">
          {health.isLoading && <span>Checking the research service…</span>}
          {health.isError && <span>The research service is not reachable right now.</span>}
          {health.data && !ready && <span>The research service is starting up…</span>}
          {ready && (
            <>
              <span><strong>{health.data?.corpus_documents?.toLocaleString()}</strong> indexed documents</span>
              <span><strong>{health.data?.corpus_chunks?.toLocaleString()}</strong> searchable passages</span>
              <span>Engines: <strong>{(health.data?.available_retrievers ?? []).map((name) => ENGINE_LABELS[name]).join(', ')}</strong></span>
            </>
          )}
        </div>
      </section>
      <section className="landing-grid" aria-label="Features">
        {features.map(({ icon: Icon, title, text }) => (
          <article key={title} className="landing-card"><Icon size={20} /><h2>{title}</h2><p>{text}</p></article>
        ))}
      </section>
      <section className="research-note landing-note">
        <ShieldCheck size={16} />
        <p>The hosted corpus is the AILA 2019 precedent and statute collection (<a href="https://doi.org/10.5281/zenodo.4063986" target="_blank" rel="noreferrer">CC BY 4.0</a>), a research snapshot rather than a complete or current legal database. Verify findings against authoritative sources. NyayaAI is not legal advice.</p>
      </section>
    </div>
  );
}
