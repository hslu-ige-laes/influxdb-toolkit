# Data Structure Analysis

## Run Info
- generated_at_utc: `2026-02-10T07:07:05.445949+00:00`
- mode: read-only metadata queries
- source: `scripts/schema_report.py`

## Profile: `v1_flimatec`
- version: `1`
- database: `flimatec-langnau-am-albis_v2`
- endpoint: `https://influxdbv1.mdb.ige-hslu.io:8086`
- status: query failed: `HTTPSConnectionPool(host='influxdbv1.mdb.ige-hslu.io', port=8086): Max retries exceeded with url: /query?q=SHOW+MEASUREMENTS&db=flimatec-langnau-am-albis_v2 (Caused by ConnectTimeoutError(<HTTPSConnection(host='influxdbv1.mdb.ige-hslu.io', port=8086) at 0x175749a1bd0>, 'Connection to influxdbv1.mdb.ige-hslu.io timed out. (connect timeout=None)'))`

## Profile: `v1_mdb_connection_test`
- version: `1`
- database: `mdb-connection-test`
- endpoint: `http://10.180.26.130:8086`
- status: ok
- measurement count: `1`
- measurement sample: dev-7c604afffe003045

| Measurement | Tag keys (sample) | Field keys (sample) |
|---|---|---|
| `dev-7c604afffe003045` | sensor | value |

## Profile: `v1_meteo`
- version: `1`
- database: `meteoSwiss`
- endpoint: `https://influxdbv1.mdb.ige-hslu.io:8086`
- status: query failed: `HTTPSConnectionPool(host='influxdbv1.mdb.ige-hslu.io', port=8086): Max retries exceeded with url: /query?q=SHOW+MEASUREMENTS&db=meteoSwiss (Caused by ConnectTimeoutError(<HTTPSConnection(host='influxdbv1.mdb.ige-hslu.io', port=8086) at 0x175749a20d0>, 'Connection to influxdbv1.mdb.ige-hslu.io timed out. (connect timeout=None)'))`

## Profile: `v1_wattsup`
- version: `1`
- database: `wattsup`
- endpoint: `https://influxdbv1.mdb.ige-hslu.io:8086`
- status: query failed: `HTTPSConnectionPool(host='influxdbv1.mdb.ige-hslu.io', port=8086): Max retries exceeded with url: /query?q=SHOW+MEASUREMENTS&db=wattsup (Caused by ConnectTimeoutError(<HTTPSConnection(host='influxdbv1.mdb.ige-hslu.io', port=8086) at 0x175749a2e90>, 'Connection to influxdbv1.mdb.ige-hslu.io timed out. (connect timeout=None)'))`

## Profile: `v2_lcm_kwh_legionellen`
- version: `2`
- bucket: `lcm-kwh-legionellen`
- endpoint: `https://influxdbv2.mdb.ige-hslu.io`
- status: ok
- measurement count: `1`
- measurement sample: ttn_data

| Measurement | Tag keys (sample) | Field keys (sample) |
|---|---|---|
| `ttn_data` | _field, application_id, dev_eui, device_id, device_id_project, sensor | airtime_s_abs, altitude_masl_abs, battery_state_abs, battery_volt_abs, best_gateway_id, latitude_degr_abs, longitude_degr_abs, num_gateways, ... |

## Profile: `v2_meteo`
- version: `2`
- bucket: `meteoSwiss`
- endpoint: `https://influxdbv2.mdb.ige-hslu.io`
- status: ok
- measurement count: `160`
- measurement sample: ABO, AEG, AIG, ALT, AND, ANT, ARH, ARO, ATT, BAN, ...

| Measurement | Tag keys (sample) | Field keys (sample) |
|---|---|---|
| `ABO` | _field, sensor | value |
| `AEG` | _field, sensor | value |
| `AIG` | _field, sensor | value |
| `ALT` | _field, sensor | value |
| `AND` | _field, sensor | value |

