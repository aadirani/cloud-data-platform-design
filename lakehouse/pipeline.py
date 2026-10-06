"""Bronze -> silver -> gold.

bronze  raw files exactly as received (never modified)
silver  cleaned, typed, de-duplicated, contract-checked; partitioned by trade_date
gold    business-ready aggregates for dashboards and risk

Re-running is safe: each run rewrites its output partitions completely (idempotent).
"""

import csv
import json
import shutil
from collections import defaultdict
from pathlib import Path

from .contracts import apply_contract


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def to_silver(raw_rows, contract):
    """Return (silver_rows, quarantine_rows, stats)."""
    key = contract["primary_key"]
    valid, quarantine = [], []
    for row in raw_rows:
        clean, problems = apply_contract(row, contract)
        if problems:
            quarantine.append(dict(row, _reason="; ".join(problems)))
        else:
            valid.append(clean)

    # Keep one row per primary key: the highest version (later amendments win).
    latest = {}
    for row in valid:
        k = tuple(row[c] for c in key)
        if k not in latest or row["version"] > latest[k]["version"]:
            latest[k] = row
    silver = sorted(latest.values(), key=lambda r: (r["executed_at"], r["trade_id"]))
    for row in silver:
        row["trade_date"] = row["executed_at"][:10]
    stats = {"bronze_rows": len(raw_rows), "valid_rows": len(valid), "quarantined": len(quarantine),
             "duplicates_or_superseded": len(valid) - len(silver), "silver_rows": len(silver)}
    return silver, quarantine, stats


def to_gold(silver):
    """Daily desk/symbol summary and client net positions."""
    daily = defaultdict(lambda: {"trades": 0, "buy_qty": 0.0, "sell_qty": 0.0, "notional_usd": 0.0})
    positions = defaultdict(float)
    for r in silver:
        d = daily[(r["trade_date"], r["desk"], r["symbol"])]
        d["trades"] += 1
        d["buy_qty" if r["side"] == "buy" else "sell_qty"] += r["quantity"]
        d["notional_usd"] += r["quantity"] * r["price"]
        positions[(r["client_id"], r["symbol"])] += r["quantity"] if r["side"] == "buy" else -r["quantity"]

    daily_rows = []
    for (day, desk, symbol), d in sorted(daily.items()):
        qty = d["buy_qty"] + d["sell_qty"]
        daily_rows.append({"trade_date": day, "desk": desk, "symbol": symbol, "trades": d["trades"],
                           "buy_qty": round(d["buy_qty"], 4), "sell_qty": round(d["sell_qty"], 4),
                           "notional_usd": round(d["notional_usd"], 2),
                           "vwap": round(d["notional_usd"] / qty, 2) if qty else None})
    position_rows = [{"client_id": c, "symbol": s, "net_qty": round(q, 4)}
                     for (c, s), q in sorted(positions.items())]
    return daily_rows, position_rows


def run(bronze_path, contract, out_dir):
    out = Path(out_dir)
    raw = read_csv(bronze_path)
    silver, quarantine, stats = to_silver(raw, contract)

    silver_dir = out / "silver" / "trades"
    if silver_dir.exists():
        shutil.rmtree(silver_dir)  # rewrite all partitions: re-runs give identical output
    fields = list(contract["columns"]) + ["trade_date"]
    by_day = defaultdict(list)
    for row in silver:
        by_day[row["trade_date"]].append(row)
    for day, rows in sorted(by_day.items()):
        write_csv(silver_dir / f"trade_date={day}" / "part-0000.csv", rows, fields)

    write_csv(out / "quarantine" / "trades.csv", quarantine, list(raw[0]) + ["_reason"] if raw else ["_reason"])
    daily, positions = to_gold(silver)
    write_csv(out / "gold" / "daily_desk_symbol.csv", daily, list(daily[0]) if daily else [])
    write_csv(out / "gold" / "client_net_positions.csv", positions, ["client_id", "symbol", "net_qty"])

    report = dict(stats, partitions=sorted(by_day), contract=contract["name"],
                  quarantine_reasons=sorted({q["_reason"] for q in quarantine}))
    (out / "quality_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
