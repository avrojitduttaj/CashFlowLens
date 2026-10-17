
from pathlib import Path
import json
import sys

import pandas as pd

# Allow imports when run as a script from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.payment_risk import (  # noqa: E402
    benchmark_models,
    prepare_labeled_history,
)


def main() -> None:
    if len(sys.argv) != 2:
        print(
            "Usage: python scripts/benchmark_tabpfn.py "
            "path/to/invoices.csv"
        )
        raise SystemExit(2)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        raise SystemExit(2)

    frame = pd.read_csv(path)
    frame.columns = [
        str(column).strip().lower().replace(" ", "_")
        for column in frame.columns
    ]

    X, y = prepare_labeled_history(frame)
    result = benchmark_models(X, y)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
