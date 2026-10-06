# Data directory

This directory is reserved for the legal corpus, processed chunks, and index artifacts.

The raw sources are intentionally not stored in git. Each dataset should be fetched and transformed with reproducible scripts in later phases of the project.

## Supported ingestion inputs

Place authorized data under `data/raw/` and point `configs/data.yaml` to the corpus. The ingestion CLI accepts `.json`, `.jsonl`, and `.csv` files:

- **Case documents:** an identifier (`doc_id`, `document_id`, `judgment_id`, `case_id`, or `id`) and text (`judgment_text`, `document_text`, `full_text`, `content`, `text`, `judgment`, or `body`). Optional fields such as `court`, `year`, and `citation` are retained as metadata.
- **AILA queries:** an ID (`query_id`, `topic_id`, or `id`) and text (`query`, `question`, `text`, or `title`).
- **AILA qrels:** `query_id`/`topic_id`/`qid`, `doc_id`/`document_id`/`judgment_id`/`docno`, and `relevance`/`relevance_grade`/`score`/`label`.
- **Legal QA:** a question (`question`, `query`, or `prompt`) and answer (`answer`, `reference_answer`, or `response`).

The normalized formats are an ingestion contract, not a claim that upstream dataset releases share one schema. Convert source exports as needed and retain their license/attribution information. Never publish restricted raw content or derived text unless its terms permit redistribution.
