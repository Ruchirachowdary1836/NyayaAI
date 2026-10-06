export default function App() {
  return (
    <main className="min-h-screen bg-paper text-slate-900 antialiased">
      <div className="mx-auto flex max-w-6xl flex-col gap-8 px-6 py-16">
        <header className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-gold">NyayaAI</p>
          <h1 className="mt-4 font-display text-4xl text-navy md:text-6xl">
            Legal research that stays evidence-first.
          </h1>
          <p className="mt-4 max-w-2xl text-lg text-slate-600">
            Hybrid retrieval for Indian precedent and statutes, with attributable citations and a strict assistive-use disclaimer.
          </p>
        </header>

        <section className="grid gap-6 md:grid-cols-3">
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="font-display text-2xl text-navy">BM25</h2>
            <p className="mt-3 text-slate-600">Lexical baseline for statute and case retrieval.</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="font-display text-2xl text-navy">Dense</h2>
            <p className="mt-3 text-slate-600">Semantic matching via sentence embeddings and FAISS.</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="font-display text-2xl text-navy">Hybrid</h2>
            <p className="mt-3 text-slate-600">RRF and weighted fusion with explainable score provenance.</p>
          </div>
        </section>
      </div>
    </main>
  );
}
