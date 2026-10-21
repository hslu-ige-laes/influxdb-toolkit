"""InfluxDB v2 implementation (Flux)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, Iterator, List, Optional
import logging
import pandas as pd
import requests

from ..base import InfluxDBClientBase
from ..exceptions import InfluxDBConnectionError, InfluxDBQueryError, UnsupportedOperationError
from ..models import WriteResult
from ..series import (
    OutputFormat,
    SeriesInfo,
    as_utc,
    csv_to_frame,
    time_windows,
    with_retry,
)
from .query_builder import (
    build_daily_count_query,
    build_flux_query,
    build_last_timestamp_query,
    build_series_discovery_query,
    build_series_range_query,
)

logger = logging.getLogger(__name__)


class InfluxDBClientV2(InfluxDBClientBase):
    """InfluxDB v2 client using Flux."""

    def __init__(
        self,
        url: str,
        token: str,
        org: str,
        bucket: Optional[str] = None,
        allow_write: bool = False,
        allow_admin: bool = False,
        client: Optional[object] = None,
    ) -> None:
        config = {
            "url": url,
            "token": token,
            "org": org,
            "bucket": bucket,
        }
        super().__init__(
            version=2,
            config=config,
            allow_write=allow_write,
            allow_admin=allow_admin,
        )
        if client is None:
            from influxdb_client import InfluxDBClient

            self._client = InfluxDBClient(url=url, token=token, org=org)
        else:
            self._client = client
        self._url = url.rstrip("/")
        self._token = token
        self._org = org
        self._bucket = bucket

    def connect(self) -> None:
        try:
            ok = self.ping()
            if not ok:
                raise InfluxDBConnectionError("Ping failed")
            self.connected = True
        except Exception as exc:
            self.connected = False
            raise InfluxDBConnectionError(str(exc)) from exc

    def close(self) -> None:
        if hasattr(self._client, "close"):
            self._client.close()
        self.connected = False

    def ping(self) -> bool:
        try:
            if hasattr(self._client, "ping"):
                self._client.ping()
            return True
        except Exception:
            return False

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
        if not self._bucket:
            raise ValueError("bucket is required for v2 queries")
        fields_list = [f for f in list(fields) if f]
        if not fields_list:
            raise ValueError("fields must contain at least one field name")
        query = build_flux_query(
            bucket=self._bucket,
            measurement=measurement,
            fields=fields_list,
            start=start,
            end=end,
            tags=tags,
            interval=interval,
            aggregation=aggregation,
        )
        logger.debug("Flux query: %s", query)
        try:
            df = self._client.query_api().query_data_frame(query, org=self._org)
        except Exception as exc:
            raise InfluxDBQueryError(str(exc)) from exc

        df = _normalize_flux_dataframe(df, timezone)
        return df

    # -------------------- Series-level bulk access --------------------

    def discover_series(
        self,
        start: Optional[datetime] = None,
        measurement: Optional[str] = None,
        retries: int = 3,
    ) -> List[SeriesInfo]:
        """List every existing series (measurement, tag set, field) with its
        last timestamp, sorted by key. ``start`` limits the search to series
        with data since then (default: all time)."""
        bucket = self._require_bucket()
        query = build_series_discovery_query(bucket, start=start, measurement=measurement)
        tables = with_retry(lambda: self._client.query_api().query(query, org=self._org), retries)
        result: List[SeriesInfo] = []
        for table in tables:
            for record in table.records:
                values: Dict[str, Any] = record.values
                tags = {
                    k: str(v)
                    for k, v in values.items()
                    if not k.startswith("_") and k not in {"result", "table"} and v is not None
                }
                last = values.get("_time")
                result.append(
                    SeriesInfo(
                        measurement=str(values["_measurement"]),
                        field=str(values["_field"]),
                        tags=tags,
                        last_time=as_utc(last) if isinstance(last, datetime) else None,
                    )
                )
        return sorted(result, key=lambda s: s.key)

    def iter_timeseries_chunks(
        self,
        measurement: str,
        field: str,
        start: datetime,
        end: datetime,
        tags: Optional[Dict[str, str]] = None,
        chunk: timedelta = timedelta(days=30),
        output: OutputFormat = "pandas",
        retries: int = 3,
    ) -> Iterator[Any]:
        """Raw samples of one series in ``[start, end)``, one frame per time
        window of ``chunk``. Frames have columns ``time`` (UTC) and ``value``
        and are pandas or polars DataFrames depending on ``output``. Pass the
        complete tag set of the series to avoid mixing series."""
        bucket = self._require_bucket()
        for lo, hi in time_windows(start, end, chunk):
            query = build_series_range_query(bucket, measurement, field, lo, hi, tags)
            yield csv_to_frame(with_retry(lambda q=query: self._query_csv(q), retries), output)

    def last_timestamp(
        self, measurement: str, field: str, tags: Optional[Dict[str, str]] = None
    ) -> Optional[datetime]:
        """Timestamp of the newest sample of a series (UTC), ``None`` if empty."""
        times = self._selector_times(measurement, field, tags, "last")
        return max(times) if times else None

    def first_timestamp(
        self, measurement: str, field: str, tags: Optional[Dict[str, str]] = None
    ) -> Optional[datetime]:
        """Timestamp of the oldest sample of a series (UTC), ``None`` if empty."""
        times = self._selector_times(measurement, field, tags, "first")
        return min(times) if times else None

    def _selector_times(
        self, measurement: str, field: str, tags: Optional[Dict[str, str]], selector: str
    ) -> List[datetime]:
        bucket = self._require_bucket()
        query = build_last_timestamp_query(bucket, measurement, field, tags, selector)
        tables = with_retry(lambda: self._client.query_api().query(query, org=self._org))
        times = [r.values.get("_time") for t in tables for r in t.records]
        return [as_utc(t) for t in times if isinstance(t, datetime)]

    def daily_counts(
        self,
        measurement: str,
        field: str,
        start: datetime,
        end: datetime,
        tags: Optional[Dict[str, str]] = None,
        output: OutputFormat = "pandas",
    ) -> Any:
        """Number of samples per UTC day (``time`` = day start, ``value`` = count),
        including days without data. Useful to detect gaps that were filled later."""
        bucket = self._require_bucket()
        query = build_daily_count_query(bucket, measurement, field, start, end, tags)
        return csv_to_frame(with_retry(lambda: self._query_csv(query)), output)

    def _query_csv(self, query: str) -> bytes:
        from influxdb_client import Dialect

        dialect = Dialect(header=True, delimiter=",", annotations=[], comment_prefix="#")
        response = self._client.query_api().query_raw(query, org=self._org, dialect=dialect)
        if isinstance(response, str):
            return response.encode("utf-8")
        if isinstance(response, bytes):
            return response
        return response.data

    def _require_bucket(self) -> str:
        if not self._bucket:
            raise ValueError("bucket is required for v2 queries")
        return self._bucket

    def query_raw(self, query: str, timezone: str = "UTC") -> pd.DataFrame:
        self._ensure_raw_query_allowed(query)
        if _is_influxql(query):
            return self._execute_influxql_compat(query, timezone)
        try:
            df = self._client.query_api().query_data_frame(query, org=self._org)
        except Exception as exc:
            raise InfluxDBQueryError(str(exc)) from exc
        return _normalize_flux_dataframe(df, timezone)

    def get_series(
        self,
        measurement: Optional[str] = None,
        database: Optional[str] = None,
    ) -> pd.DataFrame:
        bucket = database or self._bucket
        if not bucket:
            raise ValueError("bucket is required for v2 queries")
        # Use InfluxQL compatibility: SHOW SERIES works on v2 via /query endpoint
        if measurement:
            qry = f'SHOW SERIES FROM "{measurement}"'
        else:
            qry = "SHOW SERIES"
        try:
            df_raw = self._execute_influxql_compat(qry, timezone="")
        except Exception:
            # Fallback: build series from tag exploration
            return self._get_series_via_tags(measurement, bucket)
        if df_raw.empty:
            return pd.DataFrame(columns=["measurement"])
        rows: List[Dict[str, str]] = []
        col = "key" if "key" in df_raw.columns else df_raw.columns[0]
        for key_str in df_raw[col]:
            parts = str(key_str).split(",")
            entry: Dict[str, str] = {"measurement": parts[0]}
            for part in parts[1:]:
                if "=" in part:
                    k, v = part.split("=", 1)
                    entry[k] = v
            rows.append(entry)
        return pd.DataFrame(rows)

    def _get_series_via_tags(
        self, measurement: Optional[str], bucket: str
    ) -> pd.DataFrame:
        """Fallback when SHOW SERIES is unavailable: the distinct series that
        actually exist (Flux ``last()`` per series). Previously the cartesian
        product of all tag values was used, which reported non-existing series."""
        previous, self._bucket = self._bucket, bucket
        try:
            series = self.discover_series(measurement=measurement)
        finally:
            self._bucket = previous
        rows: List[Dict[str, str]] = []
        seen = set()
        for info in series:
            identity = (info.measurement, tuple(sorted(info.tags.items())))
            if identity in seen:
                continue
            seen.add(identity)
            rows.append({"measurement": info.measurement, **info.tags})
        if not rows:
            return pd.DataFrame(columns=["measurement"])
        return pd.DataFrame(rows)

    def list_measurements(self, database: Optional[str] = None) -> List[str]:
        bucket = database or self._bucket
        if not bucket:
            raise ValueError("bucket is required for v2 queries")
        query = f'''
import "influxdata/influxdb/schema"
schema.measurements(bucket: "{bucket}")
'''
        df = self._client.query_api().query_data_frame(query, org=self._org)
        df = _normalize_flux_dataframe(df, "UTC", pivot=False)
        return sorted({v for v in df.get("_value", []) if isinstance(v, str)})

    def get_tags(self, measurement: str, database: Optional[str] = None) -> List[str]:
        bucket = database or self._bucket
        if not bucket:
            raise ValueError("bucket is required for v2 queries")
        query = f'''
import "influxdata/influxdb/schema"
schema.tagKeys(
  bucket: "{bucket}",
  predicate: (r) => r._measurement == "{measurement}"
)
'''
        df = self._client.query_api().query_data_frame(query, org=self._org)
        df = _normalize_flux_dataframe(df, "UTC", pivot=False)
        values = sorted({v for v in df.get("_value", []) if isinstance(v, str)})
        return [v for v in values if v not in {"_start", "_stop", "_measurement", "_field"}]

    def get_tag_values(
        self, measurement: str, tag_key: str, database: Optional[str] = None
    ) -> List[str]:
        bucket = database or self._bucket
        if not bucket:
            raise ValueError("bucket is required for v2 queries")
        query = f'''
import "influxdata/influxdb/schema"
schema.tagValues(
  bucket: "{bucket}",
  tag: "{tag_key}",
  predicate: (r) => r._measurement == "{measurement}"
)
'''
        df = self._client.query_api().query_data_frame(query, org=self._org)
        df = _normalize_flux_dataframe(df, "UTC", pivot=False)
        return sorted({v for v in df.get("_value", []) if isinstance(v, str)})

    def get_fields(self, measurement: str, database: Optional[str] = None) -> Dict[str, str]:
        bucket = database or self._bucket
        if not bucket:
            raise ValueError("bucket is required for v2 queries")
        query = f'''
import "influxdata/influxdb/schema"
schema.fieldKeys(
  bucket: "{bucket}",
  predicate: (r) => r._measurement == "{measurement}"
)
'''
        df = self._client.query_api().query_data_frame(query, org=self._org)
        df = _normalize_flux_dataframe(df, "UTC", pivot=False)
        return {v: "" for v in sorted({v for v in df.get("_value", []) if isinstance(v, str)})}

    def get_schema(self, database: Optional[str] = None) -> pd.DataFrame:
        """Optimized: uses bulk Flux schema queries (2 queries total).

        Falls back to per-measurement queries when the bulk queries don't
        include the ``_measurement`` column (common on some InfluxDB v2 builds).
        """
        bucket = database or self._bucket
        if not bucket:
            raise ValueError("bucket is required for v2 queries")
        try:
            # Bulk field keys with measurement info
            fk_query = f'''
import "influxdata/influxdb/schema"
schema.fieldKeys(bucket: "{bucket}")
'''
            df_fields = self._client.query_api().query_data_frame(fk_query, org=self._org)
            df_fields = _normalize_flux_dataframe(df_fields, "UTC", pivot=False)

            # Check if bulk query includes measurement info
            has_measurement = (
                not df_fields.empty and "_measurement" in df_fields.columns
            )

            if not has_measurement:
                # Fallback: use the base class implementation which queries
                # per measurement (uses get_tags/get_fields with predicate).
                return InfluxDBClientBase.get_schema(self, database=database)

            # Bulk tag keys with measurement info
            tk_query = f'''
import "influxdata/influxdb/schema"
schema.tagKeys(bucket: "{bucket}")
'''
            df_tags = self._client.query_api().query_data_frame(tk_query, org=self._org)
            df_tags = _normalize_flux_dataframe(df_tags, "UTC", pivot=False)
        except Exception as exc:
            raise InfluxDBQueryError(str(exc)) from exc

        _IGNORED_TAGS = {"_start", "_stop", "_measurement", "_field"}

        # Build tag lookup: measurement → sorted tag list
        tags_by_m: Dict[str, List[str]] = {}
        if not df_tags.empty:
            m_col = "_measurement" if "_measurement" in df_tags.columns else None
            v_col = "_value" if "_value" in df_tags.columns else None
            if m_col and v_col:
                for _, row in df_tags.iterrows():
                    m_name = row[m_col]
                    tag = row[v_col]
                    if isinstance(tag, str) and tag not in _IGNORED_TAGS:
                        tags_by_m.setdefault(m_name, []).append(tag)
            elif v_col:
                all_tags = sorted({
                    v for v in df_tags[v_col]
                    if isinstance(v, str) and v not in _IGNORED_TAGS
                })
                tags_by_m["_all_"] = all_tags
        for k in tags_by_m:
            tags_by_m[k] = sorted(set(tags_by_m[k]))

        # Build rows from field keys
        rows = []
        if not df_fields.empty:
            v_col = "_value" if "_value" in df_fields.columns else None
            if v_col:
                for _, row in df_fields.iterrows():
                    m_name = row["_measurement"]
                    tag_list = tags_by_m.get(m_name, tags_by_m.get("_all_", []))
                    rows.append({
                        "measurement": m_name,
                        "field": row[v_col],
                        "type": "",
                        "tags": ", ".join(tag_list),
                    })
        return pd.DataFrame(rows, columns=["measurement", "field", "type", "tags"])

    def list_buckets(self) -> List[str]:
        buckets = self._client.buckets_api().find_buckets().buckets
        return [b.name for b in buckets]

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
        if not self._bucket:
            raise ValueError("bucket is required for v2 writes")
        if time_column not in df.columns:
            raise ValueError("time_column must exist in dataframe")
        fields = field_columns or [c for c in df.columns if c not in ([time_column] + (tag_columns or []))]
        points: List[Dict[str, object]] = []
        for _, row in df.iterrows():
            point = {
                "measurement": measurement,
                "time": row[time_column],
                "fields": {k: row[k] for k in fields},
            }
            if tag_columns:
                point["tags"] = {k: str(row[k]) for k in tag_columns}
            points.append(point)
        return self.write_points(points, measurement=measurement, batch_size=batch_size)

    def write_points(
        self,
        points: List[Dict[str, object]],
        measurement: str,
        batch_size: Optional[int] = None,
    ) -> WriteResult:
        self._ensure_writes_allowed("write_points")
        if not self._bucket:
            raise ValueError("bucket is required for v2 writes")
        if batch_size is not None and batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")
        for p in points:
            if "measurement" not in p:
                p["measurement"] = measurement
        try:
            from influxdb_client.client.write_api import SYNCHRONOUS

            write_api = self._client.write_api(write_options=SYNCHRONOUS)
        except TypeError:
            write_api = self._client.write_api()
        chunks = _chunk_points(points, batch_size)
        for chunk in chunks:
            write_api.write(bucket=self._bucket, org=self._org, record=chunk)
        return WriteResult(
            success=True,
            details={"points": len(points), "batch_size": batch_size, "batches": len(chunks)},
        )

    def delete_range(
        self,
        measurement: str,
        start: datetime,
        end: datetime,
        tags: Optional[Dict[str, str]] = None,
    ) -> bool:
        self._ensure_admin_allowed("delete_range")
        if not self._bucket:
            raise ValueError("bucket is required for v2 delete")
        predicate = f'_measurement="{measurement}"'
        if tags:
            tag_expr = " and ".join([f'{k}="{v}"' for k, v in tags.items()])
            predicate = f"{predicate} and {tag_expr}"
        self._client.delete_api().delete(start, end, predicate, self._bucket, self._org)
        return True

    def create_bucket(self, name: str, retention: str = "0s") -> bool:
        self._ensure_admin_allowed("create_bucket")
        # Deferred by project rule: do not execute real admin mutations yet.
        # retention_rules = None
        # if retention and retention != "0s":
        #     raise UnsupportedOperationError("retention parsing not implemented yet")
        # self._client.buckets_api().create_bucket(
        #     bucket_name=name, org=self._org, retention_rules=retention_rules
        # )
        raise UnsupportedOperationError("create_bucket is disabled until admin ops are approved")

    def create_database(self, name: str) -> bool:
        self._ensure_admin_allowed("create_database")
        # Deferred by project rule: do not execute real admin mutations yet.
        # return self.create_bucket(name=name)
        raise UnsupportedOperationError("create_database is disabled until admin ops are approved")

    def delete_database(self, name: str) -> bool:
        self._ensure_admin_allowed("delete_database")
        # Deferred by project rule: do not execute real admin mutations yet.
        # buckets_api = self._client.buckets_api()
        # if not hasattr(buckets_api, "find_bucket_by_name") or not hasattr(buckets_api, "delete_bucket"):
        #     raise UnsupportedOperationError("delete_database is not supported by this client")
        # bucket = buckets_api.find_bucket_by_name(name)
        # if bucket is None:
        #     raise InfluxDBQueryError(f"Bucket not found: {name}")
        # buckets_api.delete_bucket(bucket)
        raise UnsupportedOperationError("delete_database is disabled until admin ops are approved")

    def _execute_influxql_compat(self, query: str, timezone: str = "UTC") -> pd.DataFrame:
        if not self._bucket:
            raise ValueError("bucket is required for InfluxQL compatibility queries")
        qry = f"{query} tz('{timezone}')" if timezone else query
        headers = {
            "Authorization": f"Token {self._token}",
            "Accept": "application/json",
        }
        params = {"q": qry, "db": self._bucket}
        response = requests.get(f"{self._url}/query", headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            raise InfluxDBQueryError(f"InfluxQL query failed: {response.status_code} - {response.text}")
        result = response.json()
        if result.get("results") and "error" in result["results"][0]:
            raise InfluxDBQueryError(result["results"][0]["error"])
        return _influxql_result_to_df(result, timezone)


def _is_influxql(query: str) -> bool:
    q = query.strip().upper()
    return q.startswith(("SELECT", "SHOW", "CREATE", "DROP", "DELETE", "ALTER", "GRANT", "REVOKE"))


def _normalize_flux_dataframe(df: object, timezone: str, pivot: bool = True) -> pd.DataFrame:
    if isinstance(df, list):
        if not df:
            return pd.DataFrame()
        df = pd.concat(df, ignore_index=True)
    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame()
    if df.empty:
        return df
    if pivot and "_field" in df.columns and "_value" in df.columns:
        index_cols = [c for c in df.columns if c not in {"_field", "_value"}]
        if "_time" in index_cols:
            df = df.pivot_table(
                index=index_cols,
                columns="_field",
                values="_value",
                aggfunc="first",
            ).reset_index()
            if hasattr(df.columns, "name"):
                df.columns.name = None
    if "_time" in df.columns:
        df = df.rename(columns={"_time": "time"})
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=True)
        if timezone and timezone.upper() != "UTC":
            df["time"] = df["time"].dt.tz_convert(timezone)
            df["time"] = df["time"].dt.tz_localize(None)
        df = _move_time_first(df)
    return df


def _influxql_result_to_df(result: dict, timezone: str) -> pd.DataFrame:
    rows = []
    series_list = result.get("results", [{}])[0].get("series", [])
    for series in series_list:
        columns = series.get("columns", [])
        tags = series.get("tags", {})
        for values in series.get("values", []):
            row = dict(zip(columns, values))
            row.update(tags)
            rows.append(row)
    df = pd.DataFrame(rows)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=True)
        if timezone and timezone.upper() != "UTC":
            df["time"] = df["time"].dt.tz_convert(timezone)
            df["time"] = df["time"].dt.tz_localize(None)
        df = _move_time_first(df)
    return df


def _move_time_first(df: pd.DataFrame) -> pd.DataFrame:
    cols = list(df.columns)
    if cols and cols[0] != "time" and "time" in cols:
        cols = ["time"] + [c for c in cols if c != "time"]
        return df.reindex(columns=cols)
    return df


def _chunk_points(points: List[Dict[str, object]], batch_size: Optional[int]) -> List[List[Dict[str, object]]]:
    if not batch_size:
        return [points]
    return [points[i : i + batch_size] for i in range(0, len(points), batch_size)]
