"""Django AppConfig for shopman.utils.

Adding ``shopman.utils`` to ``INSTALLED_APPS`` enables shared static assets
used by the suite's transversal admin tooling.

This package intentionally has no models or migrations. Its scope is:
- cross-suite primitives
- shared formatting / contact helpers
- shared admin and Unfold helpers
"""

from django.apps import AppConfig


class UtilsConfig(AppConfig):
    name = "shopman.utils"
    label = "utils"
    verbose_name = "Utilitários"
    default_auto_field = "django.db.models.BigAutoField"
