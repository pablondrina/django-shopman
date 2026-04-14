"""
Fiscal backends — Pool pattern (Salesman-inspired).

Base class + lazy pool. Instance provides concrete backends
(e.g., Focus NFC-e, mock).

Usage:
    from shopman.shop.fiscal import fiscal_pool

    backend = fiscal_pool.get_backend()
    if backend:
        backend.emit(order_ref, items, payment, customer)

Settings:
    SHOPMAN_FISCAL_BACKENDS = [
        "myinstance.adapters.fiscal_focus.FocusNFCeBackend",
    ]
"""

from __future__ import annotations


class FiscalBackend:
    """
    Base fiscal backend. Subclass in instance code.

    Fiscal backends emit and cancel tax documents (NFC-e, NF-e, etc.).
    """

    identifier: str = ""
    label: str = ""

    def emit(self, *, order_ref, items, payment, customer):
        """
        Emit fiscal document.

        Returns dict with at least:
            success (bool)
            access_key (str): The fiscal document access key
        """
        raise NotImplementedError

    def cancel(self, *, order_ref, access_key, reason=""):
        """
        Cancel fiscal document.

        Returns dict with at least:
            success (bool)
        """
        raise NotImplementedError


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

            self._backends = [
                import_string(path)()
                for path in getattr(settings, "SHOPMAN_FISCAL_BACKENDS", [])
            ]
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
