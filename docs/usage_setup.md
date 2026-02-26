# Usage and Setup

This guide explains how to set up and use `influxdb-toolkit` with automatic v1/v2 detection at runtime.

## 1. Install

```powershell
cd c:\Users\talippun\Documents\influxdb\influxdb-toolkit
py -m pip install -e .[dev]
```

## 2. Configure credentials

Copy `.env.example` to `.env` and fill values, or set environment variables directly.

v1 keys:
- `INFLUXDB_V1_HOST`
- `INFLUXDB_V1_PORT`
- `INFLUXDB_V1_USER`
- `INFLUXDB_V1_PASSWORD`
- `INFLUXDB_V1_DATABASE`
- `INFLUXDB_V1_SSL`

v2 keys:
- `INFLUXDB_V2_URL`
- `INFLUXDB_V2_TOKEN`
- `INFLUXDB_V2_ORG`
- `INFLUXDB_V2_BUCKET`

## 3. Runtime version detection

End users do not need to pass `version` if config clearly identifies v1 or v2:

```python
from influxdb_toolkit import InfluxDBClientFactory

config = {
    "url": "https://influxdbv2.mdb.ige-hslu.io",
    "token": "...",
    "org": "...",
    "bucket": "meteoSwiss",
}

client = InfluxDBClientFactory.get_client(config=config)
```

Detection rules:
- v2 when config contains `url/token/org`
- v1 when config contains `host/database` and optional user credentials
- error on ambiguous config (both v1 and v2 keys)
- error when no identifying keys are present

## 4. Query example (same API for v1 and v2)

```python
from datetime import UTC, datetime, timedelta
from influxdb_toolkit import InfluxDBClientFactory

config = {
    "host": "influxdbv1.mdb.ige-hslu.io",
    "port": 8086,
    "username": "tobias",
    "password": "...",
    "database": "meteoSwiss",
    "ssl": True,
}

with InfluxDBClientFactory.get_client(config=config) as client:
    df = client.get_timeseries(
        measurement="temperature",
        fields=["value"],
        start=datetime.now(UTC) - timedelta(hours=24),
        end=datetime.now(UTC),
        interval="1h",
        aggregation="mean",
    )
    print(df.head())
```

## 5. Local verification

Run unit tests:

```powershell
py -m pytest
```

Optional read-only smoke run:

```powershell
py scripts/smoke_read.py --version 1
py scripts/smoke_read.py --version 2
```
