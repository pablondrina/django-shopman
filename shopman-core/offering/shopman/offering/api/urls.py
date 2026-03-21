from __future__ import annotations

from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("products", views.ProductViewSet, basename="product")
router.register("collections", views.CollectionViewSet, basename="collection")
router.register("listings", views.ListingViewSet, basename="listing")

urlpatterns = router.urls
