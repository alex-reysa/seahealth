"""Shared datetime contract for schemas.

All schema datetimes are normalized to timezone-aware UTC values and serialize to
ISO-8601 strings with a trailing Z for JSON payloads.
"""
from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import AfterValidator, PlainSerializer


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _utc_z(value: datetime, _info: Any) -> str:
    return _as_utc(value).isoformat().replace("+00:00", "Z")


AwareDatetime = Annotated[
    datetime,
    AfterValidator(_as_utc),
    PlainSerializer(_utc_z, return_type=str, when_used="json"),
]
