from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class FiscalmanOffermanConfig(AppConfig):
    """Bridge: adds the per-product fiscal segment to Offerman's Product admin.

    One-directional (Fiscalman knows Offerman, not the reverse) so the cores stay
    independent. Re-registers ``Product`` with a subclass that exposes the fiscal
    classification (profile + NCM + CEST) as form fields instead of raw JSON.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "shopman.fiscalman.contrib.offerman"
    label = "fiscalman_offerman"
    verbose_name = _("Fiscal — produtos")

    def ready(self):
        # Runs after django.contrib.admin autodiscover (Offerman already
        # registered Product), so unregister + re-register is safe.
        from django.contrib import admin

        from shopman.offerman.models import Product

        from shopman.fiscalman.contrib.offerman.admin import FiscalProductAdmin

        try:
            admin.site.unregister(Product)
        except admin.sites.NotRegistered:
            pass
        admin.site.register(Product, FiscalProductAdmin)
