"""Small adapter helpers for dotted Python paths."""

from __future__ import annotations

from importlib import import_module
from typing import Any


def import_dotted_attr(path: str) -> Any:
    """Import dotted attributes, including nested class attributes."""
    parts = path.split(".")
    if len(parts) < 2:
        raise ImportError(f"{path!r} is not a dotted path")

    last_error: ImportError | None = None
    for index in range(len(parts) - 1, 0, -1):
        module_path = ".".join(parts[:index])
        attrs = parts[index:]
        try:
            obj: Any = import_module(module_path)
        except ImportError as exc:
            last_error = exc
            continue

        for attr in attrs:
            obj = getattr(obj, attr)
        return obj

    raise ImportError(f"Could not import {path!r}") from last_error
