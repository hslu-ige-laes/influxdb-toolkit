"""Chronograf reverse-proxy adapter for InfluxDB v1.

Usage:
    from influxdb_toolkit.v1.chronograf_proxy import ChronografProxyClient
    from influxdb_toolkit import InfluxDBClientFactory

    proxy = ChronografProxyClient(
        base_url="https://influxdbv1.mdb.ige-hslu.io",
        username="placeholder",
        password="placeholder",
        database="meteoSwiss",
        source_id="1",
    )
    with InfluxDBClientFactory.get_client(version=1, config=proxy.toolkit_config, client=proxy) as client:
        print(client.list_measurements())
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Iterator, List, Optional
import warnings

import requests
from requests.auth import HTTPBasicAuth


class _ResultSet:
    """Minimal influxdb ResultSet-compatible wrapper around a raw JSON response."""

    def __init__(self, raw: Dict[str, Any]) -> None:
        self._raw = raw

    def get_points(self, measurement: Optional[str] = None) -> Iterator[Dict[str, Any]]:
        for result in self._raw.get("results", []):
            for series in result.get("series", []):
                if measurement and series.get("name") != measurement:
                    continue
                columns = series.get("columns", [])
                tags = series.get("tags", {})
                for row in series.get("values", []):
                    point = dict(zip(columns, row))
                    point.update(tags)
                    yield point


class ChronografProxyClient:
    """Mimics enough of influxdb.InfluxDBClient to work with InfluxDBClientV1.

    Parameters
    ----------
    base_url:
        HTTPS root of the Chronograf instance, e.g.
        ``"https://influxdbv1.mdb.ige-hslu.io"``.
    username / password:
        Chronograf HTTP Basic Auth credentials.
    database:
        Default InfluxDB database to query.
    source_id:
        Chronograf source ID (visible in /chronograf/v1/sources).
        Defaults to ``"1"``.
    verify_ssl:
        Whether to verify the TLS certificate.  Defaults to ``False``.
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        database: str,
        source_id: str = "1",
        verify_ssl: bool = False,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth = HTTPBasicAuth(username, password)
        self._database = database
        self._proxy_url = f"{self._base_url}/chronograf/v1/sources/{source_id}/proxy"
        self._write_url = f"{self._base_url}/chronograf/v1/sources/{source_id}/write"
        self._verify_ssl = verify_ssl
        self._session = requests.Session()
        self._session.auth = self._auth
        self._session.verify = verify_ssl
        if not verify_ssl:
            warnings.filterwarnings("ignore", message="Unverified HTTPS")

        # toolkit_config lets you pass straight into InfluxDBClientFactory
        self.toolkit_config: Dict[str, Any] = {
            "host": base_url,
            "port": 443,
            "username": username,
            "password": password,
            "database": database,
            "ssl": True,
            "verify_ssl": verify_ssl,
        }

    # ------------------------------------------------------------------
    # influxdb.InfluxDBClient-compatible interface
    # ------------------------------------------------------------------

    def ping(self) -> str:
        r = self._session.get(f"{self._base_url}/ping", timeout=10)
        return r.headers.get("X-Influxdb-Version", "ok")

    def query(self, query: str, database: Optional[str] = None) -> _ResultSet:
        db = database or self._database
        payload: Dict[str, str] = {"query": query}
        if db:
            payload["db"] = db
        r = self._session.post(self._proxy_url, json=payload, timeout=30)
        r.raise_for_status()
        return _ResultSet(r.json())

    def get_list_measurements(self) -> List[Dict[str, str]]:
        rs = self.query("SHOW MEASUREMENTS")
        return [{"name": p["name"]} for p in rs.get_points()]

    def get_list_database(self) -> List[Dict[str, str]]:
        rs = self.query("SHOW DATABASES")
        return [{"name": p["name"]} for p in rs.get_points()]

    def write_points(
        self,
        points: List[Dict[str, Any]],
        database: Optional[str] = None,
        **kwargs: Any,
    ) -> bool:
        """Write points via the Chronograf write proxy (line protocol)."""
        db = database or self._database
        lines: List[str] = []
        for p in points:
            measurement = p.get("measurement", "unknown")
            tags = p.get("tags", {})
            fields = p.get("fields", {})
            ts = p.get("time")

            tag_str = ""
            if tags:
                tag_str = "," + ",".join(f"{k}={v}" for k, v in tags.items())

            field_str = ",".join(
                f'{k}={v}' if isinstance(v, (int, float)) else f'{k}="{v}"'
                for k, v in fields.items()
            )
            line = f"{measurement}{tag_str} {field_str}"
            if ts:
                line += f" {int(ts.timestamp() * 1e9)}"
            lines.append(line)

        body = "\n".join(lines)
        r = self._session.post(
            self._write_url,
            params={"db": db},
            data=body,
            headers={"Content-Type": "application/octet-stream"},
            timeout=30,
        )
        r.raise_for_status()
        return True

    def close(self) -> None:
        self._session.close()
