from __future__ import annotations

from datetime import UTC

import pandas as pd
import pytest

from influxdb_toolkit.exceptions import UnsafeOperationError, UnsupportedOperationError
from influxdb_toolkit.v1.client import InfluxDBClientV1
from influxdb_toolkit.v2.client import (
    InfluxDBClientV2,
    _influxql_result_to_df,
    _is_influxql,
    _normalize_flux_dataframe,
)


def test_v1_admin_operations_disabled_even_when_writes_enabled() -> None:
    client = InfluxDBClientV1(
        host="localhost",
        port=8086,
        username=None,
        password=None,
        database="db",
        allow_write=True,
        client=object(),
    )
    with pytest.raises(UnsupportedOperationError, match="disabled until admin ops are approved"):
        client.create_database("x")
    with pytest.raises(UnsupportedOperationError, match="disabled until admin ops are approved"):
        client.create_user("u", "p")


def test_v2_admin_operations_disabled_even_when_writes_enabled() -> None:
    client = InfluxDBClientV2(
        url="http://localhost:8086",
        token="token",
        org="org",
        bucket="bucket",
        allow_write=True,
        client=object(),
    )
    with pytest.raises(UnsupportedOperationError, match="disabled until admin ops are approved"):
        client.create_bucket("x")
    with pytest.raises(UnsupportedOperationError, match="disabled until admin ops are approved"):
        client.delete_database("x")


def test_admin_operations_still_blocked_by_allow_write_guard() -> None:
    client = InfluxDBClientV1(
        host="localhost",
        port=8086,
        username=None,
        password=None,
        database="db",
        allow_write=False,
        client=object(),
    )
    with pytest.raises(UnsafeOperationError):
        client.delete_database("x")


def test_is_influxql_detection() -> None:
    assert _is_influxql("SELECT * FROM m") is True
    assert _is_influxql(" show measurements") is True
    assert _is_influxql('from(bucket: "b") |> range(start: -1h)') is False


def test_normalize_flux_dataframe_pivots_to_wide() -> None:
    t = pd.Timestamp("2026-02-01T00:00:00Z")
    df = pd.DataFrame(
        {
            "_time": [t, t],
            "_field": ["temperature", "humidity"],
            "_value": [22.4, 49.0],
        }
    )
    out = _normalize_flux_dataframe(df, timezone="UTC", pivot=True)

    assert "time" in out.columns
    assert "temperature" in out.columns
    assert "humidity" in out.columns
    assert len(out) == 1


def test_influxql_result_to_df_includes_tags() -> None:
    result = {
        "results": [
            {
                "series": [
                    {
                        "name": "m",
                        "columns": ["time", "value"],
                        "tags": {"sensor": "s1"},
                        "values": [["2026-02-01T00:00:00Z", 1.0]],
                    }
                ]
            }
        ]
    }
    out = _influxql_result_to_df(result, timezone="UTC")
    assert list(out["sensor"]) == ["s1"]
    assert out["time"].iloc[0].tzinfo == UTC
