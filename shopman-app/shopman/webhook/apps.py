from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class WebhookConfig(AppConfig):
    name = "shopman.webhook"
    label = "shopman_webhook"
    verbose_name = _("Webhook Manychat")
