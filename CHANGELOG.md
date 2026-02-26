# Changelog

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
