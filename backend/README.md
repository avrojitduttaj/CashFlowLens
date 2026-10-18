# CashFlowLens API

Authenticated FastAPI service for invoice validation, deterministic cash-flow analytics, and structured local Gemma briefs.

## Endpoints

- `GET /health` — service health
- `POST /api/auth/register` and `POST /api/auth/login` — create or sign in to a workspace
- `GET /api/auth/me` — current authenticated user
- `POST /api/analytics/upload` — analyze a CSV or Excel invoice export
- `POST /api/explain` — generate the core cash-flow brief with the configured Ollama model
- `POST /api/payment-risk/upload` — separate experimental payment-risk analysis

All analysis routes require a bearer token. Uploads are processed in memory and invoice rows are not persisted by the API; SQLite stores user accounts. Before the brief is sent to Ollama, the API reduces deterministic metrics to qualitative state signals. Exact amounts, counts, client names, invoice identifiers, dates, and invoice-level rows are excluded. Gemma selects only from allowed focus/action identifiers, and the API returns server-rendered copy; it never displays free-form model prose as financial guidance.

## Local model

Run Ollama locally and download the default open-weight model:

```bash
ollama pull gemma3:4b
```

Configure `OLLAMA_BASE_URL` (default `http://127.0.0.1:11434`) and `OLLAMA_MODEL` (default `gemma3:4b`) in `.env`. The API rejects non-loopback endpoints, non-Gemma model names, and cloud aliases; it also disables inherited HTTP proxy settings for the Ollama request. The frontend automatically requests a brief after successful invoice analysis; if Ollama is offline or returns invalid structured output, the API reports an error and deterministic analytics remain available.

## Tests

```bash
python -m pytest
```
