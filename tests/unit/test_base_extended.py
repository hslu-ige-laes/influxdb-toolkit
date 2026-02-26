from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from influxdb_toolkit.base import InfluxDBClientBase
from influxdb_toolkit.exceptions import UnsafeOperationError, UnsupportedOperationError


class RichDummyClient(InfluxDBClientBase):
    def __init__(self, config: dict | None = None, allow_write: bool = False) -> None:
        super().__init__(version=42, config=config or {}, allow_write=allow_write)
        self.connect_calls = 0
        self.close_calls = 0

    def connect(self) -> None:
        self.connect_calls += 1
        self.connected = True

    def close(self) -> None:
        self.close_calls += 1
        self.connected = False

    def ping(self) -> bool:
        return True

    def get_timeseries(
        self, measurement, fields, start, end, tags=None, interval=None, aggregation=None, timezone="UTC"
    ) -> pd.DataFrame:
        first = list(fields)[0]
        return pd.DataFrame({"time": [start, end], first: [1.0, 2.0]})

    def query_raw(self, query: str, timezone: str = "UTC") -> pd.DataFrame:
        return pd.DataFrame({"time": [], "value": []})

    def list_measurements(self, database=None):
        return ["m"]

    def get_tags(self, measurement: str, database=None):
        return ["sensor", "site"]

    def get_tag_values(self, measurement: str, tag_key: str, database=None):
        return ["a", "b"]

    def get_fields(self, measurement: str, database=None):
        return {"value": "float"}


def test_context_manager_connects_and_closes() -> None:
    client = RichDummyClient()
    with client as inside:
        assert inside.connected is True
    assert client.connected is False
    assert client.connect_calls == 1
    assert client.close_calls == 1


def test_get_multiple_timeseries_supports_fieldkey_alias_and_sorted_tags() -> None:
    client = RichDummyClient()
    start = datetime.now(UTC) - timedelta(hours=1)
    end = datetime.now(UTC)
    df = client.get_multiple_timeseries(
        [
            {
                "measurement": "power",
                "fieldKey": "value",
                "tags": {"b": "2", "a": "1"},
                "start": start,
                "end": end,
            }
        ]
    )
    assert "time" in df.columns
    assert "power_a=1_b=2_value" in df.columns


def test_get_multiple_timeseries_validates_measurement_and_range() -> None:
    client = RichDummyClient()
    start = datetime.now(UTC) - timedelta(hours=1)
    end = datetime.now(UTC)

    with pytest.raises(ValueError, match="measurement is required"):
        client.get_multiple_timeseries([{"fields": ["value"], "start": start, "end": end}])

    with pytest.raises(ValueError, match="start and end are required"):
        client.get_multiple_timeseries([{"measurement": "m", "fields": ["value"]}])


def test_get_measurement_schema_uses_default_and_override_database() -> None:
    client = RichDummyClient(config={"database": "default_db"})

    schema_default = client.get_measurement_schema("temperature")
    schema_override = client.get_measurement_schema("temperature", database="override_db")

    assert schema_default.database == "default_db"
    assert schema_default.tags == ["sensor", "site"]
    assert schema_default.fields == {"value": "float"}
    assert schema_override.database == "override_db"


def test_base_unsupported_methods_and_write_guard() -> None:
    client = RichDummyClient(allow_write=False)

    with pytest.raises(UnsupportedOperationError):
        client.list_databases()
    with pytest.raises(UnsupportedOperationError):
        client.list_buckets()
    with pytest.raises(UnsafeOperationError):
        client.write_points([{"fields": {"v": 1}}], measurement="m")


def test_repr_exposes_state_and_write_mode() -> None:
    client = RichDummyClient(allow_write=True)
    assert "disconnected" in repr(client)
    assert "writes_enabled" in repr(client)
    client.connect()
    assert "connected" in repr(client)
