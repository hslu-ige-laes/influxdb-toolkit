# influxdb-toolkit

Unified Python API for InfluxDB v1 and v2 with extension points for v3.

Key goals:
- Consistent read/query/exploration API across v1 (InfluxQL) and v2 (Flux).
- Safe-by-default operations: write/delete/admin require explicit enablement.
- Clean boundaries for future v3 support.

## Install

```bash
pip install influxdb-toolkit
```

For local development:

```bash
pip install -e .
```

On Windows, prefer:

```powershell
py -m pip install -e .
```

## Quickstart

### Auto-detect version (recommended)

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
    )
    print(df.head())
```

### Explicit v1 example

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
        start=datetime.now(UTC) - timedelta(hours=1),
        end=datetime.now(UTC),
    )
```

The factory determines runtime version from input keys:
- v1 keys: `host`, `database`, `username/password` (or `user/pwd`)
- v2 keys: `url`, `token`, `org`

If both sets are present, the factory raises `Ambiguous config`.

## Configuration

Environment variables are supported (see `.env.example`). Explicit kwargs override env values.

## API Overview

Core client methods:
- Query: `get_timeseries`, `query_raw`, `get_multiple_timeseries`
- Exploration: `list_measurements`, `get_tags`, `get_tag_values`, `get_fields`, `list_databases` (v1), `list_buckets` (v2)
- Write/admin (guarded): `write_points`, `write_dataframe`, `delete_range`, `create_database`, `create_bucket`, `create_user`, `grant_privileges`

## Safety

Write/delete/admin operations are disabled by default. To enable, set:

```bash
INFLUXDB_ALLOW_WRITE=true
```

Or pass `allow_write=True` in config.

Write APIs accept optional `batch_size` for chunked writes:

```python
result = client.write_points(points, measurement="m", batch_size=5000)
```

## Use Cases

- Unified dashboards and scripts that need to run against both v1 and v2 backends.
- Schema exploration before migration or data quality checks.
- Read-only smoke checks for multiple named environments.

## Docs

- `docs/architecture_concept.md`
- `docs/usage_setup.md`
- `docs/influxdb_v1_vs_v2_overview.md`
- `docs/internal_package_inventory.md`
- `docs/data_structure_analysis.md`
- `docs/python_package_comparison.md`
- `docs/auth_config_comparison.md`
- `docs/week_status.md`

## Development

```bash
pip install -e .[dev]
pytest
```

## Run Locally

`influxdb-toolkit` is a Python library, not a web server.

### 1) Install + tests

```powershell
cd C:\path\to\influxdb\influxdb-toolkit
py -m pip install -e .[dev]
py -m pytest -q -o cache_dir="$env:USERPROFILE\.pytest_cache_influxdb_toolkit"
```

### 2) Read-only smoke test against configured InfluxDB

```powershell
py scripts/smoke_read.py --version 1
py scripts/smoke_read.py --version 2
```

### 3) Use named connection profiles

```powershell
py scripts/smoke_read.py --list-profiles
py scripts/smoke_read.py --profile v1_flimatec
py scripts/smoke_read.py --profile v2_meteo
```

### 4) Re-generate schema analysis

```powershell
py scripts/schema_report.py --list-profiles
py scripts/schema_report.py --profile v1_flimatec --profile v2_meteo
py scripts/schema_report.py
```

## PyPI Release and Cross-PC Verification

1. Build artifacts:

```powershell
py -m pip install -e .[release]
py -m build
$files = Get-ChildItem dist\\* | Select-Object -ExpandProperty FullName
py -m twine check $files
```

2. Publish to TestPyPI first:

```powershell
py -m twine upload --repository testpypi dist/*
```

3. Verify on a clean PC/venv:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -i https://test.pypi.org/simple/ influxdb-toolkit
```

4. Smoke check on the new machine:
- Copy `.env.example` to `.env` and set credentials.
- Run `py scripts/smoke_read.py --list-profiles` from repo checkout, or run your own short import script with `InfluxDBClientFactory`.

5. Publish to PyPI when TestPyPI validation passes.

## Contributing

See `CONTRIBUTING.md` for coding/testing conventions and release expectations.

## License

MIT License. See `LICENSE`.


