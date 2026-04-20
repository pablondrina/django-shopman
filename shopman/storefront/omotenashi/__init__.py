"""Omotenashi infrastructure — context (QUANDO + QUEM) and copy resolution.

See `docs/omotenashi.md` for the framework. This package is the single source
of truth for temporal/personal context and interface copy; templates consume
via the `omotenashi` context processor and the `{% omotenashi %}` template tag.
"""

from .context import OmotenashiContext
from .copy import OMOTENASHI_DEFAULTS, CopyEntry, resolve_copy

__all__ = ["OmotenashiContext", "OMOTENASHI_DEFAULTS", "CopyEntry", "resolve_copy"]
