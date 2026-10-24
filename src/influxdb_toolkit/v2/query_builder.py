"""Flux query builder."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List, Optional
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


def build_series_discovery_query(
    bucket: str,
    start: Optional[datetime] = None,
    measurement: Optional[str] = None,
) -> str:
    """One row per existing series (measurement, tag set, field) with its last
    timestamp. ``last()`` is pushed down to the storage engine, so this is cheap
    even for large buckets."""
    query = [
        f'from(bucket: "{_escape_flux_string(bucket)}")',
        f"  |> range(start: {fmt_time(start) if start else '0'})",
    ]
    if measurement:
        query.append(
            f'  |> filter(fn: (r) => r._measurement == "{_escape_flux_string(measurement)}")'
        )
    query += [
        "  |> last()",
        '  |> drop(columns: ["_start", "_stop"])',  # _value tells the field type
    ]
    return "\n".join(query)


def build_series_filter(
    measurement: str,
    field: str,
    tags: Optional[Dict[str, str]] = None,
    absent_tags: Optional[Iterable[str]] = None,
) -> str:
    """Filter for exactly one series. ``absent_tags`` are tag keys the series does
    not have; requiring their absence keeps series with additional tags (e.g.
    ``room=1,sensor=x`` when asking for ``room=1``) out of the result."""
    conditions = [
        f'r._measurement == "{_escape_flux_string(measurement)}"',
        f'r._field == "{_escape_flux_string(field)}"',
    ]
    for k, v in sorted((tags or {}).items()):
        conditions.append(f'r["{_escape_flux_string(k)}"] == "{_escape_flux_string(v)}"')
    for k in sorted(set(absent_tags or ()) - set(tags or {})):
        conditions.append(f'not exists r["{_escape_flux_string(k)}"]')
    return f"  |> filter(fn: (r) => {' and '.join(conditions)})"


def build_series_range_query(
    bucket: str,
    measurement: str,
    field: str,
    start: datetime,
    end: datetime,
    tags: Optional[Dict[str, str]] = None,
    absent_tags: Optional[Iterable[str]] = None,
) -> str:
    """Raw samples of one series in ``[start, end)`` as ``_time``/``_value``."""
    return "\n".join([
        f'from(bucket: "{_escape_flux_string(bucket)}")',
        f"  |> range(start: {fmt_time(start)}, stop: {fmt_time(end)})",
        build_series_filter(measurement, field, tags, absent_tags),
        '  |> keep(columns: ["_time", "_value"])',
    ])


def build_last_timestamp_query(
    bucket: str,
    measurement: str,
    field: str,
    tags: Optional[Dict[str, str]] = None,
    selector: str = "last",
    absent_tags: Optional[Iterable[str]] = None,
) -> str:
    """Newest (``selector="last"``) or oldest (``"first"``) sample time."""
    if selector not in {"first", "last"}:
        raise ValueError("selector must be 'first' or 'last'")
    return "\n".join([
        f'from(bucket: "{_escape_flux_string(bucket)}")',
        "  |> range(start: 0)",
        build_series_filter(measurement, field, tags, absent_tags),
        f"  |> {selector}()",
        '  |> keep(columns: ["_time"])',
    ])


def build_daily_count_query(
    bucket: str,
    measurement: str,
    field: str,
    start: datetime,
    end: datetime,
    tags: Optional[Dict[str, str]] = None,
    absent_tags: Optional[Iterable[str]] = None,
) -> str:
    """Samples per UTC day, including empty days (count 0) for gap detection."""
    return "\n".join([
        f'from(bucket: "{_escape_flux_string(bucket)}")',
        f"  |> range(start: {fmt_time(start)}, stop: {fmt_time(end)})",
        build_series_filter(measurement, field, tags, absent_tags),
        '  |> aggregateWindow(every: 1d, fn: count, createEmpty: true, timeSrc: "_start")',
        '  |> keep(columns: ["_time", "_value"])',
    ])
