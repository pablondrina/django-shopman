"""Deployment app — hosts deployment-level tooling (e.g. the ``seed`` command).

This is the project/deployment wrapper, not a domain app: it has no models. It
exists in ``INSTALLED_APPS`` so Django discovers management commands that belong
to *this deployment* rather than to the shared product or a tenant package.
"""

from django.apps import AppConfig


class DeploymentConfig(AppConfig):
    name = "config"
    label = "config"
    verbose_name = "Deployment"
    default_auto_field = "django.db.models.BigAutoField"
