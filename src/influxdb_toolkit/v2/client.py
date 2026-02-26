"""InfluxDB v2 implementation (Flux)."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List, Optional
import logging
import pandas as pd
import requests

from ..base import InfluxDBClientBase
from ..exceptions import InfluxDBConnectionError, InfluxDBQueryError, UnsupportedOperationError
from ..models import WriteResult
from .query_builder import build_flux_query

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
        client: Optional[object] = None,
    ) -> None:
        config = {
            "url": url,
            "token": token,
            "org": org,
            "bucket": bucket,
        }
        super().__init__(version=2, config=config, allow_write=allow_write)
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

    def query_raw(self, query: str, timezone: str = "UTC") -> pd.DataFrame:
        if _is_influxql(query):
            return self._execute_influxql_compat(query, timezone)
        try:
            df = self._client.query_api().query_data_frame(query, org=self._org)
        except Exception as exc:
            raise InfluxDBQueryError(str(exc)) from exc
        return _normalize_flux_dataframe(df, timezone)

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
        return [v for v in values if v not in {"_start", "_stop", "_measurement"}]

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
        self._ensure_writes_allowed("delete_range")
        if not self._bucket:
            raise ValueError("bucket is required for v2 delete")
        predicate = f'_measurement="{measurement}"'
        if tags:
            tag_expr = " and ".join([f'{k}="{v}"' for k, v in tags.items()])
            predicate = f"{predicate} and {tag_expr}"
        self._client.delete_api().delete(start, end, predicate, self._bucket, self._org)
        return True

    def create_bucket(self, name: str, retention: str = "0s") -> bool:
        self._ensure_writes_allowed("create_bucket")
        # Deferred by project rule: do not execute real admin mutations yet.
        # retention_rules = None
        # if retention and retention != "0s":
        #     raise UnsupportedOperationError("retention parsing not implemented yet")
        # self._client.buckets_api().create_bucket(
        #     bucket_name=name, org=self._org, retention_rules=retention_rules
        # )
        raise UnsupportedOperationError("create_bucket is disabled until admin ops are approved")

    def create_database(self, name: str) -> bool:
        self._ensure_writes_allowed("create_database")
        # Deferred by project rule: do not execute real admin mutations yet.
        # return self.create_bucket(name=name)
        raise UnsupportedOperationError("create_database is disabled until admin ops are approved")

    def delete_database(self, name: str) -> bool:
        self._ensure_writes_allowed("delete_database")
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
        df = df.pivot_table(index="_time", columns="_field", values="_value", aggfunc="first").reset_index()
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
