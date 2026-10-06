# Cloud Data Platform Design (Lakehouse)

![tests](https://github.com/aadirani/cloud-data-platform-design/actions/workflows/tests.yml/badge.svg)

A reference design for a **lakehouse on AWS** for a digital-asset trading desk, bringing market data, trades and custody balances into one governed platform. It comes with a **working mini-pipeline** (bronze → silver → gold, enforced by a data contract) and a **cost model** showing why file format and partitioning matter. All data is synthetic.

## The idea in one paragraph

Raw data is kept exactly as received (**bronze**), so nothing is ever lost. It's then checked against a written **data contract**: right types, allowed values, required fields. Clean rows become one trusted copy per trade (**silver**), and broken rows go to **quarantine** with the reason. From silver, ready-to-use tables are built (**gold**): daily volumes and average prices per desk, client net positions. Storing data in a columnar format, split by date, makes the same queries about **1,000× cheaper** on a pay-per-scan engine like Athena.

## Try it

Needs Python 3.9+, nothing to install.

```bash
python -m lakehouse generate     # synthetic, deliberately messy raw trades
python -m lakehouse run          # bronze -> silver (+ quarantine) -> gold
python -m lakehouse cost         # query cost: CSV vs Parquet, with and without partitions
```

```
bronze rows:               320
quarantined (bad rows):    5
duplicates / superseded:   15
silver rows:               300 in 5 daily partitions
```

## What's inside

| Path | What it is |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | AWS lakehouse design, medallion layers, governance, 6 decision records, risks, cost model and monthly estimate |
| [contracts/trades.json](contracts/trades.json) | The data contract for the silver trades table |
| [lakehouse/pipeline.py](lakehouse/pipeline.py) | Bronze → silver → gold, partitioning, quality report |
| [lakehouse/contracts.py](lakehouse/contracts.py) | Contract enforcement |
| [lakehouse/athena_cost.py](lakehouse/athena_cost.py) | Query-cost model |
| [docs/code-walkthrough.md](docs/code-walkthrough.md) | Plain-language explanation |

## Scope

The local demo writes CSV files to stay dependency-free. The platform design uses Parquet/Iceberg on S3. Prices in the cost model are approximate and labelled as such.
