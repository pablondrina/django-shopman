"""JSON helpers for immutable storefront projections."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from decimal import Decimal
from enum import Enum
from typing import Any


def projection_data(value: Any) -> Any:
    """Convert projection dataclasses into JSON-safe primitives."""
    if is_dataclass(value):
        return {
            field.name: projection_data(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {
            str(key): projection_data(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple | list):
        return [projection_data(item) for item in value]
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [projection_data(item) for item in value]
    return value
