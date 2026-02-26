from datetime import datetime

import pytest

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


def test_query_builders_escape_string_inputs() -> None:
    influxql = build_influxql_query(
        measurement='m"1',
        fields=['f"1'],
        start=datetime(2026, 2, 1),
        end=datetime(2026, 2, 2),
        tags={"k'1": "v'1"},
        timezone="Europe/Zurich",
    )
    assert 'FROM "m\\"1"' in influxql
    assert '"f\\"1"' in influxql
    assert '"k\'1" = \'v\\\'1\'' in influxql

    flux = build_flux_query(
        bucket='b"1',
        measurement='m"1',
        fields=['f"1'],
        start=datetime(2026, 2, 1),
        end=datetime(2026, 2, 2),
        tags={'k"1': 'v"1'},
    )
    assert 'from(bucket: "b\\"1")' in flux
    assert 'r._measurement == "m\\"1"' in flux
    assert 'r._field == "f\\"1"' in flux
    assert 'r["k\\"1"] == "v\\"1"' in flux


def test_query_builders_validate_aggregation_and_interval() -> None:
    with pytest.raises(ValueError, match="Invalid identifier"):
        build_influxql_query(
            measurement="m",
            fields=["f1"],
            start=datetime(2026, 2, 1),
            end=datetime(2026, 2, 2),
            aggregation="mean()",
            interval="5m",
        )

    with pytest.raises(ValueError, match="Invalid interval"):
        build_flux_query(
            bucket="b",
            measurement="m",
            fields=["f1"],
            start=datetime(2026, 2, 1),
            end=datetime(2026, 2, 2),
            aggregation="mean",
            interval="5m); drop()",
        )
