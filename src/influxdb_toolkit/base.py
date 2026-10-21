"""Abstract base client for influxdb_toolkit."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional
import logging
import pandas as pd

from .exceptions import UnsafeOperationError, UnsupportedOperationError
from .models import MeasurementSchema, WriteResult


class InfluxDBClientBase(ABC):
    """Abstract base class for InfluxDB clients."""

    def __init__(
        self,
        version: int,
        config: Dict[str, Any],
        allow_write: bool = False,
        allow_admin: bool = False,
    ) -> None:
        self.version = version
        self.config = config
        self.connected = False
        self._client = None
        self._allow_write = allow_write
        self._allow_admin = allow_admin
        self.logger = logging.getLogger(f"{__name__}.v{version}")

    # -------------------- Connection management --------------------

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to InfluxDB."""

    @abstractmethod
    def close(self) -> None:
        """Close underlying client connections."""

    @abstractmethod
    def ping(self) -> bool:
        """Check if the server is responsive."""

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.close()
        return False

    # -------------------- Query methods --------------------

    @abstractmethod
    def get_timeseries(
        self,
        measurement: str,
        fields: Iterable[str],
        start: datetime,
        end: datetime,
        tags: Optional[Dict[str, str]] = None,
        interval: Optional[str] = None,
        aggregation: Optional[str] = None,
        timezone: str = "UTC",
    ) -> pd.DataFrame:
        """Fetch time series data as a DataFrame.

        Parameters
        ----------
        measurement : str
            Name of the measurement (e.g. ``"temperature"``).
        fields : Iterable[str]
            Field keys to retrieve (e.g. ``["value", "humidity"]``).
        start, end : datetime
            Time range (inclusive start, exclusive end). Timezone-aware recommended.
        tags : dict, optional
            Tag filters (e.g. ``{"device_id": "abc", "sensor": "temp"}``).
        interval : str, optional
            Aggregation window (e.g. ``"5m"``, ``"1h"``, ``"1d"``).
            Required when *aggregation* is set.
        aggregation : str, optional
            Aggregation function. Common values:

            - ``"mean"`` – arithmetic mean
            - ``"median"`` – median value
            - ``"sum"`` – sum of values
            - ``"count"`` – number of points
            - ``"min"`` / ``"max"`` – minimum / maximum
            - ``"first"`` / ``"last"`` – first / last point in window
            - ``"spread"`` – difference between min and max
            - ``"stddev"`` – standard deviation

            Must be used together with *interval*.
        timezone : str
            Output timezone (default ``"UTC"``). E.g. ``"Europe/Zurich"``.

        Returns
        -------
        pd.DataFrame
            Columns: ``time``, plus one column per field.
        """

    def get_multiple_timeseries(
        self,
        queries: List[Dict[str, object]],
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        interval: Optional[str] = None,
        aggregation: Optional[str] = None,
        timezone: str = "UTC",
        short_names: bool = False,
    ) -> pd.DataFrame:
        """Fetch multiple time series and merge on time.

        Parameters
        ----------
        short_names : bool
            If ``True``, column names use only the field name instead of
            the full ``measurement::tag=value::field`` prefix.
            Duplicate field names across queries get a numeric suffix.
        """
        merged = pd.DataFrame()
        seen_fields: Dict[str, int] = {}
        for query in queries:
            measurement = query.get("measurement")
            if not measurement:
                raise ValueError("measurement is required in each query")
            measurement = str(measurement)
            fields = query.get("fields")
            if fields is None:
                field_key = query.get("fieldKey", "value")
                fields = [field_key] if isinstance(field_key, str) else field_key
            if isinstance(fields, str):
                fields = [fields]
            tags = query.get("tags")
            q_start = query.get("start", start)
            q_end = query.get("end", end)
            if q_start is None or q_end is None:
                raise ValueError("start and end are required for get_multiple_timeseries")
            q_interval = query.get("interval", interval)
            q_aggregation = query.get("aggregation", aggregation)
            df = self.get_timeseries(
                measurement=measurement,
                fields=fields,
                start=q_start,
                end=q_end,
                tags=tags,
                interval=q_interval,
                aggregation=q_aggregation,
                timezone=timezone,
            )
            if df.empty:
                continue
            if short_names:
                # Deduplicate: append _2, _3, ... for repeated field names
                rename_map = {}
                for col in df.columns:
                    if col == "time":
                        continue
                    seen_fields[col] = seen_fields.get(col, 0) + 1
                    if seen_fields[col] > 1:
                        rename_map[col] = f"{col}_{seen_fields[col]}"
                if rename_map:
                    df = df.rename(columns=rename_map)
            else:
                prefix = _series_prefix(measurement, tags)
                df = _prefix_columns(df, prefix)
            merged = _merge_on_time(merged, df)
        return merged

    @abstractmethod
    def query_raw(self, query: str, timezone: str = "UTC") -> pd.DataFrame:
        """Execute a raw query string (InfluxQL or Flux)."""

    def get_results_from_qry(self, query: str, timezone: str = "UTC") -> pd.DataFrame:
        """Alias for query_raw (backward compatibility)."""
        return self.query_raw(query, timezone=timezone)

    # -------------------- Exploration methods --------------------

    @abstractmethod
    def list_measurements(self, database: Optional[str] = None) -> List[str]:
        """List available measurements."""

    @abstractmethod
    def get_tags(self, measurement: str, database: Optional[str] = None) -> List[str]:
        """List tag keys for a measurement."""

    @abstractmethod
    def get_tag_values(
        self, measurement: str, tag_key: str, database: Optional[str] = None
    ) -> List[str]:
        """List tag values for a tag key."""

    @abstractmethod
    def get_fields(self, measurement: str, database: Optional[str] = None) -> Dict[str, str]:
        """List field keys for a measurement with types if available."""

    @abstractmethod
    def get_series(
        self,
        measurement: Optional[str] = None,
        database: Optional[str] = None,
    ) -> pd.DataFrame:
        """List all series (measurement + tag combinations).

        Returns a DataFrame with columns: measurement, plus one column per tag key.
        If *measurement* is ``None``, series for **all** measurements are returned.
        """

    def get_all_series(self, database: Optional[str] = None) -> pd.DataFrame:
        """Convenience: get_series for all measurements in one call."""
        return self.get_series(measurement=None, database=database)

    def get_measurement_schema(
        self, measurement: str, database: Optional[str] = None
    ) -> MeasurementSchema:
        tags = self.get_tags(measurement, database=database)
        fields = self.get_fields(measurement, database=database)
        db_name = database or self.config.get("database") or self.config.get("bucket")
        return MeasurementSchema(
            measurement=measurement,
            tags=tags,
            fields=fields,
            database=db_name,
        )

    def get_schema(self, database: Optional[str] = None) -> pd.DataFrame:
        """Return a DataFrame with all measurements, their fields, types, and tags.

        Columns: measurement, field, type, tags
        """
        measurements = self.list_measurements(database=database)
        rows = []
        for m in measurements:
            tags = self.get_tags(m, database=database)
            fields = self.get_fields(m, database=database)
            for field_name, field_type in fields.items():
                rows.append({
                    "measurement": m,
                    "field": field_name,
                    "type": field_type,
                    "tags": ", ".join(tags),
                })
        return pd.DataFrame(rows, columns=["measurement", "field", "type", "tags"])

    def get_fields_per_series(
        self,
        measurement: Optional[str] = None,
        database: Optional[str] = None,
        ignore_fields: Optional[Iterable[str]] = None,
    ) -> pd.DataFrame:
        """Return a DataFrame with the actual (non-null) fields for each series.

        Columns: measurement, <tag1>, <tag2>, ..., fields, n_fields

        Uses one query per measurement (``LAST()`` grouped by tags) to detect
        which fields contain data for each tag combination.
        """
        ignore = set(ignore_fields) if ignore_fields else set()
        schema = self.get_schema(database=database)
        series = self.get_series(measurement=measurement, database=database)
        if series.empty or schema.empty:
            return pd.DataFrame(columns=["measurement", "fields", "n_fields"])

        tag_columns = [c for c in series.columns if c != "measurement"]
        known_tags = set(tag_columns) | {"time"}
        rows: List[Dict[str, Any]] = []

        measurements = [measurement] if measurement else sorted(series["measurement"].unique())
        for m in measurements:
            group = series[series["measurement"] == m]
            m_tags = [t for t in tag_columns if (group[t] != "–").any()] if tag_columns else []
            m_fields = schema.loc[
                (schema["measurement"] == m) & (~schema["field"].isin(ignore)),
                "field",
            ].tolist()
            if not m_fields:
                continue

            select_expr = ", ".join(f'LAST("{f}") AS "{f}"' for f in m_fields)
            group_by = ", ".join(f'"{t}"' for t in m_tags) if m_tags else ""
            q = f'SELECT {select_expr} FROM "{m}"'
            if group_by:
                q += f" GROUP BY {group_by}"

            try:
                df_sample = self.query_raw(q, timezone="")
            except Exception as exc:
                self.logger.warning("get_fields_per_series: query for %s failed: %s", m, exc)
                continue
            if df_sample.empty:
                continue

            for _, srow in df_sample.iterrows():
                non_null = [f for f in m_fields if f in srow.index and pd.notna(srow[f])]
                if not non_null:
                    continue
                entry: Dict[str, Any] = {"measurement": m}
                for t in m_tags:
                    entry[t] = srow.get(t, "–") if t in srow.index else "–"
                entry["fields"] = ", ".join(non_null)
                entry["n_fields"] = len(non_null)
                rows.append(entry)

        return pd.DataFrame(rows)

    # -------------------- Series-level bulk access --------------------
    # Implemented for v2; see InfluxDBClientV2 for documentation.

    def discover_series(self, start=None, measurement=None, retries: int = 3):
        raise UnsupportedOperationError(f"discover_series is not implemented for v{self.version}")

    def iter_timeseries_chunks(self, measurement, field, start, end, tags=None, **kwargs):
        raise UnsupportedOperationError(
            f"iter_timeseries_chunks is not implemented for v{self.version}"
        )

    def last_timestamp(self, measurement, field, tags=None):
        raise UnsupportedOperationError(f"last_timestamp is not implemented for v{self.version}")

    def first_timestamp(self, measurement, field, tags=None):
        raise UnsupportedOperationError(f"first_timestamp is not implemented for v{self.version}")

    def daily_counts(self, measurement, field, start, end, tags=None, output="pandas"):
        raise UnsupportedOperationError(f"daily_counts is not implemented for v{self.version}")

    def list_databases(self) -> List[str]:
        raise UnsupportedOperationError("list_databases is only supported for InfluxDB v1")

    def list_buckets(self) -> List[str]:
        raise UnsupportedOperationError("list_buckets is only supported for InfluxDB v2")

    # -------------------- Write methods (protected) --------------------

    def write_dataframe(
        self,
        df: pd.DataFrame,
        measurement: str,
        tag_columns: Optional[List[str]] = None,
        field_columns: Optional[List[str]] = None,
        time_column: str = "time",
        batch_size: Optional[int] = None,
    ) -> WriteResult:
        self._ensure_writes_allowed("write_dataframe")
        raise UnsupportedOperationError("write_dataframe not implemented for this client")

    def write_points(
        self,
        points: List[Dict[str, object]],
        measurement: str,
        batch_size: Optional[int] = None,
    ) -> WriteResult:
        self._ensure_writes_allowed("write_points")
        raise UnsupportedOperationError("write_points not implemented for this client")

    def delete_range(
        self,
        measurement: str,
        start: datetime,
        end: datetime,
        tags: Optional[Dict[str, str]] = None,
    ) -> bool:
        self._ensure_admin_allowed("delete_range")
        raise UnsupportedOperationError("delete_range not implemented for this client")

    def create_database(self, name: str) -> bool:
        self._ensure_admin_allowed("create_database")
        raise UnsupportedOperationError("create_database not implemented for this client")

    def delete_database(self, name: str) -> bool:
        self._ensure_admin_allowed("delete_database")
        raise UnsupportedOperationError("delete_database not implemented for this client")

    def create_bucket(self, name: str, retention: str = "0s") -> bool:
        self._ensure_admin_allowed("create_bucket")
        raise UnsupportedOperationError("create_bucket not implemented for this client")

    def create_user(self, username: str, password: str) -> bool:
        self._ensure_admin_allowed("create_user")
        raise UnsupportedOperationError("create_user not implemented for this client")

    def delete_user(self, username: str) -> bool:
        self._ensure_admin_allowed("delete_user")
        raise UnsupportedOperationError("delete_user not implemented for this client")

    def grant_privileges(self, user: str, database: str) -> bool:
        self._ensure_admin_allowed("grant_privileges")
        raise UnsupportedOperationError("grant_privileges not implemented for this client")

    def _ensure_writes_allowed(self, op: str) -> None:
        if not self._allow_write:
            raise UnsafeOperationError(
                f"{op} blocked. Set INFLUXDB_ALLOW_WRITE=true or allow_write=True in config."
            )

    def _ensure_admin_allowed(self, op: str) -> None:
        self._ensure_writes_allowed(op)
        if not self._allow_admin:
            raise UnsafeOperationError(
                f"{op} blocked. Set INFLUXDB_ALLOW_ADMIN=true or allow_admin=True in config."
            )

    def _ensure_raw_query_allowed(self, query: str) -> None:
        ops = _raw_query_operations(query)
        disabled_ops = sorted(ops.intersection({"DROP", "ALTER", "GRANT", "REVOKE"}))
        if disabled_ops:
            raise UnsupportedOperationError(
                f"raw {disabled_ops[0]} queries are disabled. Use explicit admin methods once approved."
            )
        if "CREATE" in ops:
            self._ensure_admin_allowed("raw CREATE")
        if "DELETE" in ops:
            self._ensure_admin_allowed("raw DELETE")

    def __repr__(self) -> str:
        status = "connected" if self.connected else "disconnected"
        writes = "writes_enabled" if self._allow_write else "read_only"
        admin = "admin_enabled" if self._allow_admin else "admin_disabled"
        return f"InfluxDBClient(v{self.version}, {status}, {writes}, {admin})"


# -------------------- Helper functions --------------------

def _series_prefix(measurement: str, tags: Optional[Dict[str, str]], sep: str = "::") -> str:
    if not tags:
        return measurement
    tag_part = sep.join([f"{k}={v}" for k, v in sorted(tags.items())])
    return f"{measurement}{sep}{tag_part}"


def _prefix_columns(df: pd.DataFrame, prefix: str, sep: str = "::") -> pd.DataFrame:
    if df.empty:
        return df
    cols = list(df.columns)
    if "time" not in cols:
        return df
    rename_map = {col: f"{prefix}{sep}{col}" for col in cols if col != "time"}
    return df.rename(columns=rename_map)


def _merge_on_time(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
    if left.empty:
        return right
    if right.empty:
        return left
    return left.merge(right, on="time", how="outer")


def _raw_query_operations(query: str) -> set[str]:
    return {
        token.upper()
        for token in _raw_query_tokens(query)
        if token.upper() in {"CREATE", "DROP", "DELETE", "ALTER", "GRANT", "REVOKE"}
    }


def _raw_query_tokens(query: str) -> List[str]:
    tokens: List[str] = []
    buf: List[str] = []
    i = 0
    quote = ""

    def flush() -> None:
        if buf:
            tokens.append("".join(buf))
            buf.clear()

    while i < len(query):
        ch = query[i]
        nxt = query[i + 1] if i + 1 < len(query) else ""

        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                if i + 1 < len(query) and query[i + 1] == quote:
                    i += 2
                    continue
                quote = ""
            i += 1
            continue

        if ch in {"'", '"'}:
            flush()
            quote = ch
            i += 1
            continue
        if ch == "#" or (ch == "-" and nxt == "-") or (ch == "/" and nxt == "/"):
            i = query.find("\n", i)
            if i == -1:
                break
            continue
        if ch == "/" and nxt == "*":
            i = query.find("*/", i + 2)
            if i == -1:
                break
            i += 2
            continue
        if ch.isalnum() or ch == "_":
            buf.append(ch)
        else:
            flush()
        i += 1

    flush()
    return tokens
