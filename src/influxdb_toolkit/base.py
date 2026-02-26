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

    def __init__(self, version: int, config: Dict[str, Any], allow_write: bool = False) -> None:
        self.version = version
        self.config = config
        self.connected = False
        self._client = None
        self._allow_write = allow_write
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
        """Fetch time series data."""

    def get_multiple_timeseries(
        self,
        queries: List[Dict[str, object]],
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        interval: Optional[str] = None,
        aggregation: Optional[str] = None,
        timezone: str = "UTC",
    ) -> pd.DataFrame:
        """Fetch multiple time series and merge on time."""
        merged = pd.DataFrame()
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
        self._ensure_writes_allowed("delete_range")
        raise UnsupportedOperationError("delete_range not implemented for this client")

    def create_database(self, name: str) -> bool:
        self._ensure_writes_allowed("create_database")
        raise UnsupportedOperationError("create_database not implemented for this client")

    def delete_database(self, name: str) -> bool:
        self._ensure_writes_allowed("delete_database")
        raise UnsupportedOperationError("delete_database not implemented for this client")

    def create_bucket(self, name: str, retention: str = "0s") -> bool:
        self._ensure_writes_allowed("create_bucket")
        raise UnsupportedOperationError("create_bucket not implemented for this client")

    def create_user(self, username: str, password: str) -> bool:
        self._ensure_writes_allowed("create_user")
        raise UnsupportedOperationError("create_user not implemented for this client")

    def delete_user(self, username: str) -> bool:
        self._ensure_writes_allowed("delete_user")
        raise UnsupportedOperationError("delete_user not implemented for this client")

    def grant_privileges(self, user: str, database: str) -> bool:
        self._ensure_writes_allowed("grant_privileges")
        raise UnsupportedOperationError("grant_privileges not implemented for this client")

    def _ensure_writes_allowed(self, op: str) -> None:
        if not self._allow_write:
            raise UnsafeOperationError(
                f"{op} blocked. Set INFLUXDB_ALLOW_WRITE=true or allow_write=True in config."
            )

    def __repr__(self) -> str:
        status = "connected" if self.connected else "disconnected"
        writes = "writes_enabled" if self._allow_write else "read_only"
        return f"InfluxDBClient(v{self.version}, {status}, {writes})"


# -------------------- Helper functions --------------------

def _series_prefix(measurement: str, tags: Optional[Dict[str, str]]) -> str:
    if not tags:
        return measurement
    tag_part = "_".join([f"{k}={v}" for k, v in sorted(tags.items())])
    return f"{measurement}_{tag_part}"


def _prefix_columns(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    if df.empty:
        return df
    cols = list(df.columns)
    if "time" not in cols:
        return df
    rename_map = {col: f"{prefix}_{col}" for col in cols if col != "time"}
    return df.rename(columns=rename_map)


def _merge_on_time(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
    if left.empty:
        return right
    if right.empty:
        return left
    return left.merge(right, on="time", how="outer")
