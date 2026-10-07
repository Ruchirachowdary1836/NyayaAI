# Limitations and caveats

The project is designed to be transparent about model and data limitations.

- AILA query counts remain limited and may constrain breadth of generalization.
- Fusion weights can be sensitive to document distribution and query type.
- Retrieval quality depends on chunking choices and index versioning.
- Generated answers are assistive only and must not substitute for legal counsel.
- Licensing restrictions may limit the public release of raw legal corpora.
- The hosted AILA 2019 corpus is a CC BY 4.0 research snapshot, not a complete or current legal database; verify retrieved text against authoritative, current sources.
- Dense retrieval requires the configured sentence-transformer model; model download, runtime, and hardware are not hidden behind mock fallbacks.
- Direct local development uses SQLite; Compose uses PostgreSQL for users and feedback. Rate limits are per process, so multi-instance deployment requires a shared limiter.
- The shipped frontend is a research interface, not a legal workflow management system; role-based access protects the local administration endpoints.
