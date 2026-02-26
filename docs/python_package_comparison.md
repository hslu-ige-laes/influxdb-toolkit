# Python Package Comparison (InfluxDB)

## Comparison Matrix

| Package | Creator / Official? | Actively Maintained? | Features | Limitations / Notes |
|---|---|---|---|---|
| `influxdb` (v1) | Community-maintained v1 client; InfluxData repo is archived | Not actively developed (repo archived) | InfluxDB 1.x client with InfluxQL queries and line protocol writes | v1-only; archived repo; not suitable for Flux or v2+ features |
| `influxdb-client` (v2) | InfluxData `influxdb-client-python` repository (v2 client) | Actively maintained | Flux queries with outputs to CSV/raw/Flux tables/Pandas; v1.8 compatibility | API not backward compatible with `influxdb` v1 client; v3 uses a different client |
| `influxdb3-python` (v3) | InfluxDB 3 client recommended by InfluxData docs | Actively maintained (recent releases) | Flight/pyarrow-based client; SQL and InfluxQL queries; write support; pandas optional | Targets InfluxDB 3; requires pyarrow; different API from v1/v2 |

## Notes

- `influxdb` is the legacy v1 client; it is archived and not in active development.
- `influxdb-client` is the official InfluxDB 2 client with Flux support and modern features.
- `influxdb3-python` is the emerging v3 client, focused on SQL/InfluxQL over Flight.

## Sources
- https://pypi.org/project/influxdb/
- https://github.com/influxdata/influxdb-python
- https://pypi.org/project/influxdb-client/
- https://github.com/influxdata/influxdb-client-python
- https://docs.influxdata.com/influxdb3/cloud-serverless/reference/client-libraries/v3/python/
- https://pypi.org/project/influxdb3-python/
