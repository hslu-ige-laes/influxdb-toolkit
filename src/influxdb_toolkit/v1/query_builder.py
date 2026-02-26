"""InfluxQL query builder."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
import re


def build_influxql_query(
    measurement: str,
    fields: List[str],
    start: datetime,
    end: datetime,
    tags: Optional[Dict[str, str]] = None,
    interval: Optional[str] = None,
    aggregation: Optional[str] = None,
    timezone: str = "UTC",
) -> str:
    field_exprs = _field_exprs(fields, aggregation)
    where = _time_condition(start, end)
    if tags:
        where += " AND " + _tags_condition(tags)
    query = f"SELECT {', '.join(field_exprs)} FROM {_quote_identifier(measurement)} WHERE {where}"
    if aggregation and interval:
        query += f" GROUP BY time({_sanitize_interval(interval)})"
    if timezone:
        query += f" TZ('{_escape_literal(timezone)}')"
    return query


def _field_exprs(fields: List[str], aggregation: Optional[str]) -> List[str]:
    if not aggregation:
        return [_quote_identifier(f) for f in fields]
    agg = _sanitize_identifier(aggregation)
    return [f"{agg}({_quote_identifier(f)})" for f in fields]


def _time_condition(start: datetime, end: datetime) -> str:
    start_s = _fmt_time(start)
    end_s = _fmt_time(end)
    return f"time >= '{start_s}' AND time < '{end_s}'"


def _tags_condition(tags: Dict[str, str]) -> str:
    return " AND ".join(
        [f"{_quote_identifier(k)} = '{_escape_literal(v)}'" for k, v in tags.items()]
    )


def _fmt_time(value: datetime) -> str:
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat()


def _quote_identifier(value: str) -> str:
    return f"\"{str(value).replace('\"', '\\\"')}\""


def _escape_literal(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def _sanitize_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Invalid identifier: {value}")
    return value


def _sanitize_interval(value: str) -> str:
    if not re.fullmatch(r"[0-9]+[A-Za-z]+", value):
        raise ValueError(f"Invalid interval: {value}")
    return value
