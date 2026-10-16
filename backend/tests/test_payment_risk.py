
import pandas as pd

from app.payment_risk import (
    benchmark_models,
    prepare_labeled_history,
)


def test_labels_late_and_on_time_payments():
    frame = pd.DataFrame({
        "invoice_date": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "due_date": ["2026-01-10", "2026-01-10", "2026-01-12"],
        "paid_date": ["2026-01-12", "2026-01-10", None],
        "amount": [100, 200, 300],
        "status": ["paid", "paid", "unpaid"],
    })

    X, y = prepare_labeled_history(frame)

    assert len(X) == 2
    assert y.tolist() == [1, 0]


def test_small_dataset_does_not_claim_accuracy():
    X = pd.DataFrame({
        "amount": [100, 200, 300, 400],
        "invoice_lead_days": [5, 6, 7, 8],
        "invoice_month": [1, 1, 2, 2],
        "due_month": [1, 1, 2, 2],
        "due_weekday": [0, 1, 2, 3],
    })
    y = pd.Series([0, 1, 0, 1])

    result = benchmark_models(X, y)

    assert result["status"] == "insufficient_data"
    assert "models" not in result
