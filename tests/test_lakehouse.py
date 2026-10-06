import json
import tempfile
import unittest
from pathlib import Path

from lakehouse.athena_cost import MIN_BYTES, bytes_scanned, compare
from lakehouse.contracts import apply_contract, load_contract, parse_timestamp
from lakehouse.generate import generate, write_bronze
from lakehouse.pipeline import run, to_gold, to_silver

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = load_contract(ROOT / "contracts" / "trades.json")
GOOD = {"trade_id": "TR00001", "version": "1", "desk": "spot", "symbol": "btcusdt", "side": "buy",
        "quantity": "0.5", "price": "60000", "client_id": "C001", "executed_at": "2026-09-01 10:00:00"}


class ContractTests(unittest.TestCase):
    def test_good_row_is_typed_and_normalised(self):
        clean, problems = apply_contract(GOOD, CONTRACT)
        self.assertEqual(problems, [])
        self.assertEqual(clean["symbol"], "BTCUSDT")
        self.assertEqual(clean["quantity"], 0.5)
        self.assertEqual(clean["executed_at"], "2026-09-01T10:00:00Z")

    def test_each_rule_reports_a_reason(self):
        cases = {"quantity": ("-1", "greater than 0"), "side": ("hold", "not in"),
                 "price": ("", "missing"), "executed_at": ("yesterday", "unrecognised timestamp"),
                 "client_id": ("ACME-CORP", "does not match"), "version": ("x", "not a valid int")}
        for field, (value, reason) in cases.items():
            with self.subTest(field=field):
                _, problems = apply_contract(dict(GOOD, **{field: value}), CONTRACT)
                self.assertEqual(len(problems), 1)
                self.assertIn(reason, problems[0])

    def test_both_timestamp_formats(self):
        self.assertEqual(parse_timestamp("2026-09-01T10:00:00Z"), parse_timestamp("2026-09-01 10:00:00"))


class SilverTests(unittest.TestCase):
    def test_latest_version_wins_and_duplicates_removed(self):
        rows = [GOOD, dict(GOOD), dict(GOOD, version="2", quantity="0.7")]
        silver, quarantine, stats = to_silver(rows, CONTRACT)
        self.assertEqual(len(silver), 1)
        self.assertEqual(silver[0]["quantity"], 0.7)
        self.assertEqual(stats["duplicates_or_superseded"], 2)
        self.assertEqual(silver[0]["trade_date"], "2026-09-01")

    def test_generated_data_counts(self):
        silver, quarantine, stats = to_silver([{k: str(v) for k, v in r.items()} for r in generate()], CONTRACT)
        self.assertEqual(stats["bronze_rows"], 320)    # 300 trades + 10 amendments + 5 duplicates + 5 bad
        self.assertEqual(stats["quarantined"], 5)
        self.assertEqual(stats["silver_rows"], 300)    # one row per trade id
        self.assertEqual(stats["duplicates_or_superseded"], 15)


class GoldTests(unittest.TestCase):
    def test_vwap_and_net_position(self):
        rows = [dict(GOOD, trade_id="TR00001"), dict(GOOD, trade_id="TR00002", side="sell", quantity="0.2",
                                                    price="61000")]
        silver, _, _ = to_silver(rows, CONTRACT)
        daily, positions = to_gold(silver)
        self.assertEqual(daily[0]["trades"], 2)
        # (0.5 x 60000 + 0.2 x 61000) / 0.7 = 60285.71
        self.assertAlmostEqual(daily[0]["vwap"], 60285.71)
        self.assertEqual(positions, [{"client_id": "C001", "symbol": "BTCUSDT", "net_qty": 0.3}])


class EndToEndTests(unittest.TestCase):
    def test_run_writes_partitions_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            bronze = Path(tmp) / "bronze" / "trades_raw.csv"
            write_bronze(bronze)
            first = run(bronze, CONTRACT, Path(tmp) / "out")
            second = run(bronze, CONTRACT, Path(tmp) / "out")
            self.assertEqual(first, second)
            partitions = sorted(p.name for p in (Path(tmp) / "out" / "silver" / "trades").iterdir())
            self.assertEqual(partitions, [f"trade_date=2026-09-0{d}" for d in range(1, 6)])
            report = json.loads((Path(tmp) / "out" / "quality_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["silver_rows"], 300)


class CostTests(unittest.TestCase):
    def test_parquet_and_partitions_reduce_cost(self):
        r = compare()
        csv_month = r["CSV, no partitions"][1]
        best_month = r["Parquet, partitioned by date"][1]
        self.assertAlmostEqual(csv_month, 500 / 1024 * 5 * 1000)   # $2,441.41
        self.assertLess(best_month, csv_month / 500)

    def test_minimum_billed_bytes(self):
        self.assertEqual(bytes_scanned(1000, fmt="csv"), MIN_BYTES)


if __name__ == "__main__":
    unittest.main()
