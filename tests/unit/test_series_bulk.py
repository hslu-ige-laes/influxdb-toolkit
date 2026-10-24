"""Tests for series-level bulk access (v2) with a fake influxdb_client."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from influxdb_toolkit.exceptions import InfluxDBQueryError, UnsupportedOperationError
from influxdb_toolkit.series import SeriesInfo, csv_to_frame, time_windows, with_retry
from influxdb_toolkit.v2.client import InfluxDBClientV2
from influxdb_toolkit.v2.query_builder import (
    build_daily_count_query,
    build_series_discovery_query,
    build_series_range_query,
)

UTC = timezone.utc


class FakeQueryApi:
    def __init__(self, tables=None, csv_by_window=None, tag_keys=()):
        self.tag_keys = list(tag_keys)
        self.tables = tables or []
        self.csv_by_window = csv_by_window or {}
        self.queries = []

    def query(self, query, org=None):
        self.queries.append(query)
        return self.tables

    def query_data_frame(self, query, org=None):
        self.queries.append(query)
        return pd.DataFrame({"_value": self.tag_keys})

    def query_raw(self, query, org=None, dialect=None):
        self.queries.append(query)
        for marker, data in self.csv_by_window.items():
            if marker in query:
                return SimpleNamespace(data=data)
        return SimpleNamespace(data=b"")


class FakeClient:
    def __init__(self, api):
        self.api = api

    def query_api(self):
        return self.api


def table(*records):
    return SimpleNamespace(records=[SimpleNamespace(values=v) for v in records])


def make_client(api):
    return InfluxDBClientV2(url="http://x", token="t", org="o", bucket="b", client=FakeClient(api))


def test_series_key_roundtrip():
    info = SeriesInfo("temp", "value", {"room": "204", "bldg": "A"})
    assert info.key == "temp/bldg=A/room=204/value"
    back = SeriesInfo.from_key(info.key)
    assert (back.measurement, back.field, back.tags) == ("temp", "value", info.tags)


def test_series_key_escapes_separators():
    info = SeriesInfo("a/b", "f=1", {"path": "x/y=z", "pct": "50%"})
    back = SeriesInfo.from_key(info.key)
    assert (back.measurement, back.field, back.tags) == ("a/b", "f=1", info.tags)
    assert info.key.count("/") == 3


def test_time_windows_cover_range():
    start = datetime(2025, 1, 1, tzinfo=UTC)
    windows = list(time_windows(start, start + timedelta(days=65), timedelta(days=30)))
    assert len(windows) == 3
    assert windows[0][0] == start and windows[-1][1] == start + timedelta(days=65)
    assert all(a[1] == b[0] for a, b in zip(windows, windows[1:]))


def test_naive_datetimes_are_utc():
    (lo, _), = time_windows(datetime(2025, 1, 1), datetime(2025, 1, 2), timedelta(days=5))
    assert lo.tzinfo == UTC


def test_discover_series_returns_existing_series_only():
    last = datetime(2025, 6, 1, 12, tzinfo=UTC)
    api = FakeQueryApi(tables=[
        table({"result": "_result", "table": 0, "_measurement": "temp", "_field": "value",
               "room": "1", "_time": last, "_value": 21.5}),
        table({"result": "_result", "table": 1, "_measurement": "temp", "_field": "value",
               "room": "2", "_time": last, "_value": "eui-a81758fffe0"}),
    ])
    series = make_client(api).discover_series()
    assert [s.key for s in series] == ["temp/room=1/value", "temp/room=2/value"]
    assert series[0].last_time == last
    assert [s.value_type for s in series] == ["number", "string"]
    assert "_value" not in series[0].tags
    assert "last()" in api.queries[0] and "range(start: 0)" in api.queries[0]


def test_get_series_fallback_is_not_cartesian(monkeypatch):
    api = FakeQueryApi(tables=[
        table({"_measurement": "m", "_field": "f", "a": "1", "b": "x"}),
        table({"_measurement": "m", "_field": "g", "a": "1", "b": "x"}),
        table({"_measurement": "m", "_field": "f", "a": "2", "b": "y"}),
    ])
    client = make_client(api)
    df = client._get_series_via_tags(None, "b")
    # cartesian product would give 4 combinations; only 2 series exist
    assert len(df) == 2
    assert set(zip(df["a"], df["b"])) == {("1", "x"), ("2", "y")}


@pytest.mark.parametrize("output", ["pandas", "polars"])
def test_iter_timeseries_chunks(output):
    pytest.importorskip(output)
    jan = b"_time,_value\r\n2025-01-01T00:00:00Z,1.5\r\n2025-01-01T00:01:00Z,2\r\n"
    feb = b"_time,_value\r\n2025-02-01T00:00:00Z,3\r\n"
    api = FakeQueryApi(csv_by_window={"2025-01-01T00:00:00+00:00": jan,
                                      "2025-01-31T00:00:00+00:00": feb})
    client = make_client(api)
    chunks = list(client.iter_timeseries_chunks(
        "temp", "value", datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 3, 1, tzinfo=UTC),
        tags={"room": "1"}, chunk=timedelta(days=30), output=output,
    ))
    assert len(chunks) == 2
    values = [v for c in chunks for v in list(c["value"])]
    assert values == [1.5, 2.0, 3.0]
    assert 'r["room"] == "1"' in api.queries[1]  # [0] = cached tag keys
    first_time = chunks[0]["time"][0]
    assert str(first_time).startswith("2025-01-01 00:00:00")


def test_empty_chunk():
    df = csv_to_frame(b"\r\n", "pandas")
    assert df.empty and list(df.columns) == ["time", "value"]
    assert str(df["time"].dtype) == "datetime64[ns, UTC]"


def test_chunks_exclude_series_with_additional_tags():
    api = FakeQueryApi(tag_keys=["room", "sensor"])
    client = make_client(api)
    window = (datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 1, 2, tzinfo=UTC))
    list(client.iter_timeseries_chunks("temp", "value", *window, tags={"room": "1"}))
    query = api.queries[-1]
    assert 'r["room"] == "1"' in query
    assert 'not exists r["sensor"]' in query
    assert 'not exists r["room"]' not in query
    list(client.iter_timeseries_chunks("temp", "value", *window, tags={"room": "1"}))
    assert sum("schema.tagKeys" in q for q in api.queries) == 1  # cached


def test_non_transient_errors_are_not_retried():
    calls = []

    class ApiException(Exception):
        status = 401

    def unauthorized():
        calls.append(1)
        raise ApiException("unauthorized")

    with pytest.raises(InfluxDBQueryError, match="unauthorized"):
        with_retry(unauthorized, retries=3, backoff_s=0)
    assert len(calls) == 1


def test_retry_gives_up_with_query_error():
    calls = []

    def failing():
        calls.append(1)
        raise ConnectionError("boom")

    with pytest.raises(InfluxDBQueryError):
        with_retry(failing, retries=2, backoff_s=0)
    assert len(calls) == 3


def test_retry_recovers():
    attempts = iter([ConnectionError("x"), "ok"])

    def flaky():
        item = next(attempts)
        if isinstance(item, Exception):
            raise item
        return item

    assert with_retry(flaky, retries=2, backoff_s=0) == "ok"


def test_query_builders():
    start = datetime(2025, 1, 1, tzinfo=UTC)
    end = datetime(2025, 2, 1, tzinfo=UTC)
    q = build_series_range_query("b", "m", "f", start, end, {"z": "1", "a": "2"})
    assert q.index('r["a"]') < q.index('r["z"]')  # deterministic tag order
    assert 'keep(columns: ["_time", "_value"])' in q
    assert "createEmpty: true" in build_daily_count_query("b", "m", "f", start, end)
    assert 'r._measurement == "x"' in build_series_discovery_query("b", measurement="x")


def test_daily_counts_and_last_timestamp():
    api = FakeQueryApi(
        tables=[table({"_time": datetime(2025, 5, 1, tzinfo=UTC)})],
        csv_by_window={"aggregateWindow": b"_time,_value\r\n2025-01-01T00:00:00Z,1440\r\n"
                                          b"2025-01-02T00:00:00Z,0\r\n"},
    )
    client = make_client(api)
    counts = client.daily_counts("m", "f", datetime(2025, 1, 1), datetime(2025, 1, 3))
    assert list(counts["value"]) == [1440, 0]
    assert client.last_timestamp("m", "f") == datetime(2025, 5, 1, tzinfo=UTC)
    assert client.first_timestamp("m", "f") == datetime(2025, 5, 1, tzinfo=UTC)
    assert "first()" in api.queries[-1]


def test_v1_reports_unsupported():
    from influxdb_toolkit.v1.client import InfluxDBClientV1

    client = InfluxDBClientV1(host="h", port=8086, username="u", password="p", database="d",
                              client=SimpleNamespace())
    with pytest.raises(UnsupportedOperationError):
        client.discover_series()
    assert isinstance(pd.DataFrame(), pd.DataFrame)
