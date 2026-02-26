"""Generate read-only schema analysis markdown from configured InfluxDB profiles.

Usage:
    py scripts/schema_report.py --list-profiles
    py scripts/schema_report.py --profile v2_meteo
    py scripts/schema_report.py --output docs/data_structure_analysis.md
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
import os
import sys
from typing import Iterable
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from influxdb_toolkit import InfluxDBClientFactory  # noqa: E402
from influxdb_toolkit.profiles import list_profile_names, resolve_profile  # noqa: E402


def _suppress_v2_pivot_warnings() -> None:
    try:
        import warnings
        from influxdb_client.client.warnings import MissingPivotFunction

        warnings.simplefilter("ignore", MissingPivotFunction)
    except Exception:
        pass


def _as_csv(items: Iterable[str], limit: int = 10) -> str:
    values = [str(x) for x in items if x]
    if not values:
        return "-"
    if len(values) <= limit:
        return ", ".join(values)
    return ", ".join(values[:limit]) + ", ..."


def _analyze_profile(name: str, max_measurements: int) -> list[str]:
    lines: list[str] = [f"## Profile: `{name}`"]
    try:
        version, config = resolve_profile(name)
    except Exception as exc:
        lines.append(f"- status: error resolving profile: `{exc}`")
        lines.append("")
        return lines

    lines.append(f"- version: `{version}`")
    if version == 1:
        lines.append(f"- database: `{config.get('database')}`")
        lines.append(f"- endpoint: `{'https' if config.get('ssl') else 'http'}://{config.get('host')}:{config.get('port')}`")
    else:
        lines.append(f"- bucket: `{config.get('bucket')}`")
        lines.append(f"- endpoint: `{config.get('url')}`")

    _append_no_proxy_hosts(config)

    client = InfluxDBClientFactory.get_client(version=version, config=config)
    try:
        measurements = client.list_measurements()
    except Exception as exc:
        lines.append(f"- status: query failed: `{exc}`")
        lines.append("")
        return lines
    finally:
        try:
            client.close()
        except Exception:
            pass

    lines.append(f"- status: ok")
    lines.append(f"- measurement count: `{len(measurements)}`")
    lines.append(f"- measurement sample: {_as_csv(measurements, limit=10)}")
    lines.append("")
    lines.append("| Measurement | Tag keys (sample) | Field keys (sample) |")
    lines.append("|---|---|---|")

    for measurement in measurements[:max_measurements]:
        client = InfluxDBClientFactory.get_client(version=version, config=config)
        try:
            tags = client.get_tags(measurement)
            fields = client.get_fields(measurement)
            tag_text = _as_csv(tags, limit=8)
            field_text = _as_csv(list(fields.keys()), limit=8)
            lines.append(f"| `{measurement}` | {tag_text} | {field_text} |")
        except Exception as exc:
            lines.append(f"| `{measurement}` | error | `{exc}` |")
        finally:
            try:
                client.close()
            except Exception:
                pass

    lines.append("")
    return lines


def _append_no_proxy_hosts(config: dict[str, object]) -> None:
    hosts: list[str] = []
    host = config.get("host")
    if isinstance(host, str) and host:
        hosts.append(host)

    url = config.get("url")
    if isinstance(url, str) and url:
        parsed = urlparse(url)
        if parsed.hostname:
            hosts.append(parsed.hostname)

    if not hosts:
        return

    current = os.getenv("NO_PROXY") or os.getenv("no_proxy") or ""
    values = [part.strip() for part in current.split(",") if part.strip()]
    changed = False
    for item in hosts:
        if item not in values:
            values.append(item)
            changed = True
    if changed:
        merged = ",".join(values)
        os.environ["NO_PROXY"] = merged
        os.environ["no_proxy"] = merged


def _build_report(profile_names: list[str], max_measurements: int) -> str:
    now = datetime.now(UTC).isoformat()
    lines = [
        "# Data Structure Analysis",
        "",
        "## Run Info",
        f"- generated_at_utc: `{now}`",
        "- mode: read-only metadata queries",
        "- source: `scripts/schema_report.py`",
        "",
    ]
    for name in profile_names:
        lines.extend(_analyze_profile(name, max_measurements=max_measurements))
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate read-only InfluxDB schema analysis markdown.")
    parser.add_argument("--profile", action="append", default=[], help="Profile name (can be repeated)")
    parser.add_argument("--max-measurements", type=int, default=5, help="How many measurements to sample per profile")
    parser.add_argument("--output", default="docs/data_structure_analysis.md", help="Output markdown path")
    parser.add_argument("--list-profiles", action="store_true", help="List available profiles and exit")
    args = parser.parse_args()

    if args.list_profiles:
        for name in list_profile_names():
            print(name)
        return 0

    _suppress_v2_pivot_warnings()
    selected = args.profile if args.profile else list_profile_names()
    content = _build_report(selected, max_measurements=args.max_measurements)

    output_path = (PROJECT_ROOT / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    print(f"wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
