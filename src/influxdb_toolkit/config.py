"""Configuration loading for influxdb_toolkit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional
import os

from dotenv import load_dotenv


def load_env() -> None:
    """Load environment variables from a .env file if present."""
    load_dotenv()


def _get_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class V1Config:
    host: str
    port: int = 8086
    username: Optional[str] = None
    password: Optional[str] = None
    database: Optional[str] = None
    ssl: bool = False
    verify_ssl: bool = False
    allow_write: bool = False


@dataclass(frozen=True)
class V2Config:
    url: str
    token: str
    org: str
    bucket: Optional[str] = None
    allow_write: bool = False


def v1_from_env() -> V1Config:
    load_env()
    return V1Config(
        host=os.getenv("INFLUXDB_V1_HOST", os.getenv("INFLUXDB_HOST", "")),
        port=int(os.getenv("INFLUXDB_V1_PORT", os.getenv("INFLUXDB_PORT", "8086"))),
        username=os.getenv("INFLUXDB_V1_USER", os.getenv("INFLUXDB_USER")),
        password=os.getenv("INFLUXDB_V1_PASSWORD", os.getenv("INFLUXDB_PWD")),
        database=os.getenv("INFLUXDB_V1_DATABASE", os.getenv("INFLUXDB_DB")),
        ssl=_get_bool(os.getenv("INFLUXDB_V1_SSL"), False),
        verify_ssl=_get_bool(os.getenv("INFLUXDB_V1_VERIFY_SSL"), False),
        allow_write=_get_bool(os.getenv("INFLUXDB_ALLOW_WRITE"), False),
    )


def v2_from_env() -> V2Config:
    load_env()
    return V2Config(
        url=os.getenv("INFLUXDB_V2_URL", os.getenv("INFLUXDB_URL", "")),
        token=os.getenv("INFLUXDB_V2_TOKEN", os.getenv("INFLUXDB_TOKEN", "")),
        org=os.getenv("INFLUXDB_V2_ORG", os.getenv("INFLUXDB_ORG", "")),
        bucket=os.getenv("INFLUXDB_V2_BUCKET", os.getenv("INFLUXDB_BUCKET")),
        allow_write=_get_bool(os.getenv("INFLUXDB_ALLOW_WRITE"), False),
    )


def _dict_get(d: Mapping[str, Any], key: str, fallback: Any = None) -> Any:
    if key in d:
        return d[key]
    return fallback


def resolve_v1_config(config: V1Config | Mapping[str, Any]) -> V1Config:
    if isinstance(config, V1Config):
        return config
    return V1Config(
        host=_dict_get(config, "host"),
        port=int(_dict_get(config, "port", 8086)),
        username=_dict_get(config, "username", _dict_get(config, "user")),
        password=_dict_get(config, "password", _dict_get(config, "pwd")),
        database=_dict_get(config, "database"),
        ssl=bool(_dict_get(config, "ssl", False)),
        verify_ssl=bool(_dict_get(config, "verify_ssl", False)),
        allow_write=bool(_dict_get(config, "allow_write", False)),
    )


def resolve_v2_config(config: V2Config | Mapping[str, Any]) -> V2Config:
    if isinstance(config, V2Config):
        return config
    return V2Config(
        url=_dict_get(config, "url"),
        token=_dict_get(config, "token"),
        org=_dict_get(config, "org"),
        bucket=_dict_get(config, "bucket"),
        allow_write=bool(_dict_get(config, "allow_write", False)),
    )