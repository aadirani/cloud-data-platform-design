# Code walkthrough

A plain-language guide for explaining this project in an interview.

## Vocabulary

- **Lakehouse:** cheap file storage (a "data lake" on S3) plus table features usually found in databases (updates, schemas, history), through an open table format like Apache Iceberg.
- **Medallion layers:** bronze (raw) → silver (clean) → gold (business-ready).
- **Data contract:** a written agreement on what a dataset contains and which rules each row must follow.
- **Partition:** splitting a table into folders by a column (here, the trade date) so queries can skip what they don't need.
- **Parquet:** a compressed, column-by-column file format, so a query reads only the columns it uses.

## `lakehouse/generate.py`

It creates 300 synthetic trades and then messes them up the way real exports do: 10 **amendments** (same trade id, version 2, corrected quantity), 5 **exact duplicates**, some lower-case symbols, two different timestamp formats, and 5 **invalid rows** (negative quantity, side "hold", missing price, timestamp "yesterday", a client id in the wrong format). 320 rows in total.

## `lakehouse/contracts.py`

`apply_contract(row, contract)` goes column by column through `contracts/trades.json`:
1. normalise if asked (`symbol` → upper case)
2. convert to the right type (text, integer, decimal, timestamp). Both timestamp formats become UTC `YYYY-MM-DDTHH:MM:SSZ`
3. check the rules: required, allowed values, pattern (e.g. client id `C` + 3 digits), minimums

It returns the clean row *and* a list of problems in plain English.

## `lakehouse/pipeline.py`

- **`to_silver`:** rows with problems go to **quarantine**, with the reasons joined. For the rest, keep **one row per trade id**, the one with the **highest version**, so amendments replace originals and duplicates disappear. Each row gets `trade_date` for partitioning. Result: 320 → 300 silver + 5 quarantined (15 duplicates or superseded versions dropped).
- **`to_gold`:** per day, desk and symbol it works out trade count, bought and sold quantity, **notional** (quantity × price) and **VWAP** (notional ÷ total quantity, the volume-weighted average price). Per client and symbol: **net position** (buys − sells).
- **`run`:** writes silver as `silver/trades/trade_date=2026-09-01/part-0000.csv`. That folder naming (Hive style) is what Athena and Spark use for partition pruning. It also writes the quarantine file, the gold tables and `quality_report.json`. It **deletes and rewrites** the silver partitions each time, so running twice gives identical results (idempotent).

## `lakehouse/athena_cost.py`

Athena bills by bytes scanned (about $5/TB, 10 MB minimum per query).
- CSV: scans everything it touches.
- Parquet: scans ÷ compression × share of columns used.
- Partitions: × share of days queried.

`compare()` runs four layouts for 500 GB and 1,000 queries a month: $2,441 for CSV with no partitions versus about $2.34 for partitioned Parquet. The compression factor (4×) is an assumption you can change.

## The tests

Contract: a good row is typed and normalised, each broken rule gives exactly one clear reason, and both timestamp formats work. Silver: the latest version wins and duplicates are removed. The generated data gives exactly 320 → 300 + 5 quarantined + 15 dropped. Gold: VWAP checked by hand ((0.5×60,000 + 0.2×61,000) ÷ 0.7 = 60,285.71) and net position 0.3. End to end: 5 date partitions, and two runs give identical output. Cost: the CSV figure is checked by hand, partitioned Parquet is over 500× cheaper, and the 10 MB minimum applies.

## Likely interview questions

- **"Lakehouse or warehouse?"** A lakehouse for cheap storage, open formats and full history. Add a warehouse on top of gold only if heavy, concurrent BI needs it (ADR-001).
- **"How do you handle amended trades?"** Primary key plus the latest version wins in silver, and it's tested (ADR-002, R-02).
- **"What happens when the source sends bad data?"** It's quarantined with the reason, an alert fires, and the producer fixes it under the contract. Never silently dropped or guessed (ADR-003).
- **"How do you keep cloud query costs down?"** Partition by date and use Parquet/Iceberg, set per-query scan limits, and serve gold tables to dashboards (§7).
- **"Who can see client data?"** Columns are classified, and Lake Formation column-level permissions restrict `client_id` to risk and compliance roles (§4).
