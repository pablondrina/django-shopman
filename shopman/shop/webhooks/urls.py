"""Webhook URL routing — payment provider callbacks."""

from django.urls import path

from shopman.shop.webhooks.efi import EfiPixWebhookView
from shopman.shop.webhooks.ifood import IFoodWebhookView
from shopman.shop.webhooks.stripe import StripeWebhookView

app_name = "webhooks"

urlpatterns = [
    path("efi/pix/", EfiPixWebhookView.as_view(), name="efi-pix-webhook"),
    path("stripe/", StripeWebhookView.as_view(), name="stripe-webhook"),
    path("ifood/", IFoodWebhookView.as_view(), name="ifood-webhook"),
]
