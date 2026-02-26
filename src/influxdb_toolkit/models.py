"""Data models for influxdb_toolkit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import pandas as pd


@dataclass(frozen=True)
class TimeseriesResult:
    """Wrapper for a time series query result."""

    data: pd.DataFrame
    query: Optional[str] = None
    metadata: Optional[Dict[str, str]] = None


@dataclass(frozen=True)
class MeasurementSchema:
    """Schema information for a measurement."""

    measurement: str
    tags: List[str]
    fields: Dict[str, str]
    database: Optional[str] = None


@dataclass(frozen=True)
class WriteResult:
    """Result of a write operation."""

    success: bool
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None