from django.urls import path

from .views import ManychatWebhookView

app_name = "customers_manychat"

urlpatterns = [
    path("webhook/", ManychatWebhookView.as_view(), name="manychat-webhook"),
]
