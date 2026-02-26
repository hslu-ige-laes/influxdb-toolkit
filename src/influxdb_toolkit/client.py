"""Factory and entry point for influxdb_toolkit clients."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from .config import resolve_v1_config, resolve_v2_config
from .v1.client import InfluxDBClientV1
from .v2.client import InfluxDBClientV2


class InfluxDBClientFactory:
    """Factory for selecting the correct client implementation."""

    @staticmethod
    def _detect_version(config: Mapping[str, Any]) -> int:
        """Infer InfluxDB version from config keys.

        v2 indicators: url/token/org
        v1 indicators: host/database/user credentials keys
        """
        v2_keys = ("url", "token", "org")
        v1_keys = ("host", "database", "username", "user", "password", "pwd")

        has_v2 = any(config.get(k) not in (None, "") for k in v2_keys)
        has_v1 = any(config.get(k) not in (None, "") for k in v1_keys)

        if has_v2 and has_v1:
            raise ValueError(
                "Ambiguous config: contains both v1 and v2 keys. "
                "Pass a clean config for one version, or set version explicitly."
            )
        if has_v2:
            return 2
        if has_v1:
            return 1
        raise ValueError(
            "Could not infer InfluxDB version from config. "
            "Provide v1 keys (host/database/username/password) or "
            "v2 keys (url/token/org), or pass version explicitly."
        )

    @staticmethod
    def get_client(
        version: Optional[int] = None,
        config: Optional[Mapping[str, Any]] = None,
    ):
        if config is None:
            raise ValueError("config is required")
        client_override = config.get("client") if isinstance(config, Mapping) else None

        if version is None:
            version = InfluxDBClientFactory._detect_version(config)

        if version == 1:
            cfg = resolve_v1_config(config)
            return InfluxDBClientV1(
                host=cfg.host,
                port=cfg.port,
                username=cfg.username,
                password=cfg.password,
                database=cfg.database,
                ssl=cfg.ssl,
                verify_ssl=cfg.verify_ssl,
                allow_write=cfg.allow_write,
                client=client_override,
            )
        if version == 2:
            cfg = resolve_v2_config(config)
            return InfluxDBClientV2(
                url=cfg.url,
                token=cfg.token,
                org=cfg.org,
                bucket=cfg.bucket,
                allow_write=cfg.allow_write,
                client=client_override,
            )

        raise ValueError(f"Unsupported InfluxDB version: {version}")
