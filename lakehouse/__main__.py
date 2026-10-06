"""Command line:
  python -m lakehouse generate --out build/bronze/trades_raw.csv     synthetic raw trades
  python -m lakehouse run --bronze build/bronze/trades_raw.csv --out build
  python -m lakehouse cost                                           query-cost comparison
"""

import argparse

from .athena_cost import compare
from .contracts import load_contract
from .generate import write_bronze
from .pipeline import run


def cmd_generate(a):
    n = write_bronze(a.out, a.trades, a.seed)
    print(f"wrote {n} raw rows (SYNTHETIC) to {a.out}")


def cmd_run(a):
    report = run(a.bronze, load_contract(a.contract), a.out)
    print(f"bronze rows:               {report['bronze_rows']}")
    print(f"quarantined (bad rows):    {report['quarantined']}")
    print(f"duplicates / superseded:   {report['duplicates_or_superseded']}")
    print(f"silver rows:               {report['silver_rows']} in {len(report['partitions'])} daily partitions")
    print("quarantine reasons:")
    for reason in report["quarantine_reasons"]:
        print(f"  - {reason}")
    print(f"outputs in {a.out}/silver, {a.out}/gold, {a.out}/quarantine, {a.out}/quality_report.json")


def cmd_cost(a):
    results = compare(raw_gb=a.raw_gb, queries=a.queries)
    print(f"{a.raw_gb} GB of raw CSV, {a.queries} queries/month, each reading 4 of 20 columns "
          f"and the last 7 days of a year\n")
    print(f"{'Layout':<30} {'per query':>12} {'per month':>12}")
    for name, (per_query, per_month) in results.items():
        print(f"{name:<30} ${per_query:>11,.4f} ${per_month:>11,.2f}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="lakehouse", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--out", default="build/bronze/trades_raw.csv")
    g.add_argument("--trades", type=int, default=300)
    g.add_argument("--seed", type=int, default=11)
    g.set_defaults(func=cmd_generate)
    r = sub.add_parser("run")
    r.add_argument("--bronze", default="build/bronze/trades_raw.csv")
    r.add_argument("--contract", default="contracts/trades.json")
    r.add_argument("--out", default="build")
    r.set_defaults(func=cmd_run)
    c = sub.add_parser("cost")
    c.add_argument("--raw-gb", type=float, default=500)
    c.add_argument("--queries", type=int, default=1000)
    c.set_defaults(func=cmd_cost)
    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
