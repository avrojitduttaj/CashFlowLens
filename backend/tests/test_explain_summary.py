import asyncio
import json
import math

import httpx
import pytest
from fastapi import HTTPException

import app.main as main
from app.main import (
    OllamaConfiguration,
    AuthUser,
    ExplainRequest,
    cashflow_plan_context,
    explain,
    ollama_configuration,
    sanitize_explanation_summary,
    validate_cashflow_plan,
)


def test_explanation_summary_contains_only_finite_aggregates():
    summary = {
        "invoice_count": 12,
        "outstanding_total": 2450.5,
        "overdue_total": float("nan"),
        "overdue_count": True,
        "expected_30_day_inflow": 900,
        "client": "Private client",
        "invoice_rows": [{"email": "client@example.com"}],
        "client_signals": [
            {
                "client": "Private client",
                "paid_invoice_count": 4,
                "average_days_late": 2.5,
                "late_invoice_count": 1,
                "email": "client@example.com",
            },
            {"paid_invoice_count": math.inf},
            "not a signal",
        ],
    }

    assert sanitize_explanation_summary(summary) == {
        "open_receivables": "present",
        "due_date_inflows_next_30_days": "present",
        "payment_history": "late_payments_observed",
    }


def test_explanation_summary_rejects_unbounded_integer_metrics():
    summary = {"invoice_count": 10**1000}

    assert sanitize_explanation_summary(summary) == {}


def test_explanation_signals_do_not_expose_exact_figures():
    assert sanitize_explanation_summary(
        {
            "outstanding_total": 0,
            "overdue_count": 0,
            "expected_30_day_inflow": 0,
            "client_signals": [],
            "invoice_rows": [{"client": "Private client"}],
        }
    ) == {
        "open_receivables": "none",
        "overdue_invoices": "none",
        "due_date_inflows_next_30_days": "none",
        "payment_history": "not_available",
    }


@pytest.mark.parametrize(
    ("base_url", "model"),
    [
        ("https://localhost:11434", "gemma3:4b"),
        ("http://example.com:11434", "gemma3:4b"),
        ("http://127.0.0.1:11434", "gemma4:cloud"),
        ("http://127.0.0.1:11434", "llama3:8b"),
        ("http://127.0.0.1:11434/api", "gemma3:4b"),
    ],
)
def test_local_gemma_configuration_rejects_nonlocal_or_non_gemma(
    base_url, model
):
    with pytest.raises(HTTPException) as error:
        ollama_configuration(base_url, model, None, "development")

    assert error.value.status_code == 503


def test_local_gemma_configuration_accepts_loopback_gemma():
    config = ollama_configuration(
        "http://127.0.0.1:11434",
        "gemma3:4b",
        "must-not-be-forwarded",
        "development",
    )

    assert config == OllamaConfiguration(
        "http://127.0.0.1:11434", "gemma3:4b", True
    )
    assert config.headers == {}


def test_remote_gateway_requires_explicit_production_and_api_key():
    for api_key, environment in (
        (None, "production"),
        ("", "production"),
        ("gateway-key", "development"),
    ):
        with pytest.raises(HTTPException) as error:
            ollama_configuration(
                "https://ollama.example.com",
                "gemma3:4b",
                api_key,
                environment,
            )

        assert error.value.status_code == 503


@pytest.mark.parametrize(
    "base_url",
    [
        "http://ollama.example.com:11434",
        "https://localhost:11434",
        "https://127.0.0.1:11434",
        "https://user:password@ollama.example.com",
        "https://ollama.example.com?token=secret",
        "https://ollama.example.com#fragment",
        "https://ollama.example.com/api/generate",
        "https://ollama.example.com/../admin",
        "https://ollama.example.com:invalid",
    ],
)
def test_remote_gateway_rejects_invalid_urls(base_url):
    with pytest.raises(HTTPException) as error:
        ollama_configuration(
            base_url,
            "gemma3:4b",
            "gateway-key",
            "production",
        )

    assert error.value.status_code == 503


def test_remote_gateway_accepts_https_and_keeps_key_out_of_repr():
    config = ollama_configuration(
        "https://ollama.example.com/gateway/",
        "gemma3:4b",
        "secret-gateway-key",
        "production",
    )

    assert config.base_url == "https://ollama.example.com/gateway"
    assert config.local_inference is False
    assert config.headers == {"Authorization": "Bearer secret-gateway-key"}
    assert "secret-gateway-key" not in repr(config)


@pytest.mark.parametrize("api_key", ["bad key", "bad\r\nheader", "bad\tvalue"])
def test_remote_gateway_rejects_unsafe_api_key_header(api_key):
    with pytest.raises(HTTPException) as error:
        ollama_configuration(
            "https://ollama.example.com",
            "gemma3:4b",
            api_key,
            "production",
        )

    assert error.value.status_code == 503


@pytest.mark.parametrize(
    ("base_url", "api_key", "environment", "expected_header", "is_local"),
    [
        (
            "http://127.0.0.1:11434",
            "must-not-be-forwarded",
            "development",
            None,
            True,
        ),
        (
            "https://ollama.example.com",
            "gateway-secret",
            "production",
            "Bearer gateway-secret",
            False,
        ),
    ],
)
def test_explain_sends_gateway_key_only_to_remote_backend(
    monkeypatch,
    base_url,
    api_key,
    environment,
    expected_header,
    is_local,
):
    sent_requests = []
    original_async_client = httpx.AsyncClient

    def handler(request):
        sent_requests.append(request)
        return httpx.Response(
            200,
            json={
                "response": json.dumps(
                    {"focus": "overdue", "actions": ["review_overdue"]}
                )
            },
        )

    def client_factory(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["timeout"].connect == 10.0
        assert kwargs["timeout"].write == 10.0
        assert kwargs["timeout"].pool == 10.0
        assert kwargs["timeout"].read == 300.0
        assert kwargs["follow_redirects"] is False
        return original_async_client(
            transport=httpx.MockTransport(handler),
            **kwargs,
        )

    monkeypatch.setattr(main.httpx, "AsyncClient", client_factory)
    monkeypatch.setenv("OLLAMA_BASE_URL", base_url)
    monkeypatch.setenv("OLLAMA_MODEL", "gemma3:4b")
    monkeypatch.setenv("OLLAMA_API_KEY", api_key)
    monkeypatch.setenv("CASHFLOWLENS_ENV", environment)

    response = asyncio.run(
        explain(
            ExplainRequest(summary={"overdue_count": 1}),
            AuthUser(
                id=1,
                email="demo@example.com",
                created_at="2026-01-01T00:00:00+00:00",
            ),
        )
    )

    assert len(sent_requests) == 1
    assert sent_requests[0].url.path == "/api/generate"
    assert sent_requests[0].headers.get("Authorization") == expected_header
    assert response["local_inference"] is is_local
    assert api_key not in json.dumps(response)


def test_explain_does_not_leak_remote_gateway_error_or_key(monkeypatch, caplog):
    gateway_key = "gateway-secret-value"
    original_async_client = httpx.AsyncClient

    def handler(request):
        return httpx.Response(
            401,
            json={"detail": f"Unauthorized: {gateway_key}"},
        )

    def client_factory(**kwargs):
        return original_async_client(
            transport=httpx.MockTransport(handler),
            **kwargs,
        )

    monkeypatch.setattr(main.httpx, "AsyncClient", client_factory)
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://ollama.example.com")
    monkeypatch.setenv("OLLAMA_MODEL", "gemma3:4b")
    monkeypatch.setenv("OLLAMA_API_KEY", gateway_key)
    monkeypatch.setenv("CASHFLOWLENS_ENV", "production")

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            explain(
                ExplainRequest(summary={"overdue_count": 1}),
                AuthUser(
                    id=1,
                    email="demo@example.com",
                    created_at="2026-01-01T00:00:00+00:00",
                ),
            )
        )

    assert error.value.status_code == 502
    assert gateway_key not in error.value.detail
    assert gateway_key not in caplog.text


def test_explain_maps_remote_connection_timeout_safely(monkeypatch, caplog):
    gateway_key = "timeout-gateway-secret"
    original_async_client = httpx.AsyncClient

    def handler(request):
        raise httpx.ConnectTimeout(gateway_key, request=request)

    def client_factory(**kwargs):
        return original_async_client(
            transport=httpx.MockTransport(handler),
            **kwargs,
        )

    monkeypatch.setattr(main.httpx, "AsyncClient", client_factory)
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://ollama.example.com")
    monkeypatch.setenv("OLLAMA_MODEL", "gemma3:4b")
    monkeypatch.setenv("OLLAMA_API_KEY", gateway_key)
    monkeypatch.setenv("CASHFLOWLENS_ENV", "production")

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            explain(
                ExplainRequest(summary={"overdue_count": 1}),
                AuthUser(
                    id=1,
                    email="demo@example.com",
                    created_at="2026-01-01T00:00:00+00:00",
                ),
            )
        )

    assert error.value.status_code == 503
    assert "timed out" in error.value.detail
    assert gateway_key not in error.value.detail
    assert gateway_key not in caplog.text


def test_cashflow_plan_only_offers_actions_supported_by_signals():
    context = cashflow_plan_context(
        {
            "outstanding_total": 400,
            "overdue_count": 2,
            "expected_30_day_inflow": 200,
            "client_signals": [],
        }
    )

    assert context["signals"] == {
        "open_receivables": "present",
        "overdue_invoices": "present",
        "due_date_inflows_next_30_days": "present",
        "payment_history": "not_available",
    }
    assert context["focus_options"] == [
        "overdue",
        "receivables",
        "upcoming_inflows",
    ]
    assert context["actions_by_focus"] == {
        "overdue": ["review_overdue", "prepare_overdue_followup"],
        "receivables": ["review_receivables"],
        "upcoming_inflows": ["check_due_dates"],
    }


def test_cashflow_plan_validation_accepts_only_allowed_distinct_actions():
    assert validate_cashflow_plan(
        {"focus": "overdue", "actions": ["review_overdue"]},
        ["overdue"],
        {"overdue": ["review_overdue", "prepare_overdue_followup"]},
    ) == ("overdue", ["review_overdue"])

    for invalid_plan in (
        {"focus": "payment_history", "actions": ["review_overdue"]},
        {"focus": [], "actions": ["review_overdue"]},
        {"focus": "overdue", "actions": ["check_due_dates"]},
        {"focus": "overdue", "actions": ["not_allowed"]},
        {"focus": "overdue", "actions": ["review_overdue", "review_overdue"]},
        {"focus": "overdue", "actions": [{}]},
        {"focus": "overdue", "actions": []},
        {"focus": "overdue", "actions": ["review_overdue"], "extra": True},
    ):
        with pytest.raises(HTTPException) as error:
            validate_cashflow_plan(
                invalid_plan,
                ["overdue"],
                {"overdue": ["review_overdue", "prepare_overdue_followup"]},
            )

        assert error.value.status_code == 502
