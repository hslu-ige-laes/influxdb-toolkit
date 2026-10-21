# Changelog

## Unreleased
- Added series-level bulk access for v2: `discover_series()` (existing series incl. last
  timestamp via pushed-down `last()`), `iter_timeseries_chunks()` (time-windowed raw
  download with retry, pandas or polars output), `first_timestamp()`/`last_timestamp()` and `daily_counts()`
  (empty days reported as 0).
- Series queries match exactly: series with additional tag keys are excluded
  (`not exists`), and only transient errors (network, 5xx, 429) are retried.
- Added `SeriesInfo` with a readable, reversible series key.
- Added optional `polars` extra.
- Fixed: the v2 `get_series()` fallback no longer reports non-existing tag combinations
  (cartesian product); it now lists the series that actually exist.
- `get_fields_per_series()` logs failed per-measurement queries instead of hiding them.

## 0.1.0
- Initial scaffold with v1/v2 abstraction, safe-by-default writes, and docs.
- Added named connection profiles and profile-driven smoke testing.
- Added authentication/configuration comparison document.
- Added weekly task status document.
- Added schema report script for read-only Task 3 regeneration.
- Added batch-size support for `write_points` and `write_dataframe` in v1/v2 clients.
- Added guarded admin methods for user/database lifecycle preparation.
- Improved runtime version detection in factory (v1/v2 inferred from config keys, with ambiguity checks).
- Added `docs/usage_setup.md` with end-user setup and auto-detection usage examples.
