from __future__ import annotations

from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("intents", views.PaymentIntentViewSet, basename="payment-intent")

urlpatterns = [
    path("active/", views.ActiveIntentView.as_view(), name="payment-active"),
] + router.urls
