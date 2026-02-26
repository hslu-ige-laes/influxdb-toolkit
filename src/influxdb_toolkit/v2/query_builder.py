"""Flux query builder."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional


def build_flux_query(
    bucket: str,
    measurement: str,
    fields: List[str],
    start: datetime,
    end: datetime,
    tags: Optional[Dict[str, str]] = None,
    interval: Optional[str] = None,
    aggregation: Optional[str] = None,
) -> str:
    field_filter = " or ".join([f'r._field == "{f}"' for f in fields])
    query = [
        f'from(bucket: "{bucket}")',
        f'  |> range(start: {fmt_time(start)}, stop: {fmt_time(end)})',
        f'  |> filter(fn: (r) => r._measurement == "{measurement}")',
        f'  |> filter(fn: (r) => {field_filter})',
    ]
    if tags:
        for k, v in tags.items():
            query.append(f'  |> filter(fn: (r) => r["{k}"] == "{v}")')
    if aggregation and interval:
        query.append(f'  |> aggregateWindow(every: {interval}, fn: {aggregation}, createEmpty: false)')
    query.append('  |> yield(name: "result")')
    return "\n".join(query)


def fmt_time(value: datetime) -> str:
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat()