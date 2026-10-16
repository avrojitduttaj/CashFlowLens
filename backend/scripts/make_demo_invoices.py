
from pathlib import Path
import csv
from datetime import date, timedelta

OUTPUT = Path(__file__).resolve().parent.parent / "sample-data" / "demo_invoices.csv"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

rows = []
start = date(2025, 1, 1)

for i in range(80):
    invoice_date = start + timedelta(days=i * 4)
    due_date = invoice_date + timedelta(days=14)
    is_paid = i < 60

    # Balanced historical examples: 30 on-time, 30 late.
    is_late = is_paid and (i % 2 == 0)
    paid_date = (
        due_date + timedelta(days=7 if is_late else 0)
        if is_paid else ""
    )

    rows.append({
        "invoice_id": f"DEMO-{i + 1:04d}",
        "client": f"Client {(i % 8) + 1}",
        "invoice_date": invoice_date.isoformat(),
        "due_date": due_date.isoformat(),
        "amount": 500 + ((i * 137) % 4500),
        "status": "paid" if is_paid else "unpaid",
        "paid_date": paid_date.isoformat() if paid_date else "",
    })

with OUTPUT.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

print(f"Created {len(rows)} synthetic invoices at: {OUTPUT}")
print("60 historical paid invoices; 20 unpaid invoices.")
