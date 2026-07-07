"""Webhook URL routing — payment provider + courier callbacks."""

from django.urls import path

from shopman.shop.webhooks.efi import EfiPixWebhookView
from shopman.shop.webhooks.ifood import IFoodWebhookView
from shopman.shop.webhooks.ifood_events import IFoodEventsWebhookView
from shopman.shop.webhooks.machine import MachineWebhookView
from shopman.shop.webhooks.stripe import StripeWebhookView

app_name = "webhooks"

urlpatterns = [
    path("efi/pix/", EfiPixWebhookView.as_view(), name="efi-pix-webhook"),
    path("stripe/", StripeWebhookView.as_view(), name="stripe-webhook"),
    path("ifood/", IFoodWebhookView.as_view(), name="ifood-webhook"),
    # WP-5: optional signed push path for the direct integration (events).
    path("ifood/events/", IFoodEventsWebhookView.as_view(), name="ifood-events-webhook"),
    # Courier (Machine): status/posição das corridas de entrega.
    path("machine/", MachineWebhookView.as_view(), name="machine-webhook"),
]
