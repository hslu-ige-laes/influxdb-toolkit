# influxdb-toolkit

Python package for querying InfluxDB v1 (InfluxQL) and v2 (Flux) with one consistent API.

## Install

```bash
python -m pip install influxdb-toolkit
```

For local repo usage:

```bash
python -m pip install -e .
```

## 1-Minute Query (Auto-detect v1/v2)

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
    df = client.get_timeseries(
        measurement="temperature",
        fields=["value"],
        start=datetime.now(UTC) - timedelta(hours=24),
        end=datetime.now(UTC),
        interval="5m",
        aggregation="mean",
        timezone="UTC",
    )
    print(df.head())
```

## Copy/Paste Templates

### V1 only

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
        tags={"site": "A1"},
        interval="5m",
        aggregation="mean",
    )
    print(df.head())
```

### V2 only

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
        tags={"site": "A1"},
        interval="5m",
        aggregation="mean",
    )
    print(df.head())
```

### Auto-detect (single script for mixed environments)

```python
from datetime import UTC, datetime, timedelta
from influxdb_toolkit import InfluxDBClientFactory

# Use either v1 keys OR v2 keys.
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

## Common Query Tasks

### Query one metric

```python
df = client.get_timeseries(
    measurement="temperature",
    fields=["value"],
    start=start,
    end=end,
    tags={"site": "A1"},
    interval="5m",
    aggregation="mean",
)
```

### Query multiple metrics together

```python
df = client.get_multiple_timeseries(
    queries=[
        {"measurement": "temperature", "fields": ["value"], "tags": {"site": "A1"}},
        {"measurement": "pressure", "fields": ["value"], "tags": {"site": "A1"}},
    ],
    start=start,
    end=end,
    interval="10m",
    aggregation="mean",
)
```

### Run raw query text

V1 InfluxQL:

```python
df = client.query_raw(
    'SELECT mean("value") FROM "temperature" WHERE time >= now() - 24h GROUP BY time(5m)',
    timezone="UTC",
)
```

V2 Flux:

```python
flux = '''
from(bucket: "my-bucket")
  |> range(start: -24h)
  |> filter(fn: (r) => r._measurement == "temperature")
  |> filter(fn: (r) => r._field == "value")
  |> aggregateWindow(every: 5m, fn: mean)
'''
df = client.query_raw(flux, timezone="UTC")
```

### Explore schema before querying

```python
measurements = client.list_measurements()
tag_keys = client.get_tags("temperature")
tag_values = client.get_tag_values("temperature", "site")
fields = client.get_fields("temperature")
```

## Full Query API

- `get_timeseries`
- `get_multiple_timeseries`
- `query_raw`
- `get_results_from_qry` (alias to `query_raw`)
- `list_measurements`
- `get_tags`
- `get_tag_values`
- `get_fields`
- `list_databases` (v1)
- `list_buckets` (v2)

## Config Rules

Factory version detection:
- v1 keys: `host`, `database`, `username/password` (or `user/pwd`)
- v2 keys: `url`, `token`, `org`

Environment variables are supported via `.env.example`.

## Safety

Write/delete/admin operations are disabled by default.

Enable only if needed:

```bash
set INFLUXDB_ALLOW_WRITE=true
```

## Developer Docs

If you are maintaining/extending the package:
- `docs/usage_setup.md`
- `docs/architecture_concept.md`
- `CONTRIBUTING.md`
- `RELEASE.md`

## License

MIT. See `LICENSE`.