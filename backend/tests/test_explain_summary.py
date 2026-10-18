import math

import pytest
from fastapi import HTTPException

from app.main import (
    cashflow_plan_context,
    local_gemma_configuration,
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
        local_gemma_configuration(base_url, model)

    assert error.value.status_code == 503


def test_local_gemma_configuration_accepts_loopback_gemma():
    assert local_gemma_configuration(
        "http://localhost:11434", "gemma3:4b"
    ) == ("http://localhost:11434", "gemma3:4b")


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
