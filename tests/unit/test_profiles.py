from __future__ import annotations

import pytest

from influxdb_toolkit.profiles import list_profile_names, resolve_profile


def test_list_profile_names_is_sorted_and_non_empty() -> None:
    names = list_profile_names()
    assert names == sorted(names)
    assert "v1_flimatec" in names
    assert "v2_meteo" in names


def test_resolve_profile_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown profile"):
        resolve_profile("does_not_exist")


def test_resolve_profile_v1_reads_optional_env_credentials(monkeypatch) -> None:
    monkeypatch.setenv("INFLUXDB_V1_USER", "alice")
    monkeypatch.setenv("INFLUXDB_V1_PASSWORD", "secret")
    version, cfg = resolve_profile("v1_flimatec")

    assert version == 1
    assert cfg["database"] == "flimatec-langnau-am-albis_v2"
    assert cfg["username"] == "alice"
    assert cfg["password"] == "secret"
    assert cfg["allow_write"] is False


def test_resolve_profile_v2_requires_token_and_org(monkeypatch) -> None:
    monkeypatch.delenv("INFLUXDB_V2_TOKEN", raising=False)
    monkeypatch.delenv("INFLUXDB_TOKEN", raising=False)
    monkeypatch.delenv("INFLUXDB_V2_ORG", raising=False)
    monkeypatch.delenv("INFLUXDB_ORG", raising=False)

    with pytest.raises(ValueError, match="INFLUXDB_V2_TOKEN"):
        resolve_profile("v2_meteo")


def test_resolve_profile_v2_reads_env(monkeypatch) -> None:
    monkeypatch.setenv("INFLUXDB_V2_TOKEN", "tok")
    monkeypatch.setenv("INFLUXDB_V2_ORG", "org")
    version, cfg = resolve_profile("v2_lcm_kwh_legionellen")

    assert version == 2
    assert cfg["url"] == "https://influxdbv2.mdb.ige-hslu.io"
    assert cfg["bucket"] == "lcm-kwh-legionellen"
    assert cfg["token"] == "tok"
    assert cfg["org"] == "org"
    assert cfg["allow_write"] is False
