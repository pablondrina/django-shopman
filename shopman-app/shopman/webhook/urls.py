from __future__ import annotations

from django.urls import path

from .views import ManychatWebhookView

app_name = "shopman_webhook"

urlpatterns = [
    path("manychat/", ManychatWebhookView.as_view(), name="manychat-webhook"),
]
