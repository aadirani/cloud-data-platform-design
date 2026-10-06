"""Data contracts: the agreed shape and rules of a dataset, checked on every row.

A contract is a JSON file (see contracts/trades.json). Rows that break it are not
"fixed" silently: they're quarantined with the reason.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

TIMESTAMP_FORMATS = ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"]


def load_contract(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_timestamp(text):
    """Accept the source system's known formats; always return UTC ISO-8601 with 'Z'."""
    for fmt in TIMESTAMP_FORMATS:
        try:
            dt = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    raise ValueError(f"unrecognised timestamp '{text}'")


def _convert(value, kind):
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    if kind == "string":
        return text
    if kind == "int":
        return int(text)
    if kind == "float":
        return float(text)
    if kind == "timestamp":
        return parse_timestamp(text)
    raise ValueError(f"unknown type {kind}")


def apply_contract(row, contract):
    """Return (clean_row, problems). clean_row has typed values and normalised text."""
    clean, problems = {}, []
    for name, rule in contract["columns"].items():
        raw = row.get(name)
        if rule.get("normalize") == "upper" and raw is not None:
            raw = str(raw).upper()
        try:
            value = _convert(raw, rule["type"])
        except ValueError as err:
            problems.append(f"{name}: {err}" if "timestamp" in str(err) else f"{name}: not a valid {rule['type']}")
            continue
        if value is None:
            if not rule.get("nullable", False):
                problems.append(f"{name}: missing")
            clean[name] = None
            continue
        if "allowed" in rule and value not in rule["allowed"]:
            problems.append(f"{name}: '{value}' not in {rule['allowed']}")
        if "pattern" in rule and not re.fullmatch(rule["pattern"], value):
            problems.append(f"{name}: '{value}' does not match {rule['pattern']}")
        if "min" in rule and value < rule["min"]:
            problems.append(f"{name}: {value} is below {rule['min']}")
        if "min_exclusive" in rule and value <= rule["min_exclusive"]:
            problems.append(f"{name}: {value} must be greater than {rule['min_exclusive']}")
        clean[name] = value
    return clean, problems
