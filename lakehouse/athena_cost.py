"""Why file format and partitioning matter: query cost on a pay-per-data-scanned engine.

Amazon Athena (like several serverless query engines) charges by data scanned:
approximately $5 per TB in us-east-1 (check current pricing), with a 10 MB minimum per query.

- CSV: every query reads every byte of every file it touches.
- Parquet: columnar and compressed, so a query reads only the columns it needs.
- Partitioning by date: a query for 7 days skips the other days entirely.

The compression and column-share figures are assumptions to vary, not measurements.
"""

TB = 1024 ** 4
MIN_BYTES = 10 * 1024 ** 2  # 10 MB minimum billed per query


def bytes_scanned(raw_bytes, fmt="csv", compression=4.0, column_share=1.0, partition_share=1.0):
    if fmt == "csv":
        scanned = raw_bytes * partition_share
    elif fmt == "parquet":
        scanned = raw_bytes / compression * column_share * partition_share
    else:
        raise ValueError("fmt must be 'csv' or 'parquet'")
    return max(scanned, MIN_BYTES)


def monthly_cost(raw_bytes, queries_per_month, price_per_tb=5.0, **kw):
    per_query = bytes_scanned(raw_bytes, **kw) / TB * price_per_tb
    return per_query, per_query * queries_per_month


def compare(raw_gb=500, queries=1000, columns_total=20, columns_used=4, days_total=365, days_queried=7,
            compression=4.0, price_per_tb=5.0):
    raw = raw_gb * 1024 ** 3
    scenarios = {
        "CSV, no partitions": dict(fmt="csv"),
        "CSV, partitioned by date": dict(fmt="csv", partition_share=days_queried / days_total),
        "Parquet, no partitions": dict(fmt="parquet", compression=compression,
                                       column_share=columns_used / columns_total),
        "Parquet, partitioned by date": dict(fmt="parquet", compression=compression,
                                             column_share=columns_used / columns_total,
                                             partition_share=days_queried / days_total),
    }
    return {name: monthly_cost(raw, queries, price_per_tb, **kw) for name, kw in scenarios.items()}
