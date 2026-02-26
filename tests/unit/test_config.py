from __future__ import annotations

from influxdb_toolkit.config import (
    V1Config,
    V2Config,
    _get_bool,
    resolve_v1_config,
    resolve_v2_config,
    v1_from_env,
    v2_from_env,
)


def test_get_bool_variants() -> None:
    assert _get_bool("true") is True
    assert _get_bool("Yes") is True
    assert _get_bool("ON") is True
    assert _get_bool("0") is False
    assert _get_bool(None, default=True) is True


def test_v1_from_env_reads_v1_and_fallback_keys(monkeypatch) -> None:
    monkeypatch.setenv("INFLUXDB_HOST", "fallback-host")
    monkeypatch.setenv("INFLUXDB_PORT", "9000")
    monkeypatch.setenv("INFLUXDB_USER", "fallback-user")
    monkeypatch.setenv("INFLUXDB_PWD", "fallback-pwd")
    monkeypatch.setenv("INFLUXDB_DB", "fallback-db")
    monkeypatch.setenv("INFLUXDB_ALLOW_WRITE", "true")
    monkeypatch.delenv("INFLUXDB_V1_HOST", raising=False)
    monkeypatch.delenv("INFLUXDB_V1_PORT", raising=False)
    monkeypatch.delenv("INFLUXDB_V1_USER", raising=False)
    monkeypatch.delenv("INFLUXDB_V1_PASSWORD", raising=False)
    monkeypatch.delenv("INFLUXDB_V1_DATABASE", raising=False)

    cfg = v1_from_env()

    assert cfg.host == "fallback-host"
    assert cfg.port == 9000
    assert cfg.username == "fallback-user"
    assert cfg.password == "fallback-pwd"
    assert cfg.database == "fallback-db"
    assert cfg.allow_write is True


def test_v2_from_env_reads_values(monkeypatch) -> None:
    monkeypatch.setenv("INFLUXDB_V2_URL", "https://v2.local")
    monkeypatch.setenv("INFLUXDB_V2_TOKEN", "tok")
    monkeypatch.setenv("INFLUXDB_V2_ORG", "org")
    monkeypatch.setenv("INFLUXDB_V2_BUCKET", "bucket")
    monkeypatch.setenv("INFLUXDB_ALLOW_WRITE", "false")

    cfg = v2_from_env()

    assert cfg.url == "https://v2.local"
    assert cfg.token == "tok"
    assert cfg.org == "org"
    assert cfg.bucket == "bucket"
    assert cfg.allow_write is False


def test_resolve_v1_config_supports_alias_keys() -> None:
    cfg = resolve_v1_config(
        {
            "host": "h",
            "port": 8088,
            "user": "u",
            "pwd": "p",
            "database": "db",
            "ssl": True,
            "verify_ssl": False,
            "allow_write": True,
        }
    )

    assert cfg == V1Config(
        host="h",
        port=8088,
        username="u",
        password="p",
        database="db",
        ssl=True,
        verify_ssl=False,
        allow_write=True,
    )


def test_resolve_v2_config_dataclass_passthrough() -> None:
    original = V2Config(url="https://v2", token="t", org="o", bucket="b", allow_write=False)
    cfg = resolve_v2_config(original)
    assert cfg is original
