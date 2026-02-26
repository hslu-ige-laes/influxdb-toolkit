import pandas as pd
from datetime import UTC, datetime, timedelta

from influxdb_toolkit.base import InfluxDBClientBase


class DummyClient(InfluxDBClientBase):
    def __init__(self):
        super().__init__(version=0, config={}, allow_write=False)

    def connect(self) -> None:
        self.connected = True

    def close(self) -> None:
        self.connected = False

    def ping(self) -> bool:
        return True

    def get_timeseries(self, measurement, fields, start, end, tags=None, interval=None, aggregation=None, timezone="UTC"):
        data = {
            "time": [start, end],
            "value": [1.0, 2.0],
        }
        return pd.DataFrame(data)

    def query_raw(self, query: str, timezone: str = "UTC") -> pd.DataFrame:
        return pd.DataFrame()

    def list_measurements(self, database=None):
        return []

    def get_tags(self, measurement: str, database=None):
        return []

    def get_tag_values(self, measurement: str, tag_key: str, database=None):
        return []

    def get_fields(self, measurement: str, database=None):
        return {}


def test_get_multiple_timeseries_merges():
    client = DummyClient()
    start = datetime.now(UTC) - timedelta(hours=1)
    end = datetime.now(UTC)
    df = client.get_multiple_timeseries(
        [
            {"measurement": "m1", "fields": ["value"], "start": start, "end": end},
            {"measurement": "m2", "fields": ["value"], "start": start, "end": end},
        ]
    )
    assert "time" in df.columns
    assert any(c.startswith("m1_") for c in df.columns)
    assert any(c.startswith("m2_") for c in df.columns)
