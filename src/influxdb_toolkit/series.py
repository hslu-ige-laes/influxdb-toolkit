"""Series-level helpers for bulk access: identity, time windows, frame conversion.

A *series* is one (measurement, tag set, field) combination - the unit that
tools like local caches or explorers store and display.
"""

from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterator, Literal, Optional, Tuple, TypeVar

import pandas as pd

from .exceptions import InfluxDBQueryError

logger = logging.getLogger(__name__)

OutputFormat = Literal["pandas", "polars"]
T = TypeVar("T")


@dataclass(frozen=True)
class SeriesInfo:
    """One series: measurement + tag set + field.

    ``first_time``/``last_time`` are filled when the discovery query provides
    them (timezone-aware UTC).
    """

    measurement: str
    field: str
    tags: Dict[str, str] = field(default_factory=dict)
    first_time: Optional[datetime] = None
    last_time: Optional[datetime] = None
    value_type: Optional[str] = None  # "number", "string" or "bool" (from the last value)

    @property
    def key(self) -> str:
        """Readable, unique path ``measurement/tag=value/.../field`` (tags sorted).
        ``%``, ``/`` and ``=`` inside names are percent-encoded."""
        parts = [_escape(self.measurement)]
        parts += [f"{_escape(k)}={_escape(v)}" for k, v in sorted(self.tags.items())]
        parts.append(_escape(self.field))
        return "/".join(parts)

    @classmethod
    def from_key(cls, key: str) -> "SeriesInfo":
        """Inverse of :attr:`key`."""
        parts = key.split("/")
        if len(parts) < 2:
            raise ValueError(f"Invalid series key: {key}")
        tags = {}
        for part in parts[1:-1]:
            k, v = part.split("=", 1)
            tags[_unescape(k)] = _unescape(v)
        return cls(measurement=_unescape(parts[0]), field=_unescape(parts[-1]), tags=tags)


def _escape(text: str) -> str:
    return text.replace("%", "%25").replace("/", "%2F").replace("=", "%3D")


def _unescape(text: str) -> str:
    return text.replace("%3D", "=").replace("%2F", "/").replace("%25", "%")


def value_type_of(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    return "string"


def as_utc(value: datetime) -> datetime:
    """Interpret naive datetimes as UTC and convert aware ones to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def time_windows(
    start: datetime, end: datetime, chunk: timedelta
) -> Iterator[Tuple[datetime, datetime]]:
    """Split ``[start, end)`` into consecutive windows of at most ``chunk``."""
    if chunk <= timedelta(0):
        raise ValueError("chunk must be positive")
    lo, hi = as_utc(start), as_utc(end)
    while lo < hi:
        nxt = min(lo + chunk, hi)
        yield lo, nxt
        lo = nxt


_TRANSIENT_NAMES = {
    "ConnectionError", "TimeoutError", "MaxRetryError", "NewConnectionError",
    "ProtocolError", "ReadTimeoutError", "ConnectTimeoutError", "RemoteDisconnected",
}


def is_transient(exc: BaseException) -> bool:
    """Network problems, 5xx and 429 are worth retrying; other 4xx (e.g. a wrong
    token or an unknown bucket) and query errors are not."""
    status = getattr(exc, "status", None)
    if isinstance(status, int):
        return status >= 500 or status == 429
    return any(cls.__name__ in _TRANSIENT_NAMES for cls in type(exc).__mro__)


def with_retry(fn: Callable[[], T], retries: int = 3, backoff_s: float = 1.0) -> T:
    """Call ``fn``; retry transient errors (see :func:`is_transient`) with
    exponential backoff. Other errors are raised at once as InfluxDBQueryError."""
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - network errors come in many types
            if not is_transient(exc):
                if isinstance(exc, InfluxDBQueryError):
                    raise
                raise InfluxDBQueryError(str(exc)) from exc
            if attempt == retries:
                raise InfluxDBQueryError(f"Query failed after {retries + 1} attempts: {exc}") from exc
            wait = backoff_s * 2**attempt
            logger.warning("Query failed (%s), retrying in %.1f s", exc, wait)
            time.sleep(wait)
    raise AssertionError("unreachable")


def empty_frame(output: OutputFormat) -> Any:
    if output == "polars":
        pl = _polars()
        return pl.DataFrame(schema={"time": pl.Datetime("us", "UTC"), "value": pl.Float64})
    return pd.DataFrame({"time": pd.Series([], dtype="datetime64[ns, UTC]"),
                         "value": pd.Series([], dtype="float64")})


def csv_to_frame(data: bytes, output: OutputFormat) -> Any:
    """Convert annotation-free Flux CSV (columns ``_time``, ``_value``) to a
    ``time``/``value`` frame with UTC timestamps. ``value`` is numeric; a string field
    (texts that are not numbers, e.g. a gateway id) keeps its texts instead of
    becoming all-null."""
    if not data.strip():
        return empty_frame(output)
    if output == "polars":
        pl = _polars()
        df = pl.read_csv(io.BytesIO(data), columns=["_time", "_value"], infer_schema_length=0)
        raw = df.get_column("_value")
        is_text = raw.cast(pl.Float64, strict=False).null_count() > raw.null_count()
        value = pl.col("_value") if is_text else pl.col("_value").cast(pl.Float64, strict=False)
        return df.select(
            pl.col("_time").str.to_datetime(time_zone="UTC", time_unit="us").alias("time"),
            value.alias("value"),
        )
    df = pd.read_csv(io.BytesIO(data), usecols=["_time", "_value"])
    numeric = pd.to_numeric(df["_value"], errors="coerce")
    is_text = numeric.isna().sum() > df["_value"].isna().sum()
    return pd.DataFrame({
        "time": pd.to_datetime(df["_time"], utc=True, format="ISO8601"),
        "value": df["_value"].astype("string") if is_text else numeric,
    })


def _polars() -> Any:
    try:
        import polars as pl
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ImportError(
            "output='polars' requires polars: pip install influxdb-toolkit[polars]"
        ) from exc
    return pl
