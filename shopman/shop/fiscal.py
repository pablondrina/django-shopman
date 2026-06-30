"""
Fiscal backend pool (orchestrator-level).

Lazy registry of fiscal provider backends loaded from settings. The fiscal
*contract* (``FiscalBackend`` Protocol + result dataclasses) lives in the
Fiscalman persona (``shopman.fiscalman.contracts``); concrete provider adapters
(e.g. Focus NFe) live in ``shopman/shop/adapters/`` — same convention as the
payment adapters — and implement that Protocol structurally.

Usage:
    from shopman.shop.fiscal import fiscal_pool

    backend = fiscal_pool.get_backend()
    if backend:
        backend.emit(reference=..., items=..., payment=..., customer=...)

Settings:
    SHOPMAN_FISCAL_ADAPTER = "shopman.shop.adapters.fiscal_focusnfe.FocusNFeBackend"
"""

from __future__ import annotations


class FiscalPool:
    """
    Lazy pool of fiscal backends loaded from settings.

    Typically only one backend (or none). get_backend() returns
    the first, or None if pool is empty (smart no-op).
    """

    def __init__(self):
        self._backends = None

    def get_backends(self):
        if self._backends is None:
            from django.conf import settings
            from django.utils.module_loading import import_string

            adapter = getattr(settings, "SHOPMAN_FISCAL_ADAPTER", None)
            if adapter is None:
                paths = []
            elif isinstance(adapter, list):
                paths = adapter
            else:
                paths = [adapter]
            self._backends = [import_string(path)() for path in paths if path]
        return self._backends

    def get_backend(self, identifier=None):
        """
        Get a fiscal backend. If identifier is None, return the first.
        Returns None if pool is empty (no fiscal configured).
        """
        backends = self.get_backends()
        if identifier:
            for b in backends:
                if b.identifier == identifier:
                    return b
            return None
        return backends[0] if backends else None

    def reset(self):
        """Clear cached backends. Use in tests."""
        self._backends = None


fiscal_pool = FiscalPool()
