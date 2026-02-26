from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from influxdb_toolkit.exceptions import UnsafeOperationError
from influxdb_toolkit.v1.client import InfluxDBClientV1
from influxdb_toolkit.v2.client import InfluxDBClientV2


class FakeV1Client:
    def __init__(self) -> None:
        self.written_batches = []

    def write_points(self, points):
        self.written_batches.append(points)
        return True


class FakeWriteApi:
    def __init__(self) -> None:
        self.calls = []

    def write(self, bucket, org, record):
        self.calls.append({"bucket": bucket, "org": org, "record": record})


class FakeV2Client:
    def __init__(self) -> None:
        self._write_api = FakeWriteApi()

    def write_api(self):
        return self._write_api


def test_v1_write_points_batching() -> None:
    fake = FakeV1Client()
    client = InfluxDBClientV1(
        host="localhost",
        port=8086,
        username=None,
        password=None,
        database="db",
        allow_write=True,
        client=fake,
    )
    points = [{"fields": {"value": i}, "time": datetime.now(UTC)} for i in range(5)]
    result = client.write_points(points, measurement="m", batch_size=2)

    assert result.success is True
    assert result.details["batches"] == 3
    assert len(fake.written_batches) == 3
    assert all(batch[0]["measurement"] == "m" for batch in fake.written_batches if batch)


def test_v1_write_dataframe_batching() -> None:
    fake = FakeV1Client()
    client = InfluxDBClientV1(
        host="localhost",
        port=8086,
        username=None,
        password=None,
        database="db",
        allow_write=True,
        client=fake,
    )
    df = pd.DataFrame(
        {
            "time": [datetime.now(UTC), datetime.now(UTC), datetime.now(UTC)],
            "value": [1.0, 2.0, 3.0],
            "sensor": ["a", "a", "b"],
        }
    )

    result = client.write_dataframe(
        df,
        measurement="temperature",
        tag_columns=["sensor"],
        field_columns=["value"],
        batch_size=2,
    )

    assert result.success is True
    assert result.details["batches"] == 2
    assert len(fake.written_batches) == 2


def test_v2_write_points_batching() -> None:
    fake = FakeV2Client()
    client = InfluxDBClientV2(
        url="http://localhost:8086",
        token="token",
        org="org",
        bucket="bucket",
        allow_write=True,
        client=fake,
    )
    points = [{"measurement": "m", "fields": {"value": i}, "time": datetime.now(UTC)} for i in range(5)]
    result = client.write_points(points, measurement="m", batch_size=2)

    assert result.success is True
    assert result.details["batches"] == 3
    assert len(fake.write_api().calls) == 3


def test_write_guard_blocks_when_disabled() -> None:
    fake = FakeV1Client()
    client = InfluxDBClientV1(
        host="localhost",
        port=8086,
        username=None,
        password=None,
        database="db",
        allow_write=False,
        client=fake,
    )
    with pytest.raises(UnsafeOperationError):
        client.write_points([{"fields": {"value": 1}}], measurement="m")
