from __future__ import annotations

from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("positions", views.PositionViewSet, basename="position")

urlpatterns = [
    path("availability/", views.AvailabilityView.as_view(), name="availability"),
    path("availability/bulk/", views.BulkAvailabilityView.as_view(), name="availability-bulk"),
    path("promise/", views.PromiseView.as_view(), name="promise"),
    path("positions/<slug:ref>/quants/", views.PositionQuantsView.as_view(), name="position-quants"),
    path("alerts/below-minimum/", views.BelowMinimumAlertView.as_view(), name="alerts-below-minimum"),
    path("receive/", views.ReceiveView.as_view(), name="receive"),
    path("issue/", views.IssueView.as_view(), name="issue"),
    path("moves/", views.MoveListView.as_view(), name="moves"),
    path("holds/", views.HoldListView.as_view(), name="holds"),
] + router.urls
