"""
Craftsman API URLs (vNext).

Include this in your project's urlpatterns:

    path('api/craftsman/', include('shopman.crafting.api.urls')),
"""

from rest_framework.routers import DefaultRouter

from .views import QueryViewSet, RecipeViewSet, WorkOrderViewSet

router = DefaultRouter()
router.register("recipes", RecipeViewSet)
router.register("work-orders", WorkOrderViewSet)
router.register("queries", QueryViewSet, basename="queries")

urlpatterns = router.urls
