from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class OffermanSocialConfig(AppConfig):
    """Bridge: adds the per-product social/commerce segment to Offerman's Product admin.

    Composes with any already-registered ``ProductAdmin`` (incl. Fiscalman's) by
    subclassing whatever is registered at ``ready()`` time — so the tabs stack.
    List this app AFTER ``fiscalman.contrib.offerman`` in ``INSTALLED_APPS`` so it
    runs last and inherits the fiscal tab.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "shopman.offerman.contrib.social"
    label = "offerman_social"
    verbose_name = _("Redes sociais — produtos")

    def ready(self):
        from django.contrib import admin
        from shopman.offerman.contrib.social.admin import build_social_product_admin
        from shopman.offerman.models import Product

        current = admin.site._registry.get(Product)
        if current is None:
            # Product admin not registered (admin_unfold contrib off) — nothing to extend.
            return
        social_admin_cls = build_social_product_admin(type(current))
        admin.site.unregister(Product)
        admin.site.register(Product, social_admin_cls)
