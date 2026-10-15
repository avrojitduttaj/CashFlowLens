# CashFlowLens

**Know what is coming in. Spot what is slipping. Follow up with confidence.**

CashFlowLens is a local-first cash-flow companion for freelancers and micro-agencies. Create an account, upload a CSV or Excel invoice export, and the API validates the data and calculates outstanding invoices, overdue balances, due-date-based inflows, and descriptive client payment-delay signals. An optional local Ollama/Gemma integration can explain aggregate results.

> **MVP/security note:** This is a development prototype, not production-ready financial software. Authentication uses a custom signed bearer token and PBKDF2 password hashes. Set a strong `CASHFLOWLENS_TOKEN_SECRET`, use HTTPS, add rate limiting, CSRF-safe deployment architecture, account recovery, and security review before public launch. Do not upload real financial data to a public deployment until its data handling has been reviewed.

## What works now

- Account registration and login with SQLite-backed user accounts
- Password hashing with PBKDF2-HMAC-SHA256 and expiring signed bearer tokens
- Authenticated CSV / XLSX / XLS upload (8 MB limit)
- Server-side schema validation and deterministic invoice analytics
- Dynamic dashboard based on the uploaded file, not hardcoded sample metrics
- Expected inflows by due date for the next 30 days
- Client payment-delay summaries based on paid invoices with a paid date
- Follow-up email drafts for unpaid invoices
- Optional Gemma explanation endpoint, using aggregated metrics rather than raw invoice rows
- Invoice file content is analyzed in request memory and is not saved by the API; user accounts are stored in SQLite

## Run locally

Use two terminals.

### 1. Backend (Python 3.11+ recommended)

```bash
cd backend
python -m venv .venv
# Windows PowerShell:
.venv\\Scripts\\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env  # Windows; on macOS/Linux use: cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Change `CASHFLOWLENS_TOKEN_SECRET` in `backend/.env` to a long random value before exposing the service. The SQLite database is created automatically at `backend/cashflowlens.sqlite3` by default.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL (normally `http://localhost:5173`). Optionally set `VITE_API_URL` in `frontend/.env` if the API is not at `http://localhost:8000`.

### 3. Optional local Gemma

Install Ollama separately, pull a Gemma model (default `gemma3:4b`), and make sure Ollama is reachable at `OLLAMA_BASE_URL`. Core upload and analytics work without AI. The UI's “Explain with Gemma” action will report a clear service error if Ollama is unavailable.

## File format

Required columns (case-insensitive; spaces in headers are converted to underscores):

- `client`
- `invoice_date`
- `due_date`
- `amount`
- `status`

Optional: `invoice_id`, `paid_date`. Some common aliases such as `client_name`, `customer`, `invoice_number`, `total`, `invoice_amount`, `payment_status`, `paid_on`, and `payment_date` are recognized. ISO dates (`YYYY-MM-DD`) are recommended. Statuses `paid`, `complete`, or `completed` are treated as paid; a valid `paid_date` also marks an invoice as paid.

A sample file is available at `sample-data/invoices.csv` and through the app's upload empty state.

## API overview

- `GET /health` — health check
- `POST /api/auth/register` — create an account
- `POST /api/auth/login` — authenticate
- `GET /api/auth/me` — current user (Bearer token)
- `POST /api/analytics/upload` — authenticated CSV/XLSX analysis (multipart field `file`)
- `POST /api/explain` — authenticated optional Ollama/Gemma explanation of aggregate metrics

Interactive API docs: `http://localhost:8000/docs`.

## Analytics caveats

- Expected inflows are the sum of unpaid invoices with due dates within the next 30 days, not a probability-weighted forecast.
- Payment-delay summaries are descriptive and use only paid invoices with valid `paid_date` values.
- Small samples can be misleading. This MVP does not provide financial, accounting, or tax advice.

## Next steps

- Add tests for auth, file parsing, analytics, and malformed spreadsheets
- Add column mapping and more export-specific header aliases
- Add robust rate limiting, secure session management, and account recovery before public deployment
- Benchmark TabPFN against a transparent baseline on a suitable tabular payment-delay task
- Gather real first-user feedback with consent

## License

MIT. See [LICENSE](LICENSE).
