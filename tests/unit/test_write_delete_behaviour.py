from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from influxdb_toolkit.exceptions import UnsafeOperationError, UnsupportedOperationError
from influxdb_toolkit.v1.client import InfluxDBClientV1
from influxdb_toolkit.v2.client import InfluxDBClientV2


class FakeResultSet:
    def __init__(self, points=None) -> None:
        self._points = points or []

    def get_points(self):
        yield from self._points


class FakeV1Client:
    def __init__(self) -> None:
        self.queries = []
        self.written = []

    def query(self, query, **kwargs):
        self.queries.append({"query": query, "kwargs": kwargs})
        return FakeResultSet([{"time": "2026-04-30T00:00:00Z", "value": 1.0}])

    def write_points(self, points):
        self.written.append(points)
        return True


class FakeDeleteApi:
    def __init__(self) -> None:
        self.calls = []

    def delete(self, start, end, predicate, bucket, org):
        self.calls.append(
            {
                "start": start,
                "end": end,
                "predicate": predicate,
                "bucket": bucket,
                "org": org,
            }
        )


class FakeWriteApi:
    def __init__(self) -> None:
        self.calls = []

    def write(self, bucket, org, record):
        self.calls.append({"bucket": bucket, "org": org, "record": record})


class FakeV2Client:
    def __init__(self) -> None:
        self._write_api = FakeWriteApi()
        self._delete_api = FakeDeleteApi()

    def write_api(self):
        return self._write_api

    def delete_api(self):
        return self._delete_api


def test_v1_simulated_write_points_allowed_when_enabled() -> None:
    fake = FakeV1Client()
    client = InfluxDBClientV1(
        host="localhost",
        port=8086,
        username="test",
        password="secret",
        database="testdb",
        allow_write=True,
        client=fake,
    )

    result = client.write_points(
        [{"fields": {"value": 12.3}, "time": datetime.now(UTC)}],
        measurement="temperature",
    )

    assert result.success is True
    assert result.details["points"] == 1
    assert fake.written[0][0]["measurement"] == "temperature"


def test_v2_simulated_write_dataframe_allowed_when_enabled() -> None:
    fake = FakeV2Client()
    client = InfluxDBClientV2(
        url="http://localhost:8087",
        token="token",
        org="hslu_ige",
        bucket="testbucket",
        allow_write=True,
        client=fake,
    )
    frame = pd.DataFrame(
        {
            "time": [datetime.now(UTC)],
            "sensor": ["s1"],
            "value": [12.3],
        }
    )

    result = client.write_dataframe(
        frame,
        measurement="temperature",
        tag_columns=["sensor"],
        field_columns=["value"],
    )

    assert result.success is True
    assert fake.write_api().calls[0]["bucket"] == "testbucket"
    assert fake.write_api().calls[0]["org"] == "hslu_ige"
    assert fake.write_api().calls[0]["record"][0]["tags"] == {"sensor": "s1"}


def test_v2_simulated_delete_range_allowed_when_enabled() -> None:
    fake = FakeV2Client()
    client = InfluxDBClientV2(
        url="http://localhost:8087",
        token="token",
        org="hslu_ige",
        bucket="testbucket",
        allow_write=True,
        allow_admin=True,
        client=fake,
    )
    start = datetime.now(UTC) - timedelta(hours=1)
    end = datetime.now(UTC)

    assert client.delete_range("temperature", start, end, tags={"sensor": "s1"}) is True

    assert fake.delete_api().calls == [
        {
            "start": start,
            "end": end,
            "predicate": '_measurement="temperature" and sensor="s1"',
            "bucket": "testbucket",
            "org": "hslu_ige",
        }
    ]


def test_v1_delete_range_is_not_implemented_even_when_writes_enabled() -> None:
    client = InfluxDBClientV1(
        host="localhost",
        port=8086,
        username="test",
        password="secret",
        database="testdb",
        allow_write=True,
        allow_admin=True,
        client=FakeV1Client(),
    )

    with pytest.raises(UnsupportedOperationError, match="delete_range not implemented"):
        client.delete_range("temperature", datetime.now(UTC) - timedelta(hours=1), datetime.now(UTC))


@pytest.mark.parametrize(
    "client",
    [
        InfluxDBClientV1(
            host="localhost",
            port=8086,
            username="test",
            password="secret",
            database="testdb",
            allow_write=False,
            client=FakeV1Client(),
        ),
        InfluxDBClientV2(
            url="http://localhost:8087",
            token="token",
            org="hslu_ige",
            bucket="testbucket",
            allow_write=False,
            client=FakeV2Client(),
        ),
    ],
)
def test_raw_delete_queries_are_blocked_when_writes_are_disabled(client) -> None:
    with pytest.raises(UnsafeOperationError, match="raw DELETE blocked"):
        client.query_raw('DELETE FROM "temperature" WHERE time < now()')


def test_raw_delete_queries_are_blocked_for_non_admin_writers() -> None:
    client = InfluxDBClientV1(
        host="localhost",
        port=8086,
        username="test",
        password="secret",
        database="testdb",
        allow_write=True,
        allow_admin=False,
        client=FakeV1Client(),
    )

    with pytest.raises(UnsafeOperationError, match="allow_admin=True"):
        client.query_raw('DELETE FROM "temperature" WHERE time < now()')


def test_v2_delete_range_is_blocked_for_non_admin_writers() -> None:
    client = InfluxDBClientV2(
        url="http://localhost:8087",
        token="token",
        org="hslu_ige",
        bucket="testbucket",
        allow_write=True,
        allow_admin=False,
        client=FakeV2Client(),
    )

    with pytest.raises(UnsafeOperationError, match="allow_admin=True"):
        client.delete_range("temperature", datetime.now(UTC) - timedelta(hours=1), datetime.now(UTC))


def test_raw_delete_queries_are_allowed_only_with_admin_permission() -> None:
    fake = FakeV1Client()
    client = InfluxDBClientV1(
        host="localhost",
        port=8086,
        username="admin",
        password="secret",
        database="testdb",
        allow_write=True,
        allow_admin=True,
        client=fake,
    )

    df = client.query_raw('DELETE FROM "temperature" WHERE time < now()', timezone="")

    assert df["value"].tolist() == [1.0]
    assert fake.queries[0]["query"] == 'DELETE FROM "temperature" WHERE time < now()'


def test_raw_create_queries_are_allowed_only_with_admin_permission() -> None:
    non_admin = InfluxDBClientV1(
        host="localhost",
        port=8086,
        username="test",
        password="secret",
        database="testdb",
        allow_write=True,
        allow_admin=False,
        client=FakeV1Client(),
    )
    with pytest.raises(UnsafeOperationError, match="allow_admin=True"):
        non_admin.query_raw('CREATE DATABASE "newdb"', timezone="")

    fake = FakeV1Client()
    admin = InfluxDBClientV1(
        host="localhost",
        port=8086,
        username="admin",
        password="secret",
        database="testdb",
        allow_write=True,
        allow_admin=True,
        client=fake,
    )
    admin.query_raw('CREATE DATABASE "newdb"', timezone="")

    assert fake.queries[0]["query"] == 'CREATE DATABASE "newdb"'


def test_raw_delete_detection_is_case_insensitive_and_ignores_quoted_text() -> None:
    client = InfluxDBClientV1(
        host="localhost",
        port=8086,
        username="test",
        password="secret",
        database="testdb",
        allow_write=True,
        allow_admin=False,
        client=FakeV1Client(),
    )

    client.query_raw('SELECT "delete" FROM "temperature"', timezone="")
    with pytest.raises(UnsafeOperationError, match="allow_admin=True"):
        client.query_raw('  /* harmless */ dElEtE FROM "temperature"', timezone="")


def test_high_risk_raw_admin_queries_are_disabled_even_when_admin_is_enabled() -> None:
    client = InfluxDBClientV1(
        host="localhost",
        port=8086,
        username="admin",
        password="secret",
        database="testdb",
        allow_write=True,
        allow_admin=True,
        client=FakeV1Client(),
    )

    for query, op in [
        ('DROP DATABASE "testdb"', "DROP"),
        ('ALTER RETENTION POLICY "rp" ON "testdb" DURATION 1h', "ALTER"),
        ('GRANT ALL ON "testdb" TO "user"', "GRANT"),
        ('REVOKE ALL ON "testdb" FROM "user"', "REVOKE"),
    ]:
        with pytest.raises(UnsupportedOperationError, match=f"raw {op} queries are disabled"):
            client.query_raw(query)


def test_v1_raw_select_query_still_executes() -> None:
    fake = FakeV1Client()
    client = InfluxDBClientV1(
        host="localhost",
        port=8086,
        username="test",
        password="secret",
        database="testdb",
        allow_write=False,
        client=fake,
    )

    df = client.query_raw('SELECT "value" FROM "temperature"', timezone="UTC")

    assert df["value"].tolist() == [1.0]
    assert fake.queries[0]["query"] == 'SELECT "value" FROM "temperature" tz(\'UTC\')'
