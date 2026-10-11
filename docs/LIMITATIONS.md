# Limitations and caveats

NyayaAI is a research tool. These limits are deliberate to state plainly.

## Data

- The hosted corpus is the AILA 2019 precedent and statute collection (CC BY 4.0): 2,914
  Supreme Court judgments and 197 statute sections. It is a research snapshot, not a complete or
  current legal database. Verify findings against authoritative, current sources.
- Judgment dates and case numbers are parsed from each judgment's own header lines. Dates were
  found for all judgments; case numbers for about 93%. Statutes carry no dates, so year filters
  exclude them. Nothing is inferred when a header is missing.
- AILA's 50 queries and relevance judgments limit how far the benchmark generalizes.

## Retrieval

- Search filters and date sorting operate on a relevance-ranked candidate pool (100 chunks,
  widened up to 6,400 when filters leave too few). `total` is the count within that pool and is
  marked `total_is_capped` when the pool was full.
- Dense retrieval needs the optional `dense` dependencies and enough memory/CPU. Embedding the
  full corpus with `all-MiniLM-L6-v2` on a laptop CPU takes on the order of an hour; the result
  is cached. That model reads only the first 256 word pieces of each ~480-token chunk.
  The free Render plan runs BM25 only.
- Hybrid fusion parameters (`HYBRID_METHOD`, `HYBRID_ALPHA`, `HYBRID_RRF_K`) can be sensitive to
  query type and corpus.

## Answer generation

- Answers are only as good as the retrieved passages and the configured model. Small local
  models frequently decline or answer without citations; NyayaAI then withholds the answer
  rather than showing ungrounded text.
- Citation auditing checks that cited passage numbers exist and that sentences carry citations;
  it cannot prove that a cited passage semantically supports the sentence. Review sources.
- Generated text is legal information, not legal advice.

## Platform

- Rate limits are per process. A multi-instance deployment needs a shared limiter (e.g. Redis).
- Uploaded files are stored in the database (≤ 5 MB each, 200 per user). Scanned PDFs without a
  text layer are stored but marked as failed; OCR is not performed.
- Library search builds an in-memory BM25 index per user on demand.
- Experiment metrics treat the supplied relevant IDs as binary judgments; IDs absent from the
  corpus still count as relevant and are listed in the results.
