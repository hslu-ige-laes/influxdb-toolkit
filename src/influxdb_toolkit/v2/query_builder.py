"""Flux query builder."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
import re


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
    field_filter = " or ".join([f'r._field == "{_escape_flux_string(f)}"' for f in fields])
    query = [
        f'from(bucket: "{_escape_flux_string(bucket)}")',
        f'  |> range(start: {fmt_time(start)}, stop: {fmt_time(end)})',
        f'  |> filter(fn: (r) => r._measurement == "{_escape_flux_string(measurement)}")',
        f'  |> filter(fn: (r) => {field_filter})',
    ]
    if tags:
        for k, v in tags.items():
            query.append(
                f'  |> filter(fn: (r) => r["{_escape_flux_string(k)}"] == "{_escape_flux_string(v)}")'
            )
    if aggregation and interval:
        query.append(
            "  |> aggregateWindow("
            f"every: {_sanitize_interval(interval)}, "
            f"fn: {_sanitize_identifier(aggregation)}, "
            "createEmpty: false)"
        )
    query.append('  |> yield(name: "result")')
    return "\n".join(query)


def fmt_time(value: datetime) -> str:
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat()


def _escape_flux_string(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _sanitize_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Invalid identifier: {value}")
    return value


def _sanitize_interval(value: str) -> str:
    if not re.fullmatch(r"[0-9]+[A-Za-z]+", value):
        raise ValueError(f"Invalid interval: {value}")
    return value
