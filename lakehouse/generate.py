"""Generate a SYNTHETIC raw trade export, messy on purpose, like real source data.

Problems included: amended trades (same id, higher version), exact duplicates,
lower-case symbols, two timestamp formats, and a few invalid rows.
"""

import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

FIELDS = ["trade_id", "version", "desk", "symbol", "side", "quantity", "price",
          "client_id", "executed_at", "updated_at"]
PRICES = {"BTCUSDT": 60000.0, "ETHUSDT": 3000.0, "SOLUSDT": 150.0}


def generate(n=300, seed=11, days=5):
    rng = random.Random(seed)
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(1, n + 1):
        symbol = rng.choice(list(PRICES))
        t = start + timedelta(seconds=rng.randint(0, days * 86400 - 1))
        price = round(PRICES[symbol] * rng.uniform(0.97, 1.03), 2)
        qty = round(rng.uniform(0.01, 2.0) * (60000 / PRICES[symbol]) ** 0.5, 4)
        executed = t.strftime("%Y-%m-%dT%H:%M:%SZ") if rng.random() < 0.7 else t.strftime("%Y-%m-%d %H:%M:%S")
        rows.append({"trade_id": f"TR{i:05d}", "version": 1, "desk": rng.choice(["spot", "otc", "derivatives"]),
                     "symbol": symbol.lower() if rng.random() < 0.1 else symbol,
                     "side": rng.choice(["buy", "sell"]), "quantity": qty, "price": price,
                     "client_id": f"C{rng.randint(1, 20):03d}", "executed_at": executed,
                     "updated_at": t.strftime("%Y-%m-%dT%H:%M:%SZ")})

    # Amendments: a later version corrects the quantity. Silver must keep only the latest.
    for row in rng.sample(rows, 10):
        amended = dict(row, version=2, quantity=round(float(row["quantity"]) * 1.1, 4))
        rows.append(amended)
    # Exact duplicates (the source sent the same record twice).
    rows += [dict(r) for r in rng.sample(rows[:n], 5)]
    # Invalid rows: these must end up in quarantine, not in silver.
    rows += [
        dict(rows[0], trade_id="TR90001", quantity=-1.0),
        dict(rows[1], trade_id="TR90002", side="hold"),
        dict(rows[2], trade_id="TR90003", price=""),
        dict(rows[3], trade_id="TR90004", executed_at="yesterday"),
        dict(rows[4], trade_id="TR90005", client_id="ACME-CORP"),
    ]
    rng.shuffle(rows)
    return rows


def write_bronze(path, n=300, seed=11):
    rows = generate(n, seed)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
