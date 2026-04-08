"""
Django AppConfig para contrib/refs.
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class RefsConfig(AppConfig):
    name = "shopman.omniman.contrib.refs"
    label = "refs"
    verbose_name = _("Referências")

    def ready(self):
        """Registra RefTypes padrão quando a app carrega."""
        from shopman.omniman.contrib.refs.registry import register_ref_type
        from shopman.omniman.contrib.refs.types import DEFAULT_REF_TYPES

        for ref_type in DEFAULT_REF_TYPES:
            try:
                register_ref_type(ref_type)
            except ValueError:
                # Já registrado (pode acontecer em reloads)
                pass
