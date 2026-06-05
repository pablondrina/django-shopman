"""Copy projection — OmotenashiCopy resolved as surface-agnostic data.

The orchestrator owns copy (``OmotenashiCopy`` rows + ``OMOTENASHI_DEFAULTS``
code defaults). This projection resolves a *namespace* of keys into a frozen
catalog that any surface's Presentation layer reads to place strings.

The data Projections carry only the semantic copy *key* (e.g. a promise's
``copy_key``); the Presentation asks this catalog for the resolved
title/message. Copy therefore stays authoritative and centralized in the
orchestrator — never invented by the surface, never hardcoded in it. The
canonical default lives in ``OMOTENASHI_DEFAULTS``; ``resolve_copy`` cascades
DB override → code default and never raises, so a surface that trusts the
catalog always gets the canonical string without re-declaring fallbacks.
"""

from __future__ import annotations

from dataclasses import dataclass

from shopman.shop.omotenashi.copy import all_keys, resolve_copy

WILDCARD = "*"


@dataclass(frozen=True)
class CopyText:
    """A resolved copy entry: title and/or message, already cascaded."""

    title: str = ""
    message: str = ""


@dataclass(frozen=True)
class CopyCatalog:
    """A frozen snapshot of one namespace's copy, resolved for a moment/audience.

    ``entries`` is built once at construction and never mutated; the catalog is
    a read seal like every other projection. The Presentation reads strings via
    :meth:`title`/:meth:`message`, keyed by the semantic copy key the data
    projection carries.
    """

    namespace: str
    moment: str
    audience: str
    entries: dict[str, CopyText]

    def get(self, key: str) -> CopyText:
        return self.entries.get(key, CopyText())

    def title(self, key: str, fallback: str = "") -> str:
        return self.get(key).title or fallback

    def message(self, key: str, fallback: str = "") -> str:
        return self.get(key).message or fallback


def build_copy(
    namespace: str,
    *,
    moment: str = WILDCARD,
    audience: str = WILDCARD,
) -> CopyCatalog:
    """Resolve every copy key under ``<NAMESPACE>_`` into a frozen catalog.

    Keys are discovered from the orchestrator's canonical copy registry
    (``OMOTENASHI_DEFAULTS``) and resolved through the DB→default cascade, so
    operator overrides take effect and code defaults always backstop.
    """
    prefix = f"{namespace.upper()}_"
    entries: dict[str, CopyText] = {}
    for key in all_keys():
        if not key.startswith(prefix):
            continue
        entry = resolve_copy(key, moment=moment, audience=audience)
        entries[key] = CopyText(title=entry.title, message=entry.message)
    return CopyCatalog(
        namespace=namespace,
        moment=moment,
        audience=audience,
        entries=entries,
    )


__all__ = ["CopyCatalog", "CopyText", "build_copy"]
