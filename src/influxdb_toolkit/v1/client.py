"""InfluxDB v1 implementation (InfluxQL)."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List, Optional
import logging
import pandas as pd

from ..base import InfluxDBClientBase
from ..exceptions import InfluxDBConnectionError, InfluxDBQueryError, UnsupportedOperationError
from ..models import WriteResult
from .query_builder import build_influxql_query

logger = logging.getLogger(__name__)


class InfluxDBClientV1(InfluxDBClientBase):
    """InfluxDB v1 client using InfluxQL."""

    def __init__(
        self,
        host: str,
        port: int,
        username: Optional[str],
        password: Optional[str],
        database: Optional[str],
        ssl: bool = False,
        verify_ssl: bool = False,
        allow_write: bool = False,
        client: Optional[object] = None,
    ) -> None:
        config = {
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "database": database,
            "ssl": ssl,
            "verify_ssl": verify_ssl,
        }
        super().__init__(version=1, config=config, allow_write=allow_write)
        if client is None:
            from influxdb import InfluxDBClient

            self._client = InfluxDBClient(
                host=host,
                port=port,
                username=username,
                password=password,
                database=database,
                ssl=ssl,
                verify_ssl=verify_ssl,
            )
        else:
            self._client = client
        self._database = database

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
        fields_list = [f for f in list(fields) if f]
        if not fields_list:
            raise ValueError("fields must contain at least one field name")
        query = build_influxql_query(
            measurement=measurement,
            fields=fields_list,
            start=start,
            end=end,
            tags=tags,
            interval=interval,
            aggregation=aggregation,
            timezone=timezone,
        )
        logger.debug("InfluxQL query: %s", query)
        try:
            result = self._client.query(query)
            df = pd.DataFrame(result.get_points())
        except Exception as exc:
            raise InfluxDBQueryError(str(exc)) from exc

        if df.empty:
            return df
        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"], utc=True)
            if timezone and timezone.upper() != "UTC":
                df["time"] = df["time"].dt.tz_convert(timezone)
                df["time"] = df["time"].dt.tz_localize(None)
            df = _move_time_first(df)
        return df

    def query_raw(self, query: str, timezone: str = "UTC") -> pd.DataFrame:
        qry = f"{query} tz('{timezone}')" if timezone else query
        try:
            result = self._client.query(qry)
            df = pd.DataFrame(result.get_points())
            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"], utc=True)
                if timezone and timezone.upper() != "UTC":
                    df["time"] = df["time"].dt.tz_convert(timezone)
                    df["time"] = df["time"].dt.tz_localize(None)
                df = _move_time_first(df)
            return df
        except Exception as exc:
            raise InfluxDBQueryError(str(exc)) from exc

    def list_measurements(self, database: Optional[str] = None) -> List[str]:
        if database and database != self._database:
            qry = f'SHOW MEASUREMENTS ON "{database}"'
            result = self._client.query(qry)
            points = list(result.get_points())
            return [p.get("name") for p in points if "name" in p]
        measurements = self._client.get_list_measurements()
        return [m.get("name") for m in measurements if "name" in m]

    def get_tags(self, measurement: str, database: Optional[str] = None) -> List[str]:
        qry = f'SHOW TAG KEYS FROM "{measurement}"'
        if database:
            qry += f' ON "{database}"'
        result = self._client.query(qry)
        points = list(result.get_points())
        return [p.get("tagKey") for p in points if "tagKey" in p]

    def get_tag_values(
        self, measurement: str, tag_key: str, database: Optional[str] = None
    ) -> List[str]:
        qry = f'SHOW TAG VALUES FROM "{measurement}" WITH KEY = "{tag_key}"'
        if database:
            qry += f' ON "{database}"'
        result = self._client.query(qry)
        points = list(result.get_points())
        return [p.get("value") for p in points if "value" in p]

    def get_fields(self, measurement: str, database: Optional[str] = None) -> Dict[str, str]:
        qry = f'SHOW FIELD KEYS FROM "{measurement}"'
        if database:
            qry += f' ON "{database}"'
        result = self._client.query(qry)
        points = list(result.get_points())
        return {p.get("fieldKey"): p.get("fieldType") for p in points if "fieldKey" in p}

    def list_databases(self) -> List[str]:
        dbs = self._client.get_list_database()
        return [d.get("name") for d in dbs if "name" in d]

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
        if time_column not in df.columns:
            raise ValueError("time_column must exist in dataframe")
        fields = field_columns or [c for c in df.columns if c not in ([time_column] + (tag_columns or []))]
        points = []
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
        if batch_size is not None and batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")
        for p in points:
            if "measurement" not in p:
                p["measurement"] = measurement

        chunks = _chunk_points(points, batch_size)
        batches = 0
        overall_ok = True
        try:
            for chunk in chunks:
                batches += 1
                ok = bool(self._client.write_points(chunk))
                overall_ok = overall_ok and ok
            return WriteResult(
                success=overall_ok,
                details={"points": len(points), "batch_size": batch_size, "batches": batches},
            )
        except Exception as exc:
            raise InfluxDBQueryError(str(exc)) from exc

    def create_database(self, name: str) -> bool:
        self._ensure_writes_allowed("create_database")
        # Deferred by project rule: do not execute real admin mutations yet.
        # qry = f'CREATE DATABASE "{name}"'
        # self._client.query(qry)
        raise UnsupportedOperationError("create_database is disabled until admin ops are approved")

    def delete_database(self, name: str) -> bool:
        self._ensure_writes_allowed("delete_database")
        # Deferred by project rule: do not execute real admin mutations yet.
        # qry = f'DROP DATABASE "{name}"'
        # self._client.query(qry)
        raise UnsupportedOperationError("delete_database is disabled until admin ops are approved")

    def create_user(self, username: str, password: str) -> bool:
        self._ensure_writes_allowed("create_user")
        # Deferred by project rule: do not execute real admin mutations yet.
        # safe_pwd = password.replace("'", "\\'")
        # qry = f"CREATE USER \"{username}\" WITH PASSWORD '{safe_pwd}'"
        # self._client.query(qry)
        raise UnsupportedOperationError("create_user is disabled until admin ops are approved")

    def delete_user(self, username: str) -> bool:
        self._ensure_writes_allowed("delete_user")
        # Deferred by project rule: do not execute real admin mutations yet.
        # qry = f'DROP USER "{username}"'
        # self._client.query(qry)
        raise UnsupportedOperationError("delete_user is disabled until admin ops are approved")

    def grant_privileges(self, user: str, database: str) -> bool:
        self._ensure_writes_allowed("grant_privileges")
        # Deferred by project rule: do not execute real admin mutations yet.
        # qry = f'GRANT ALL ON "{database}" TO "{user}"'
        # self._client.query(qry)
        raise UnsupportedOperationError("grant_privileges is disabled until admin ops are approved")


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
