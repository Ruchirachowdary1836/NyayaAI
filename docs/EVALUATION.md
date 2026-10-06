# Evaluation protocol

NyayaAI uses a strict, reproducible evaluation workflow for retrieval and answer quality.

## Retrieval evaluation

- Primary corpus: AILA precedent and statute retrieval data.
- Supplementary corpus: ILDC and legal QA datasets.
- Metrics: Precision@k, Recall@k, MAP, MRR, and nDCG.
- Statistical tests: paired t-test, Wilcoxon signed-rank, effect size, and bootstrap confidence intervals.

## Answer evaluation

- ROUGE/BLEU where reference answers exist.
- Faithfulness and hallucination evaluation using claim-to-passage entailment.
- Citation precision checks against the retrieved passages.
- Human review rubric for legal correctness on a 5-point scale.

## Reproducibility

- Seed values are fixed in config.
- Retrieval and QA conditions share the same corpus, prompt, and decoding parameters.
- Logging to MLflow persists config hashes, experiment IDs, and results for comparison.
