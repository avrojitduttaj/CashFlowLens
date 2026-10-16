
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = [
    "amount",
    "invoice_lead_days",
    "invoice_month",
    "due_month",
    "due_weekday",
]

MIN_TRAINING_ROWS = 40
MIN_ROWS_PER_CLASS = 10


def make_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Build only features available before an invoice is paid."""
    invoice_date = pd.to_datetime(
        frame["invoice_date"], errors="coerce"
    )
    due_date = pd.to_datetime(frame["due_date"], errors="coerce")

    features = pd.DataFrame(index=frame.index)
    features["amount"] = pd.to_numeric(
        frame["amount"], errors="coerce"
    )
    features["invoice_lead_days"] = (
        due_date - invoice_date
    ).dt.days
    features["invoice_month"] = invoice_date.dt.month
    features["due_month"] = due_date.dt.month
    features["due_weekday"] = due_date.dt.weekday

    return features[FEATURES].replace(
        [np.inf, -np.inf], np.nan
    )


def prepare_labeled_history(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series]:
    """
    Use only invoices with a valid paid_date and due_date.

    Target: 1 if payment occurred after the due date,
    otherwise 0. Unpaid invoices are not training labels.
    """
    required = {
        "invoice_date", "due_date", "amount",
        "paid_date", "status",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(
            f"Missing columns: {', '.join(sorted(missing))}"
        )

    paid_date = pd.to_datetime(
        frame["paid_date"], errors="coerce"
    )
    due_date = pd.to_datetime(
        frame["due_date"], errors="coerce"
    )

    valid = (
        paid_date.notna()
        & due_date.notna()
        & pd.to_numeric(
            frame["amount"], errors="coerce"
        ).notna()
    )

    # A paid status without a paid_date is not enough
    # to determine whether an invoice was late.
    labeled = frame.loc[valid].copy()
    paid_date = paid_date.loc[valid]
    due_date = due_date.loc[valid]

    paid_status = labeled["status"].astype(str).str.lower().isin(
        {"paid", "complete", "completed"}
    )
    labeled = labeled.loc[paid_status]
    paid_date = paid_date.loc[paid_status]
    due_date = due_date.loc[paid_status]

    y = (paid_date > due_date).astype(int)
    X = make_features(labeled)

    # Keep only invoices with every required feature present.
    valid_features = X.notna().all(axis=1)

    X = X.loc[valid_features].astype(float)
    y = y.loc[valid_features].astype(int)

    return X, y



def _metrics(
    y_true: pd.Series,
    predictions: np.ndarray,
    probabilities: np.ndarray,
) -> dict[str, float | None]:
    return {
        "accuracy": round(float(accuracy_score(
            y_true, predictions
        )), 3),
        "balanced_accuracy": round(float(
            balanced_accuracy_score(y_true, predictions)
        ), 3),
        "f1_late": round(float(
            f1_score(y_true, predictions, zero_division=0)
        ), 3),
        "roc_auc": (
            round(float(roc_auc_score(
                y_true, probabilities
            )), 3)
            if len(np.unique(y_true)) == 2 else None
        ),
    }


def _tabpfn_classifier():
    """Import lazily so core analytics works without TabPFN."""
    from tabpfn import TabPFNClassifier

    return TabPFNClassifier()


def benchmark_models(
    X: pd.DataFrame,
    y: pd.Series,
    random_state: int = 42,
) -> dict[str, Any]:
    """Compare TabPFN with logistic regression on one holdout."""
    class_counts = y.value_counts()

    if (
        len(X) < MIN_TRAINING_ROWS
        or len(class_counts) < 2
        or int(class_counts.min()) < MIN_ROWS_PER_CLASS
    ):
        return {
            "status": "insufficient_data",
            "labeled_rows": len(X),
            "class_counts": {
                str(int(k)): int(v)
                for k, v in class_counts.items()
            },
            "message": (
                "Need at least 40 labeled invoices and "
                "10 examples in each class for this experiment."
            ),
        }

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.25,
        random_state=random_state,
        stratify=y,
    )

    baseline = make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        LogisticRegression(max_iter=1000),
    )
    baseline.fit(X_train, y_train)

    results: dict[str, Any] = {
        "status": "ok",
        "labeled_rows": len(X),
        "train_rows": len(X_train),
        "test_rows": len(X_test),
        "positive_label": "paid late",
        "models": {
            "logistic_regression": _metrics(
                y_test,
                baseline.predict(X_test),
                baseline.predict_proba(X_test)[:, 1],
            )
        },
    }

    try:
        tabpfn = _tabpfn_classifier()
        tabpfn.fit(X_train, y_train)
        probabilities = tabpfn.predict_proba(X_test)[:, 1]
        predictions = (probabilities >= 0.5).astype(int)

        results["models"]["tabpfn"] = _metrics(
            y_test, predictions, probabilities
        )
    except Exception as exc:
        results["models"]["tabpfn"] = {
            "status": "unavailable",
            "reason": (
                f"{type(exc).__name__}: {str(exc)[:250]}"
            ),
        }

    results["caveat"] = (
        "Exploratory holdout benchmark, not evidence of "
        "production accuracy. Small or unrepresentative "
        "datasets may produce misleading metrics."
    )
    return results


def predict_unpaid_invoices(
    history: pd.DataFrame,
    all_invoices: pd.DataFrame,
) -> dict[str, Any]:
    """
    Train on paid history and score currently unpaid invoices.

    The returned probability is an experimental model output,
    not a calibrated probability of late payment.
    """
    X, y = prepare_labeled_history(history)

    counts = y.value_counts()
    if (
        len(X) < MIN_TRAINING_ROWS
        or len(counts) < 2
        or int(counts.min()) < MIN_ROWS_PER_CLASS
    ):
        return {
            "status": "insufficient_data",
            "message": "Not enough labeled payment history.",
            "predictions": [],
        }

    try:
        model = _tabpfn_classifier()
        model.fit(X, y)
    except Exception as exc:
        return {
            "status": "unavailable",
            "message": (
                "TabPFN could not be loaded. "
                "Use deterministic analytics instead."
            ),
            "reason": f"{type(exc).__name__}: {str(exc)[:200]}",
            "predictions": [],
        }

    paid_status = all_invoices["status"].astype(str).str.lower().isin(
        {"paid", "complete", "completed"}
    )
    unpaid = all_invoices.loc[~paid_status].copy()

    if unpaid.empty:
        return {
            "status": "ok",
            "predictions": [],
            "message": "No unpaid invoices to score.",
        }

    X_unpaid = make_features(unpaid)
    probabilities = model.predict_proba(X_unpaid)[:, 1]

    predictions = []
    for (index, row), probability in zip(
        unpaid.iterrows(), probabilities
    ):
        predictions.append({
            "invoice_id": str(
                row.get("invoice_id", f"INV-{index + 1:04d}")
            ),
            "client": str(row.get("client", "")),
            "amount": float(row["amount"]),
            "due_date": str(row["due_date"]),
            "experimental_late_score": round(
                float(probability), 3
            ),
            "label": (
                "higher relative score"
                if probability >= 0.5
                else "lower relative score"
            ),
            "warning": (
                "Experimental and uncalibrated; not a guarantee."
            ),
        })

    return {
        "status": "ok",
        "labeled_rows": len(X),
        "predictions": predictions,
        "caveat": (
            "Predictions are experimental. Validate on "
            "representative historical data before relying on them."
        ),
    }
