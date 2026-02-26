# Internal Package Inventory

## Scope
Reviewed internal packages under `existierende Packages/`:
- `01_pyinfluxdb`
- `02_influxdbpy_github_reto`
- `05_monitoringDB_v1_v2`
- `06_Siemens_BX`
- `07_miniDataCloudClient`
- R wrappers in `03_influxdbr_wrapper` and `04_lcm_r_influxdb2`

## Commonalities
- Core read API revolves around `get_timeseries` and `get_multiple_timeseries`.
- Tags/fields/measurements are primary exploration primitives.
- Time aggregation + fill are common options.
- All code assumes pandas for dataframes (Python) and wide-format output.

## Differences
- Config/auth: hardcoded credentials vs `.env` vs `.ini` vs env vars.
- Query languages: InfluxQL (v1) vs Flux (v2).
- v2 data: different shaping logic, often needs pivoting.
- Safety: some packages include write/delete with no guard; others are read-only by practice.
- Timezone handling varies; some shift in query, others in pandas.

## Redundancies
- Multiple copies of nearly identical v1 query functions (pyinfluxdb, Siemens_BX, influxdbpy).
- Duplicate v1/v2 factory pattern implementations (`02_influxdbpy_github_reto`, `05_monitoringDB_v1_v2`).
- Duplicate tag/field helpers and parsing utilities.

## Recommended Unified API
- Standardize on `get_timeseries`, `get_multiple_timeseries`, and `query_raw`.
- Normalize outputs to `time` column + one column per field.
- Provide `list_measurements`, `get_tags`, `get_fields`, and version-specific `list_databases` / `list_buckets`.
- Enforce safe-by-default writes; explicit enablement required.
- Centralize config loading with env-first priority.

## Notes
- `07_miniDataCloudClient` shows robust config file handling and daily chunking for slow endpoints.
- `02_influxdbpy_github_reto` is the cleanest v1/v2 factory baseline.
- R code highlights additional metadata mapping (units, sensor types) but can be layered later.