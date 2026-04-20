from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class OffermanConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "shopman.offerman"
    label = "offerman"
    verbose_name = _("Catálogo de Produtos")

    def ready(self):
        self._register_ref_types()

    def _register_ref_types(self):
        try:
            from shopman.refs import register_ref_type
            from shopman.refs.types import RefType
            sku = RefType(
                slug="SKU",
                label="SKU",
                allowed_targets=("offerman.Product",),
                unique_scope="all",
                normalizer="upper_strip",
            )
            try:
                register_ref_type(sku)
            except ValueError:
                pass
        except ImportError:
            pass
