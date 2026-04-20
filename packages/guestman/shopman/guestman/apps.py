from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class GuestmanConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "shopman.guestman"
    label = "guestman"
    verbose_name = _("Gestão de Clientes")

    def ready(self):
        self._register_ref_types()

    def _register_ref_types(self):
        try:
            from shopman.refs import register_ref_type
            from shopman.refs.types import RefType
            customer = RefType(
                slug="CUSTOMER",
                label="Cliente",
                allowed_targets=("guestman.Customer",),
                unique_scope="all",
                normalizer="upper_strip",
            )
            try:
                register_ref_type(customer)
            except ValueError:
                pass
        except ImportError:
            pass
