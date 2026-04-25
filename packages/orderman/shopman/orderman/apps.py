from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class OrdermanConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "shopman.orderman"
    label = "orderman"
    verbose_name = _("Pedidos")

    def ready(self):
        from shopman.orderman import dispatch  # noqa: F401 — connect post_save signal
        self._register_ref_types()

    def _register_ref_types(self):
        try:
            from shopman.orderman.contrib.refs.types import DEFAULT_REF_TYPES
            from shopman.refs import register_ref_type
            for ref_type in DEFAULT_REF_TYPES:
                try:
                    register_ref_type(ref_type)
                except ValueError:
                    pass  # Already registered (e.g. on test hot-reload)
        except ImportError:
            pass  # shopman.refs not installed
