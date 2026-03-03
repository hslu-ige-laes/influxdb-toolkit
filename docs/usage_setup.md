# Usage Setup (Query First)

This guide is for users who want to query InfluxDB quickly with `influxdb-toolkit`.

## Install

```bash
python -m pip install influxdb-toolkit
```

Local development install:

```bash
python -m pip install -e .
```

## Copy/Paste Templates

### Template A: V1 only

```python
from datetime import UTC, datetime, timedelta
from influxdb_toolkit import InfluxDBClientFactory

config = {
    "host": "localhost",
    "port": 8086,
    "username": "user",
    "password": "pass",
    "database": "mydb",
    "ssl": False,
}

with InfluxDBClientFactory.get_client(version=1, config=config) as client:
    df = client.get_timeseries(
        measurement="temperature",
        fields=["value"],
        start=datetime.now(UTC) - timedelta(hours=24),
        end=datetime.now(UTC),
        interval="5m",
        aggregation="mean",
    )
    print(df.head())
```

### Template B: V2 only

```python
from datetime import UTC, datetime, timedelta
from influxdb_toolkit import InfluxDBClientFactory

config = {
    "url": "http://localhost:8086",
    "token": "my-token",
    "org": "my-org",
    "bucket": "my-bucket",
}

with InfluxDBClientFactory.get_client(version=2, config=config) as client:
    df = client.get_timeseries(
        measurement="temperature",
        fields=["value"],
        start=datetime.now(UTC) - timedelta(hours=24),
        end=datetime.now(UTC),
        interval="5m",
        aggregation="mean",
    )
    print(df.head())
```

### Template C: Auto-detect v1/v2

```python
from datetime import UTC, datetime, timedelta
from influxdb_toolkit import InfluxDBClientFactory

config = {
    "url": "http://localhost:8086",
    "token": "my-token",
    "org": "my-org",
    "bucket": "my-bucket",
}

with InfluxDBClientFactory.get_client(config=config) as client:
    df = client.get_multiple_timeseries(
        queries=[
            {"measurement": "temperature", "fields": ["value"], "tags": {"site": "A1"}},
            {"measurement": "pressure", "fields": ["value"], "tags": {"site": "A1"}},
        ],
        start=datetime.now(UTC) - timedelta(hours=24),
        end=datetime.now(UTC),
        interval="10m",
        aggregation="mean",
    )
    print(df.head())
```

## Choose your config

### InfluxDB v1 config

```python
v1_config = {
    "host": "localhost",
    "port": 8086,
    "username": "user",
    "password": "pass",
    "database": "mydb",
    "ssl": False,
}
```

### InfluxDB v2 config

```python
v2_config = {
    "url": "http://localhost:8086",
    "token": "my-token",
    "org": "my-org",
    "bucket": "my-bucket",
}
```

You can also call `InfluxDBClientFactory.get_client(config=...)` without `version`; version is auto-detected from keys.

## Query recipes

```python
from datetime import UTC, datetime, timedelta
from influxdb_toolkit import InfluxDBClientFactory

config = {
    "url": "http://localhost:8086",
    "token": "my-token",
    "org": "my-org",
    "bucket": "my-bucket",
}

with InfluxDBClientFactory.get_client(config=config) as client:
    start = datetime.now(UTC) - timedelta(hours=24)
    end = datetime.now(UTC)

    # 1) single timeseries
    df_1 = client.get_timeseries(
        measurement="temperature",
        fields=["value"],
        start=start,
        end=end,
        tags={"site": "A1"},
        interval="5m",
        aggregation="mean",
        timezone="UTC",
    )

    # 2) merged multi-query
    df_2 = client.get_multiple_timeseries(
        queries=[
            {"measurement": "temperature", "fields": ["value"], "tags": {"site": "A1"}},
            {"measurement": "pressure", "fields": ["value"], "tags": {"site": "A1"}},
        ],
        start=start,
        end=end,
        interval="10m",
        aggregation="mean",
    )

    # 3) raw query text (InfluxQL or Flux)
    df_3 = client.query_raw('SHOW MEASUREMENTS')

    # 4) schema discovery
    measurements = client.list_measurements()
    tags = client.get_tags("temperature")
    values = client.get_tag_values("temperature", "site")
    fields = client.get_fields("temperature")
```



## All Query Methods

### Quick reference

| Method | Purpose | Works on |
|---|---|---|
| `get_timeseries` | Query one measurement/field set over time | v1 + v2 |
| `get_multiple_timeseries` | Run multiple queries and merge on `time` | v1 + v2 |
| `query_raw` | Run raw query text (InfluxQL/Flux) | v1 + v2 |
| `get_results_from_qry` | Backward-compatible alias of `query_raw` | v1 + v2 |
| `list_measurements` | List available measurements | v1 + v2 |
| `get_tags` | List tag keys for a measurement | v1 + v2 |
| `get_tag_values` | List values for one tag key | v1 + v2 |
| `get_fields` | List fields (with types where available) | v1 + v2 |
| `list_databases` | List databases | v1 only |
| `list_buckets` | List buckets | v2 only |

### Minimal examples

```python
from datetime import UTC, datetime, timedelta
from influxdb_toolkit import InfluxDBClientFactory

config = {
    "url": "http://localhost:8086",
    "token": "my-token",
    "org": "my-org",
    "bucket": "my-bucket",
}

with InfluxDBClientFactory.get_client(config=config) as client:
    start = datetime.now(UTC) - timedelta(hours=24)
    end = datetime.now(UTC)

    # 1) get_timeseries
    df_ts = client.get_timeseries("temperature", ["value"], start, end)

    # 2) get_multiple_timeseries
    df_multi = client.get_multiple_timeseries(
        queries=[
            {"measurement": "temperature", "fields": ["value"], "start": start, "end": end},
            {"measurement": "pressure", "fields": ["value"], "start": start, "end": end},
        ]
    )

    # 3) query_raw
    df_raw = client.query_raw('SHOW MEASUREMENTS')

    # 4) get_results_from_qry
    df_alias = client.get_results_from_qry('SHOW MEASUREMENTS')

    # 5) list_measurements
    measurements = client.list_measurements()

    # 6) get_tags
    tag_keys = client.get_tags("temperature")

    # 7) get_tag_values
    tag_vals = client.get_tag_values("temperature", "site")

    # 8) get_fields
    fields = client.get_fields("temperature")

    # 9a) v1 only
    # databases = client.list_databases()

    # 9b) v2 only
    # buckets = client.list_buckets()
```

## Optional environment variables

Copy `.env.example` to `.env` and fill values.

## Troubleshooting

- If version detection fails, pass `version=1` or `version=2` explicitly.
- If a query fails on v2 with no bucket, include `bucket` in config.
- If timezone output is unexpected, set `timezone="UTC"` explicitly.