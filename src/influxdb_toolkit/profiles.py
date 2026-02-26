"""Named connection profiles for common InfluxDB targets.

Profiles contain host/database/bucket metadata and resolve credentials from
environment variables by default.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple
import os


CONNECTION_PROFILES: Dict[str, Dict[str, Any]] = {
    # InfluxDB v1 profiles
    "v1_flimatec": {
        "version": 1,
        "host": "influxdbv1.mdb.ige-hslu.io",
        "port": 8086,
        "database": "flimatec-langnau-am-albis_v2",
        "ssl": True,
        "verify_ssl": False,
    },
    "v1_meteo": {
        "version": 1,
        "host": "influxdbv1.mdb.ige-hslu.io",
        "port": 8086,
        "database": "meteoSwiss",
        "ssl": True,
        "verify_ssl": False,
    },
    "v1_wattsup": {
        "version": 1,
        "host": "influxdbv1.mdb.ige-hslu.io",
        "port": 8086,
        "database": "wattsup",
        "ssl": True,
        "verify_ssl": False,
    },
    "v1_mdb_connection_test": {
        "version": 1,
        "host": "10.180.26.130",
        "port": 8086,
        "database": "mdb-connection-test",
        "ssl": False,
        "verify_ssl": False,
    },
    # InfluxDB v2 profiles
    "v2_lcm_kwh_legionellen": {
        "version": 2,
        "url": "https://influxdbv2.mdb.ige-hslu.io",
        "bucket": "lcm-kwh-legionellen",
    },
    "v2_meteo": {
        "version": 2,
        "url": "https://influxdbv2.mdb.ige-hslu.io",
        "bucket": "meteoSwiss",
    },
}


def list_profile_names() -> list[str]:
    """Return all available profile names."""
    return sorted(CONNECTION_PROFILES.keys())


def resolve_profile(name: str) -> Tuple[int, Dict[str, Any]]:
    """Resolve a named profile into `(version, config)` with env credentials."""
    if name not in CONNECTION_PROFILES:
        available = ", ".join(list_profile_names())
        raise ValueError(f"Unknown profile '{name}'. Available: {available}")

    profile = dict(CONNECTION_PROFILES[name])
    version = int(profile.pop("version"))

    if version == 1:
        username = os.getenv("INFLUXDB_V1_USER", os.getenv("INFLUXDB_USER", ""))
        password = os.getenv("INFLUXDB_V1_PASSWORD", os.getenv("INFLUXDB_PWD", ""))
        profile["username"] = username if username else None
        profile["password"] = password if password else None
    elif version == 2:
        token = os.getenv("INFLUXDB_V2_TOKEN", os.getenv("INFLUXDB_TOKEN", ""))
        org = os.getenv("INFLUXDB_V2_ORG", os.getenv("INFLUXDB_ORG", ""))
        if not token or not org:
            raise ValueError(
                "Profile requires INFLUXDB_V2_TOKEN and INFLUXDB_V2_ORG "
                "(or INFLUXDB_TOKEN / INFLUXDB_ORG)."
            )
        profile["token"] = token
        profile["org"] = org
    else:
        raise ValueError(f"Unsupported profile version: {version}")

    profile["allow_write"] = False
    return version, profile

