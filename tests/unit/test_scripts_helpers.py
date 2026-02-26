from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
from pathlib import Path

import pandas as pd
import pytest


def _load_script(module_name: str, relative_path: str):
    root = Path(__file__).resolve().parents[2]
    script_path = root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_smoke_v1_config_requires_database(monkeypatch) -> None:
    smoke = _load_script("smoke_read_for_test_v1", "scripts/smoke_read.py")
    monkeypatch.delenv("INFLUXDB_V1_DATABASE", raising=False)
    monkeypatch.delenv("INFLUXDB_DB", raising=False)
    with pytest.raises(ValueError, match="INFLUXDB_V1_DATABASE"):
        smoke._v1_config_from_env()


def test_smoke_v2_config_requires_token_org_bucket(monkeypatch) -> None:
    smoke = _load_script("smoke_read_for_test_v2", "scripts/smoke_read.py")
    monkeypatch.delenv("INFLUXDB_V2_TOKEN", raising=False)
    monkeypatch.delenv("INFLUXDB_TOKEN", raising=False)
    monkeypatch.delenv("INFLUXDB_V2_ORG", raising=False)
    monkeypatch.delenv("INFLUXDB_ORG", raising=False)
    monkeypatch.delenv("INFLUXDB_V2_BUCKET", raising=False)
    monkeypatch.delenv("INFLUXDB_BUCKET", raising=False)
    with pytest.raises(ValueError, match="INFLUXDB_V2_TOKEN"):
        smoke._v2_config_from_env()


def test_smoke_run_uses_client_and_closes(monkeypatch) -> None:
    smoke = _load_script("smoke_read_for_test_run", "scripts/smoke_read.py")

    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        def list_measurements(self):
            return ["m"]

        def get_tags(self, measurement):
            return ["sensor"]

        def get_fields(self, measurement):
            return {"value": "float"}

        def get_timeseries(self, **kwargs):
            return pd.DataFrame({"time": [datetime.now(UTC)], "value": [1.0]})

        def close(self):
            self.closed = True

    fake = FakeClient()
    monkeypatch.setattr(
        smoke,
        "_v1_config_from_env",
        lambda: {"host": "h", "port": 8086, "username": "", "password": "", "database": "db", "ssl": False},
    )
    monkeypatch.setattr(smoke.InfluxDBClientFactory, "get_client", lambda version, config: fake)

    rc = smoke.run(1)
    assert rc == 0
    assert fake.closed is True


def test_smoke_run_profile_uses_resolved_profile(monkeypatch) -> None:
    smoke = _load_script("smoke_read_for_test_profile", "scripts/smoke_read.py")
    calls: list[tuple[int, dict]] = []

    monkeypatch.setattr(smoke, "resolve_profile", lambda _name: (2, {"url": "u", "token": "t", "org": "o", "bucket": "b"}))
    monkeypatch.setattr(smoke, "_run_with_config", lambda version, config: calls.append((version, config)) or 0)

    rc = smoke.run_profile("v2_meteo")
    assert rc == 0
    assert calls == [(2, {"url": "u", "token": "t", "org": "o", "bucket": "b"})]


def test_schema_append_no_proxy_hosts_is_idempotent(monkeypatch) -> None:
    schema = _load_script("schema_report_for_test_proxy", "scripts/schema_report.py")
    monkeypatch.setenv("NO_PROXY", "localhost")
    schema._append_no_proxy_hosts({"host": "example.com", "url": "https://influx.example.org:8086"})
    schema._append_no_proxy_hosts({"host": "example.com", "url": "https://influx.example.org:8086"})

    values = [v.strip() for v in (schema.os.getenv("NO_PROXY") or "").split(",") if v.strip()]
    assert values.count("example.com") == 1
    assert values.count("influx.example.org") == 1


def test_schema_analyze_profile_handles_resolve_error(monkeypatch) -> None:
    schema = _load_script("schema_report_for_test_error", "scripts/schema_report.py")

    def _raise(_name):
        raise ValueError("bad profile")

    monkeypatch.setattr(schema, "resolve_profile", _raise)
    lines = schema._analyze_profile("broken", max_measurements=3)
    assert any("error resolving profile" in line for line in lines)


def test_schema_build_report_includes_run_info(monkeypatch) -> None:
    schema = _load_script("schema_report_for_test_report", "scripts/schema_report.py")
    monkeypatch.setattr(schema, "_analyze_profile", lambda name, max_measurements: [f"## Profile: `{name}`", ""])
    report = schema._build_report(["demo"], max_measurements=2)
    assert "# Data Structure Analysis" in report
    assert "generated_at_utc" in report
    assert "## Profile: `demo`" in report
