# InfluxDB v1 vs v2 Overview

## Concepts

| Topic | v1 (InfluxQL) | v2 (Flux) |
|---|---|---|
| Data containers | Databases + retention policies | Buckets |
| Query language | InfluxQL (SQL-like) | Flux (functional pipeline) |
| Auth | Username/password | Token |
| API | Multiple endpoints | Unified REST API |

## Query Example

### v1 (InfluxQL)
```sql
SELECT mean("temperature")
FROM "sensors"
WHERE time >= '2026-02-01T00:00:00Z' AND time < '2026-02-02T00:00:00Z'
GROUP BY time(5m)
TZ('UTC')
```

### v2 (Flux)
```flux
from(bucket: "sensors")
  |> range(start: 2026-02-01T00:00:00Z, stop: 2026-02-02T00:00:00Z)
  |> filter(fn: (r) => r._measurement == "sensors")
  |> filter(fn: (r) => r._field == "temperature")
  |> aggregateWindow(every: 5m, fn: mean, createEmpty: false)
```

## Practical Differences

- v1 uses database + retention policy; v2 uses buckets with retention.
- v2 introduces Flux and a richer transformation pipeline.
- v2 query responses often include `_time`, `_field`, `_value`, requiring pivoting for wide tables.
- v1 InfluxQL queries are simpler for SQL-like users but less expressive for pipeline transforms.

## Wrapper Implications

- The wrapper normalizes results to a `time` column and one column per field.
- Tags/fields exploration uses `SHOW` queries in v1 and `schema.*` functions in v2.
- The API keeps time range, aggregation interval, and tags consistent across versions.