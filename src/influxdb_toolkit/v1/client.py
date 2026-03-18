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
        import urllib.request
        import ssl

        host = self.config.get("host", "")
        port = self.config.get("port", 8086)
        # Handle case where host already includes scheme (e.g. from ChronografProxyClient)
        if host.startswith("https://") or host.startswith("http://"):
            base_url = f"{host.rstrip('/')}:{port}" if f":{port}" not in host else host.rstrip("/")
        else:
            scheme = "https" if self.config.get("ssl") else "http"
            base_url = f"{scheme}://{host}:{port}"

        # Step 1: DNS / network reachability
        logger.info("Step 1/3: Testing network reachability → %s", base_url)
        try:
            ctx = ssl.create_default_context()
            if not self.config.get("verify_ssl", False):
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(f"{base_url}/ping", method="GET")
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                status = resp.status
            logger.info("  /ping HTTP %s – server reachable", status)
        except Exception as exc:
            self.connected = False
            raise InfluxDBConnectionError(
                f"Network/DNS error: cannot reach {base_url}/ping – {exc}"
            ) from exc

        # Step 2: Ping via client library
        logger.info("Step 2/3: Ping via InfluxDB client library")
        try:
            ok = self.ping()
            if not ok:
                raise InfluxDBConnectionError(
                    "Client ping returned False. Server reachable but client handshake failed."
                )
            logger.info("  Client ping OK")
        except InfluxDBConnectionError:
            self.connected = False
            raise
        except Exception as exc:
            self.connected = False
            raise InfluxDBConnectionError(f"Client ping error: {exc}") from exc

        # Step 3: Verify credentials & database access
        logger.info("Step 3/3: Verifying database access → '%s'", self._database)
        try:
            dbs = self._client.get_list_database()
            db_names = [d.get("name") for d in dbs]
            logger.info("  Accessible databases: %s", db_names)
            if self._database and self._database not in db_names:
                raise InfluxDBConnectionError(
                    f"Database '{self._database}' not found. "
                    f"Available: {db_names}. "
                    f"Check database name or credentials (user may lack access)."
                )
            logger.info("  Database '%s' confirmed accessible", self._database)
        except InfluxDBConnectionError:
            self.connected = False
            raise
        except Exception as exc:
            self.connected = False
            err_msg = str(exc)
            if "Expecting value" in err_msg or "JSONDecode" in type(exc).__name__:
                hint = (
                    f"Server returned empty/HTML response for SHOW DATABASES. "
                    f"This usually means authentication is required or a reverse proxy "
                    f"(e.g. Chronograf) is intercepting API requests. "
                    f"Username provided: {'yes' if self.config.get('username') else 'NO'}, "
                    f"Password provided: {'yes' if self.config.get('password') else 'NO'}. "
                    f"If using Chronograf, use ChronografProxyClient instead."
                )
            else:
                hint = f"Error: {exc}"
            raise InfluxDBConnectionError(
                f"Credential/database check failed: {hint}"
            ) from exc

        self.connected = True
        logger.info("Connection established successfully.")

    def close(self) -> None:
        if hasattr(self._client, "close"):
            self._client.close()
        self.connected = False

    def ping(self) -> bool:
        try:
            if hasattr(self._client, "ping"):
                version = self._client.ping()
                logger.debug("  ping response: %s", version)
            return True
        except Exception as exc:
            # Some reverse proxies (e.g. Chronograf) return 200 instead of 204
            # for /ping. The influxdb library treats 200 as an error.
            err_msg = str(exc)
            if "200" in err_msg:
                logger.debug("  ping returned 200 (proxy) – treating as OK")
                return True
            logger.warning("  ping failed: %s: %s", type(exc).__name__, exc)
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
            df["time"] = _parse_time_column(df["time"])
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
                df["time"] = _parse_time_column(df["time"])
                if timezone and timezone.upper() != "UTC":
                    df["time"] = df["time"].dt.tz_convert(timezone)
                    df["time"] = df["time"].dt.tz_localize(None)
                df = _move_time_first(df)
            return df
        except Exception as exc:
            raise InfluxDBQueryError(str(exc)) from exc

    def get_series(
        self,
        measurement: Optional[str] = None,
        database: Optional[str] = None,
    ) -> pd.DataFrame:
        if measurement:
            qry = f'SHOW SERIES FROM "{measurement}"'
        else:
            qry = "SHOW SERIES"
        try:
            result = self._client.query(qry, database=database or self._database)
            df_raw = pd.DataFrame(result.get_points())
        except Exception as exc:
            raise InfluxDBQueryError(str(exc)) from exc
        if df_raw.empty:
            return pd.DataFrame(columns=["measurement"])
        rows = []
        for _, row in df_raw.iterrows():
            key_str = row.get("key", "")
            parts = key_str.split(",")
            entry: Dict[str, str] = {"measurement": parts[0]}
            for part in parts[1:]:
                if "=" in part:
                    k, v = part.split("=", 1)
                    entry[k] = v
            rows.append(entry)
        return pd.DataFrame(rows)

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

    def get_schema(self, database: Optional[str] = None) -> pd.DataFrame:
        """Optimized: uses bulk SHOW TAG KEYS / SHOW FIELD KEYS (2 queries total)."""
        db = database or self._database
        try:
            # Bulk field keys: returns measurement + fieldKey + fieldType
            fk_result = self._client.query('SHOW FIELD KEYS', database=db)
            # Bulk tag keys: returns measurement + tagKey
            tk_result = self._client.query('SHOW TAG KEYS', database=db)
        except Exception as exc:
            raise InfluxDBQueryError(str(exc)) from exc

        # Extract series list from ResultSet (works with both standard influxdb
        # library ResultSet (.raw) and ChronografProxyClient _ResultSet (._raw))
        def _get_series(result_set: object) -> list:
            raw = getattr(result_set, "raw", None) or getattr(result_set, "_raw", {})
            # Standard: {"series": [...]}  /  Chronograf proxy: {"results": [{"series": [...]}]}
            if "series" in raw:
                return raw["series"]
            for r in raw.get("results", []):
                if "series" in r:
                    return r["series"]
            return []

        # Build tag lookup: measurement → sorted tag list
        tags_by_m: Dict[str, List[str]] = {}
        for series in _get_series(tk_result):
            m_name = series.get("name", "")
            cols = series.get("columns", [])
            for vals in series.get("values", []):
                row = dict(zip(cols, vals))
                tag = row.get("tagKey", "")
                if tag:
                    tags_by_m.setdefault(m_name, []).append(tag)
        for k in tags_by_m:
            tags_by_m[k] = sorted(set(tags_by_m[k]))

        # Build rows from field keys
        rows = []
        for series in _get_series(fk_result):
            m_name = series.get("name", "")
            cols = series.get("columns", [])
            tag_str = ", ".join(tags_by_m.get(m_name, []))
            for vals in series.get("values", []):
                row = dict(zip(cols, vals))
                rows.append({
                    "measurement": m_name,
                    "field": row.get("fieldKey", ""),
                    "type": row.get("fieldType", ""),
                    "tags": tag_str,
                })
        return pd.DataFrame(rows, columns=["measurement", "field", "type", "tags"])

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


def _parse_time_column(series: pd.Series) -> pd.Series:
    """Parse a time column that may contain ISO strings or integer timestamps.

    Auto-detects the unit by inspecting the magnitude of the first value:
      - > 1e18  → nanoseconds
      - > 1e15  → microseconds
      - > 1e12  → milliseconds
      - otherwise → seconds
    """
    import numpy as np
    sample = series.dropna().iloc[0] if not series.dropna().empty else None
    logger.debug("_parse_time_column: sample=%r, type=%s", sample, type(sample).__name__)
    if sample is not None and isinstance(sample, (int, float, np.integer, np.floating)):
        abs_val = abs(float(sample))
        if abs_val > 1e18:
            unit = "ns"
        elif abs_val > 1e15:
            unit = "us"
        elif abs_val > 1e12:
            unit = "ms"
        else:
            unit = "s"
        logger.debug("_parse_time_column: abs_val=%.0f → unit=%s", abs_val, unit)
        return pd.to_datetime(series, unit=unit, utc=True)
    return pd.to_datetime(series, utc=True)


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
