"""Webhook URL routing — payment provider callbacks."""

from django.urls import path

from shopman.webhooks.efi import EfiPixWebhookView
from shopman.webhooks.stripe import StripeWebhookView

app_name = "webhooks"

urlpatterns = [
    path("efi/pix/", EfiPixWebhookView.as_view(), name="efi-pix-webhook"),
    path("stripe/", StripeWebhookView.as_view(), name="stripe-webhook"),
]
