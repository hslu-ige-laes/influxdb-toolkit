"""Exceptions for influxdb_toolkit."""

class InfluxDBError(Exception):
    """Base exception for influxdb_toolkit."""


class InfluxDBConnectionError(InfluxDBError):
    """Connection to InfluxDB failed."""


class InfluxDBQueryError(InfluxDBError):
    """Query execution failed."""


class InfluxDBAuthenticationError(InfluxDBError):
    """Authentication failed."""


class UnsafeOperationError(InfluxDBError):
    """Raised when a write/delete/admin operation is blocked by safety rules."""


class UnsupportedOperationError(InfluxDBError):
    """Raised when an operation is not supported by the client/version."""