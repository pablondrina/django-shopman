from __future__ import annotations

from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("customers", views.CustomerViewSet, basename="customer")

urlpatterns = [
    path("lookup/", views.LookupView.as_view(), name="customer-lookup"),
    path("insights/summary/", views.InsightsSummaryView.as_view(), name="insights-summary"),
] + router.urls
