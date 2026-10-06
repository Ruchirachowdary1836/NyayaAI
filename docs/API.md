# API contract

The backend exposes a typed API for legal search, answer generation, comparison, and evaluation.

## Endpoints

- POST /api/v1/search
- POST /api/v1/compare
- POST /api/v1/qa
- GET /api/v1/qa/stream
- GET /api/v1/documents/{id}
- GET /api/v1/experiments
- GET /api/v1/experiments/{run_id}
- POST /api/v1/feedback
- GET /health
- GET /ready

## Safety and trust requirements

- JWT-based authentication with user/admin roles.
- Rate limiting and request-ID logging.
- Caching for repeated queries.
- A visible disclaimer in every API answer payload.
- Strict evidence check before returning generated responses.
