"""InfluxQL query builder."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional


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
    query = f"SELECT {', '.join(field_exprs)} FROM \"{measurement}\" WHERE {where}"
    if aggregation and interval:
        query += f" GROUP BY time({interval})"
    if timezone:
        query += f" TZ('{timezone}')"
    return query


def _field_exprs(fields: List[str], aggregation: Optional[str]) -> List[str]:
    if not aggregation:
        return [f'"{f}"' for f in fields]
    return [f"{aggregation}(\"{f}\")" for f in fields]


def _time_condition(start: datetime, end: datetime) -> str:
    start_s = _fmt_time(start)
    end_s = _fmt_time(end)
    return f"time >= '{start_s}' AND time < '{end_s}'"


def _tags_condition(tags: Dict[str, str]) -> str:
    return " AND ".join([f'"{k}" = \'{v}\'' for k, v in tags.items()])


def _fmt_time(value: datetime) -> str:
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat()