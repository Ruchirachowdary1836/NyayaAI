# Evaluation protocol

NyayaAI uses a strict, reproducible evaluation workflow for retrieval and answer quality.

## Retrieval evaluation

- Primary corpus: AILA precedent and statute retrieval data.
- Supplementary corpus: ILDC and legal QA datasets.
- Metrics: Precision@k, Recall@k, MAP, MRR, and nDCG.
- Statistical tests: paired t-test, Wilcoxon signed-rank, effect size, and bootstrap confidence intervals.
- The Render image calculates and records a BM25-only baseline from the AILA 2019 official 50 queries and relevance judgments. Prior-case and statute tasks are evaluated against their own judged document pools. The dashboard reports the 100 task-query evaluations and source attribution; it does not imply dense/hybrid results.

## Answer evaluation

- ROUGE/BLEU where reference answers exist.
- Faithfulness and hallucination evaluation using claim-to-passage entailment.
- Citation precision checks against the retrieved passages.
- Human review rubric for legal correctness on a 5-point scale.

## Reproducibility

- Seed values are fixed in config.
- Retrieval and QA conditions share the same corpus, prompt, and decoding parameters.
- `configs/experiment.yaml` records corpus/query/qrels inputs and retrieval settings.
- `make experiment` writes a configuration hash, per-query CSV, metrics JSON, paired t-tests, Wilcoxon results, and bootstrap intervals to `evaluation/results/<run_id>/`, and logs parameters, aggregate metrics, and artifacts to MLflow.
- MLflow uses `tracking.tracking_uri` from `configs/experiment.yaml`; `MLFLOW_TRACKING_URI` overrides it for deployments such as Docker Compose. Run or inspect the configured tracking server before starting an experiment; tracking failures are surfaced.
- Holm-Bonferroni adjustment is applied across paired metric comparisons.
- The full experiment command requires licensed, locally prepared corpus chunks, queries, qrels, the configured sentence-transformer model, and an available MLflow store. Do not treat toy tests as benchmark results.

## Running a retrieval experiment

1. Ingest an authorized corpus and configure query and relevance-judgment paths in `configs/data.yaml`. The Render build extracts AILA's official benchmark files from the same checksum-verified archive.
2. Set corpus/query/qrels paths and fixed run parameters in `configs/experiment.yaml`.
3. Run `make experiment`; generated legal text remains gitignored.
4. The dashboard reads generated metrics files without synthesizing missing results. The hosted BM25 seed run is produced by `evaluation.seed_aila_benchmark`; dense/hybrid scores require an actual full experiment.

## Measured three-engine comparison (2026-10-11)

Run through the platform's experiment API (`POST /api/v1/experiments/runs`) on the full ingested
AILA 2019 corpus (3,111 documents, 24,178 chunks), all 50 official prior-case queries with their
binary relevance judgments, k = 10 documents per query (best passage per document from a 40-chunk
pool). Dense used `sentence-transformers/all-MiniLM-L6-v2`; hybrid used RRF (k = 60).

| Engine | MAP | MRR | nDCG@10 | Recall@10 |
|---|---|---|---|---|
| BM25 | 0.0886 | 0.1576 | 0.1227 | 0.1443 |
| Dense (MiniLM) | 0.0467 | 0.0850 | 0.0680 | 0.0795 |
| Hybrid (RRF) | 0.0569 | 0.1033 | 0.0733 | 0.0773 |

BM25 agrees with the recorded offline baseline (MAP 0.0854; the small difference comes from the
document-level pooling protocol). The small general-purpose embedding model, which reads only the
first 256 word pieces of each chunk, underperforms lexical matching on AILA's long fact-pattern
queries, and RRF fusion with it does not recover BM25's quality. A legal-domain or longer-context
embedding model is needed before dense or hybrid retrieval should be preferred on this task.
These figures are from a single run with no significance testing.
