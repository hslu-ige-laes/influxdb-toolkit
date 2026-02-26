# Architecture Concept

## Goals
- Provide a consistent API for InfluxDB v1 (InfluxQL) and v2 (Flux).
- Keep write/delete/admin operations safe by default.
- Make v3 integration minimal by isolating version-specific logic.

## Architectural Decision

- Decision: class-based API (factory + abstract base + version strategies).
- Why not function-based: function-only wrappers duplicate connection state, auth handling, and query semantics across v1/v2.
- Benefit: shared lifecycle, shared safety gates, and consistent method contracts.

## Design

- Factory pattern in `influxdb_toolkit.client.InfluxDBClientFactory` selects v1/v2 based on config.
- Strategy pattern via `InfluxDBClientBase` and versioned implementations under `v1/` and `v2/`.
- Query builders (`v1/query_builder.py`, `v2/query_builder.py`) isolate language-specific query assembly.
- Shared error model in `exceptions.py`.

## Module Boundaries

- `base.py` defines the public API contract and shared helpers.
- `v1/client.py` uses `influxdb` (InfluxQL) and implements exploration and query methods.
- `v2/client.py` uses `influxdb-client` (Flux) and adds InfluxQL compatibility for v2 where available.
- `config.py` loads env and normalizes configuration into `V1Config` / `V2Config`.

## API Design

The unified API is derived from common behavior found in existing internal packages:

- Query:
  - `get_timeseries(...) -> pandas.DataFrame`
  - `get_multiple_timeseries(...) -> pandas.DataFrame`
  - `query_raw(...) -> pandas.DataFrame`
- Exploration:
  - `list_measurements(...)`
  - `get_tags(...)`
  - `get_tag_values(...)`
  - `get_fields(...)`
  - `list_databases()` (v1) / `list_buckets()` (v2)
- Write/Delete/Admin (guarded by `allow_write`):
  - `write_dataframe(...)`, `write_points(...)` with optional `batch_size`
  - `delete_range(...)`
  - `create_database(...)`, `delete_database(...)`
  - `create_bucket(...)`
  - `create_user(...)`, `delete_user(...)`, `grant_privileges(...)`

## Safety

- `allow_write` defaults to `False`.
- Write/delete/admin methods raise `UnsafeOperationError` unless explicitly enabled.
- This aligns with the current project safety rules for read-only DB usage.

## Extension to v3

- Add `v3/` with `client.py` and `query_builder.py`.
- Extend factory to recognize v3 config.
- Reuse base interface and shared models.

## Dependencies

- Runtime:
  - `influxdb` for v1 access
  - `influxdb-client` for v2 access
  - `pandas` for normalized DataFrame output
  - `python-dotenv` for local `.env` loading
  - `requests` for lightweight compatibility calls
- Development:
  - `pytest`, `pytest-cov`

## Versioning and Compatibility Strategy

- Package versioning: SemVer (`MAJOR.MINOR.PATCH`).
- Compatibility rules:
  - Keep unified method names stable across v1/v2 clients.
  - Add new optional parameters in a backward-compatible way when possible.
  - Keep backward aliases (`get_results_from_qry`, `fieldKey` in multi-query input).
- Planned v3 onboarding:
  - Add `version=3` in factory without breaking existing `version=1/2`.
  - Reuse data/result models and safety semantics.

## Testing

- Unit tests use mocks only.
- Integration tests are placeholders and should be wired to Docker when approved.
