from django.urls import path

from channels.webhooks import EfiPixWebhookView, StripeWebhookView

app_name = "channels_webhooks"

urlpatterns = [
    path("efi/pix/", EfiPixWebhookView.as_view(), name="efi-pix-webhook"),
    path("stripe/", StripeWebhookView.as_view(), name="stripe-webhook"),
]
