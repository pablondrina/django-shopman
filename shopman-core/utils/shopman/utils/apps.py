"""Django AppConfig for shopman.utils.

Adding 'shopman.utils' to INSTALLED_APPS enables Django's static file
finders to locate the bundled JavaScript (autocomplete_autofill.js, etc.).

No models or migrations — this is a utility-only app.
"""

from django.apps import AppConfig


class UtilsConfig(AppConfig):
    name = "shopman.utils"
    label = "utils"
    verbose_name = "Utilitários"
    default_auto_field = "django.db.models.BigAutoField"
