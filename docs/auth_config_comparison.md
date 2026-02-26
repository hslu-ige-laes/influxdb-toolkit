# Authentication and Configuration Comparison

Date: 2026-02-09

## Goal
Choose a configuration approach for `influxdb-toolkit` that is secure, practical for local analytics work, and deployable in CI/production.

## Options Compared

| Approach | Pros | Cons | Fit for this project |
|---|---|---|---|
| `.env` file + `python-dotenv` | Easy local onboarding, works with IDE terminals, keeps secrets out of code when `.env` is gitignored | Plain-text secrets on disk, can be leaked if committed by mistake | Strong for local developer setup |
| `.ini` / `.yaml` config file | Supports named profiles and non-secret defaults, human-readable | Secret management is weak unless combined with env vars, extra parser/dependency choices | Useful for optional non-secret defaults |
| Direct environment variables | Best for CI/CD, containers, and secret stores; no secret files in repo | Less convenient manually; easy to forget values in a new shell | Best for production and automation |
| Python file with constants | Simple to implement | High leak risk, often committed accidentally, not environment-friendly | Not recommended for secrets |

## Recommendation

Use a hybrid standard:

1. Local development: `.env` file loaded by `python-dotenv`.
2. Production and CI: direct environment variables from secret stores.
3. Optional: keep only non-secret defaults in config files.
4. Never store secrets in Python constant files.

## How It Is Implemented Here

- `src/influxdb_toolkit/config.py` loads `.env` and reads env variables.
- `.env.example` documents required keys for v1 and v2.
- `scripts/smoke_read.py` supports env-based runs and named profiles.
- `src/influxdb_toolkit/profiles.py` keeps endpoint metadata while reading credentials from env variables.

This gives local convenience and production-safe behavior without changing code per environment.
