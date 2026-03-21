from __future__ import annotations

from django.urls import path

from .webhooks import EfiPixWebhookView

app_name = "shopman_payment_webhook"

urlpatterns = [
    path("efi/pix/", EfiPixWebhookView.as_view(), name="efi-pix-webhook"),
]
