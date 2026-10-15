# CashFlowLens API

Local FastAPI service for CSV analytics and optional Ollama/Gemma narrative explanations.

- `GET /health`
- `POST /api/analytics` with a CSV file field named `file`
- `POST /api/explain` with aggregated figures only; raw invoice rows should not be sent to the LLM

The API does not persist uploads. The current frontend demo performs its own CSV parsing in-browser and is not yet wired to these endpoints.
