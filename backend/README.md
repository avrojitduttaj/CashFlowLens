# CashFlowLens API

Authenticated FastAPI service for invoice validation, deterministic cash-flow analytics, and structured Gemma briefs.

## Endpoints

- `GET /health` — service health
- `POST /api/auth/register` and `POST /api/auth/login` — create or sign in to a workspace
- `GET /api/auth/me` — current authenticated user
- `POST /api/analytics/upload` — analyze a CSV or Excel invoice export
- `POST /api/explain` — generate the core cash-flow brief with the configured Ollama model
- `POST /api/payment-risk/upload` — separate experimental payment-risk analysis

All analysis routes require a bearer token. Uploads are processed in memory and invoice rows are not persisted by the API; SQLite stores user accounts. Before the brief is sent to Ollama, the API reduces deterministic metrics to qualitative state signals. Exact amounts, counts, client names, invoice identifiers, dates, and invoice-level rows are excluded. Gemma selects only from allowed focus/action identifiers, and the API returns server-rendered copy; it never displays free-form model prose as financial guidance. `backend/app/payment_risk.py` contains no Ollama request or configuration path.

## Local model

Run Ollama locally and download the default open-weight model:

```bash
ollama pull gemma3:4b
```

For local development, `OLLAMA_BASE_URL` defaults to `http://127.0.0.1:11434` and `OLLAMA_MODEL` defaults to `gemma3:4b`. Local Ollama is restricted to loopback HTTP and ignores `OLLAMA_API_KEY`.

For a remote Ollama-compatible gateway, set `CASHFLOWLENS_ENV=production`, `OLLAMA_BASE_URL` to the gateway's HTTPS base URL, and `OLLAMA_API_KEY` in the backend's secret manager. The backend appends `/api/generate` and sends the key only in the outbound `Authorization: Bearer ...` header. Never put the key in frontend configuration. Remote HTTP, remote endpoints outside production mode, localhost HTTPS, URL userinfo/query credentials, and missing or malformed API keys are rejected. Use a gateway that supports Ollama's generate API and JSON-schema `format` option. Do not expose port 11434 publicly; keep Ollama private behind the secured gateway.

Requests use a 10-second connection timeout and bounded read/write/pool timeouts. Upstream response bodies and credential values are not included in API errors or logs. If Ollama is unavailable or returns invalid structured output, the API reports an error and deterministic analytics remain available. The remote gateway path has not been tested against a real provider; verify its URL, authentication, TLS, model availability, and structured-output support before production use.

## Tests

```bash
python -m pytest
```
