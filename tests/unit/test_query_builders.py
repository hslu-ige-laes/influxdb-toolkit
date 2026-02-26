from datetime import datetime

from influxdb_toolkit.v1.query_builder import build_influxql_query
from influxdb_toolkit.v2.query_builder import build_flux_query


def test_influxql_query_builder():
    q = build_influxql_query(
        measurement="m",
        fields=["f1", "f2"],
        start=datetime(2026, 2, 1),
        end=datetime(2026, 2, 2),
        tags={"k": "v"},
        interval="5m",
        aggregation="mean",
        timezone="UTC",
    )
    assert "SELECT mean(\"f1\"), mean(\"f2\")" in q
    assert "FROM \"m\"" in q
    assert "GROUP BY time(5m)" in q


def test_flux_query_builder():
    q = build_flux_query(
        bucket="b",
        measurement="m",
        fields=["f1", "f2"],
        start=datetime(2026, 2, 1),
        end=datetime(2026, 2, 2),
        tags={"k": "v"},
        interval="5m",
        aggregation="mean",
    )
    assert 'from(bucket: "b")' in q
    assert 'r._measurement == "m"' in q
    assert 'r._field == "f1"' in q
    assert 'aggregateWindow' in q