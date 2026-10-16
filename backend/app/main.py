from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
import secrets
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr
from app.payment_risk import (
    benchmark_models,
    predict_unpaid_invoices,
    prepare_labeled_history,
)

load_dotenv()
ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("CASHFLOWLENS_DB", str(ROOT / "cashflowlens.sqlite3")))
TOKEN_SECRET = os.getenv("CASHFLOWLENS_TOKEN_SECRET", "dev-only-change-this-secret-before-deploying").encode()
TOKEN_TTL = 60 * 60 * 12
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
app = FastAPI(title="CashFlowLens API", version="0.2.0", description="Authenticated invoice analytics with optional local Gemma explanations.")
origins = os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in origins if o.strip()], allow_credentials=False, allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Authorization", "Content-Type"])

REQUIRED = {"client", "invoice_date", "due_date", "amount", "status"}
PAID = {"paid", "complete", "completed"}

class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class ExplainRequest(BaseModel):
    summary: dict[str, Any] = Field(description="Aggregated figures only; avoid personal/client details")
    model: str | None = None

class ForecastPoint(BaseModel):
    date: str
    expected_inflow: float
    invoice_count: int

class ClientSignal(BaseModel):
    client: str
    paid_invoice_count: int
    average_days_late: float
    late_invoice_count: int
    evidence_note: str

class AnalyticsResponse(BaseModel):
    invoice_count: int
    outstanding_total: float
    overdue_total: float
    overdue_count: int
    expected_30_day_inflow: float
    forecast: list[ForecastPoint]
    client_signals: list[ClientSignal]
    caveats: list[str]
    invoices: list[dict[str, Any]]

class AuthUser(BaseModel):
    id: int
    email: str
    created_at: str


def db() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, salt TEXT NOT NULL, created_at TEXT NOT NULL)")
init_db()


def password_hash(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000).hex()


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def make_token(user_id: int, email: str) -> str:
    payload = b64(json.dumps({"sub": user_id, "email": email, "exp": int(time.time()) + TOKEN_TTL}, separators=(",", ":")).encode())
    signature = b64(hmac.new(TOKEN_SECRET, payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{signature}"


def current_user(authorization: str | None = Header(default=None)) -> AuthUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Please log in to continue.")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload, signature = token.split(".", 1)
        expected = b64(hmac.new(TOKEN_SECRET, payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if int(claims["exp"]) < int(time.time()):
            raise ValueError("expired")
        with db() as conn:
            row = conn.execute("SELECT id, email, created_at FROM users WHERE id = ?", (int(claims["sub"]),)).fetchone()
        if not row:
            raise ValueError("user")
        return AuthUser(**dict(row))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Your session is invalid or expired. Please log in again.") from exc


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "cashflowlens-api"}


@app.post("/api/auth/register")
def register(credentials: Credentials) -> dict[str, Any]:
    email = str(credentials.email).strip().lower()
    salt = secrets.token_bytes(16)
    created_at = datetime.now(timezone.utc).isoformat()
    try:
        with db() as conn:
            cursor = conn.execute("INSERT INTO users (email, password_hash, salt, created_at) VALUES (?, ?, ?, ?)", (email, password_hash(credentials.password, salt), salt.hex(), created_at))
            user_id = int(cursor.lastrowid)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="An account with this email already exists. Try logging in.") from exc
    user = AuthUser(id=user_id, email=email, created_at=created_at)
    return {"access_token": make_token(user_id, email), "token_type": "bearer", "user": user}


@app.post("/api/auth/login")
def login(credentials: Credentials) -> dict[str, Any]:
    email = str(credentials.email).strip().lower()
    with db() as conn:
        row = conn.execute("SELECT id, email, password_hash, salt, created_at FROM users WHERE email = ?", (email,)).fetchone()
    if not row or not hmac.compare_digest(password_hash(credentials.password, bytes.fromhex(row["salt"])), row["password_hash"]):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    user = AuthUser(id=row["id"], email=row["email"], created_at=row["created_at"])
    return {"access_token": make_token(user.id, user.email), "token_type": "bearer", "user": user}


@app.get("/api/auth/me", response_model=AuthUser)
def me(user: AuthUser = Depends(current_user)) -> AuthUser:
    return user


def parse_upload(raw: bytes, filename: str) -> pd.DataFrame:
    try:
        if filename.lower().endswith(".csv"):
            frame = pd.read_csv(io.BytesIO(raw))
        elif filename.lower().endswith((".xlsx", ".xls")):
            frame = pd.read_excel(io.BytesIO(raw))
        else:
            raise HTTPException(status_code=415, detail="Upload a .csv or .xlsx file.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="We couldn't read this file. Check that it is a valid CSV or Excel workbook.") from exc
    frame.columns = [str(c).strip().lower().replace(" ", "_") for c in frame.columns]
    # A few friendly header aliases for common exports.
    aliases = {"client_name": "client", "customer": "client", "invoice_number": "invoice_id", "invoice": "invoice_id", "invoice_date": "invoice_date", "due": "due_date", "due_date": "due_date", "total": "amount", "invoice_amount": "amount", "payment_status": "status", "paid_on": "paid_date", "payment_date": "paid_date"}
    frame = frame.rename(columns={c: aliases[c] for c in frame.columns if c in aliases and aliases[c] not in frame.columns})
    missing = REQUIRED - set(frame.columns)
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing required columns: {', '.join(sorted(missing))}. Required: client, invoice_date, due_date, amount, status.")
    if frame.empty:
        raise HTTPException(status_code=422, detail="The file contains no invoice rows.")
    frame["client"] = frame["client"].fillna("").astype(str).str.strip()
    frame["status"] = frame["status"].fillna("unpaid").astype(str).str.strip().str.lower()
    frame["amount"] = pd.to_numeric(frame["amount"].astype(str).str.replace(r"[$,£€₹]", "", regex=True).str.strip(), errors="coerce")
    for column in ("invoice_date", "due_date"):
        frame[column] = pd.to_datetime(frame[column], errors="coerce").dt.date
    if "paid_date" in frame.columns:
        frame["paid_date"] = pd.to_datetime(frame["paid_date"], errors="coerce").dt.date
    else:
        frame["paid_date"] = None
    if frame["client"].eq("").any() or frame["amount"].isna().any() or frame["due_date"].isna().any():
        raise HTTPException(status_code=422, detail="Some rows have a blank client, invalid amount, or invalid due_date. Fix those rows and try again.")
    if (frame["amount"] < 0).any():
        raise HTTPException(status_code=422, detail="Negative invoice amounts aren't supported in this MVP.")
    return frame


def is_paid(frame: pd.DataFrame) -> pd.Series:
    return frame["status"].isin(PAID) | frame["paid_date"].notna()


def build_analytics(frame: pd.DataFrame, today: date | None = None) -> AnalyticsResponse:
    today = today or date.today()
    paid = is_paid(frame)
    unpaid = frame.loc[~paid].copy()
    overdue = unpaid.loc[unpaid["due_date"] < today]
    horizon = today + timedelta(days=30)
    expected = unpaid.loc[(unpaid["due_date"] >= today) & (unpaid["due_date"] <= horizon)]
    buckets: dict[date, dict[str, float | int]] = {}
    for _, row in expected.iterrows():
        day = row["due_date"]
        bucket = buckets.setdefault(day, {"amount": 0.0, "count": 0})
        bucket["amount"] = float(bucket["amount"]) + float(row["amount"])
        bucket["count"] = int(bucket["count"]) + 1
    forecast = [ForecastPoint(date=day.isoformat(), expected_inflow=round(float(value["amount"]), 2), invoice_count=int(value["count"])) for day, value in sorted(buckets.items())]
    signals: list[ClientSignal] = []
    historical = frame.loc[paid & frame["paid_date"].notna()].copy()
    for client, group in historical.groupby("client"):
        if not str(client).strip():
            continue
        lateness = [max(0, (row.paid_date - row.due_date).days) for row in group.itertuples()]
        signals.append(ClientSignal(client=str(client), paid_invoice_count=len(lateness), average_days_late=round(sum(lateness) / len(lateness), 1), late_invoice_count=sum(days > 0 for days in lateness), evidence_note=f"Observed from {len(lateness)} paid invoice(s); descriptive history only."))
    signals.sort(key=lambda x: x.average_days_late, reverse=True)
    invoice_rows = []
    for index, row in frame.iterrows():
        paid_date = row.get("paid_date")
        invoice_rows.append({
            "invoice_id": str(row.get("invoice_id") or f"INV-{index + 1:04d}"),
            "client": str(row["client"]),
            "invoice_date": row["invoice_date"].isoformat() if pd.notna(row["invoice_date"]) else "",
            "due_date": row["due_date"].isoformat(),
            "amount": float(row["amount"]),
            "status": str(row["status"]),
            "paid_date": paid_date.isoformat() if paid_date and not pd.isna(paid_date) else None,
            "paid": bool(paid.loc[index]) if index in paid.index else False,
        })
    return AnalyticsResponse(invoice_count=len(frame), outstanding_total=round(float(unpaid["amount"].sum()), 2), overdue_total=round(float(overdue["amount"].sum()), 2), overdue_count=len(overdue), expected_30_day_inflow=round(float(expected["amount"].sum()), 2), forecast=forecast, client_signals=signals, caveats=["Expected inflow is based on due dates; it is not a probability-weighted guarantee.", "Client delay signals use only rows marked paid with a valid paid_date.", "Small sample sizes can produce unstable averages.", "Your uploaded file is processed for this request and invoice rows are not stored by the API."], invoices=invoice_rows)


@app.post("/api/analytics/upload", response_model=AnalyticsResponse)
async def analytics_upload(file: UploadFile = File(...), user: AuthUser = Depends(current_user)) -> AnalyticsResponse:
    if not file.filename or not file.filename.lower().endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(status_code=415, detail="Upload a .csv or .xlsx file.")
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is larger than the 8 MB MVP limit.")
    frame = parse_upload(raw, file.filename)
    return build_analytics(frame)


@app.post("/api/explain")
async def explain(request: ExplainRequest, user: AuthUser = Depends(current_user)) -> dict[str, str]:
    """Optional local Gemma explanation. Send aggregated figures, not raw invoices."""
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    model = request.model or os.getenv("OLLAMA_MODEL", "gemma3:4b")
    prompt = ("You are CashFlowLens, a careful assistant for independent workers. Explain these aggregated cash-flow figures in plain language. "
              "Do not make guarantees or provide financial advice. Distinguish facts from possibilities, mention small-sample uncertainty, and give at most three practical next steps. "
              f"Aggregated figures: {request.summary}")
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(f"{base_url}/api/generate", json={"model": model, "prompt": prompt, "stream": False})
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Local Ollama is unavailable. Start Ollama and pull the configured Gemma model, or use analytics without AI.") from exc
    return {"model": model, "explanation": str(payload.get("response", "")).strip(), "local_inference": True}


@app.post("/api/payment-risk/upload")
async def payment_risk_upload(
    file: UploadFile = File(...),
    user: AuthUser = Depends(current_user),
) -> dict[str, Any]:
    """
    Experimental payment-delay benchmark and predictions.

    Upload a CSV/XLSX with historical paid invoices
    (including paid_date) and current unpaid invoices.
    """
    if not file.filename or not file.filename.lower().endswith(
        (".csv", ".xlsx", ".xls")
    ):
        raise HTTPException(
            status_code=415,
            detail="Upload a CSV or Excel invoice file.",
        )

    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="File exceeds the 8 MB limit.",
        )

    frame = parse_upload(raw, file.filename)

    # Training labels come only from historical paid invoices.
    X, y = prepare_labeled_history(frame)
    benchmark = benchmark_models(X, y)

    # TabPFN predictions are optional. Analytics remains available
    # when there is insufficient data or TabPFN is unavailable.
    predictions = predict_unpaid_invoices(frame, frame)

    return {
        "benchmark": benchmark,
        "payment_risk": predictions,
        "notice": (
            "Experimental estimates only. These are not "
            "guarantees of payment or financial advice."
        ),
    }
