"""Nelson Boulangerie — instance app."""

from django.apps import AppConfig


class NelsonConfig(AppConfig):
    name = "nelson"
    label = "nelson"
    verbose_name = "Nelson Boulangerie"
    default_auto_field = "django.db.models.BigAutoField"
