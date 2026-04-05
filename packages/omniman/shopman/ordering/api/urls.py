from __future__ import annotations

from django.http import JsonResponse
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ChannelViewSet, DirectiveViewSet, OrderViewSet, SessionViewSet
from .polling import order_stream_view


def health_check(request):
    """
    Healthcheck endpoint para monitoramento.

    Retorna status da aplicação para uso em:
    - Kubernetes liveness/readiness probes
    - Load balancer health checks
    - Monitoring systems

    Returns:
        200 OK com {"status": "healthy", "version": "X.X.X"}
    """
    from shopman.ordering import __version__

    return JsonResponse({
        "status": "healthy",
        "version": __version__,
    })


router = DefaultRouter(trailing_slash=False)
router.register("channels", ChannelViewSet, basename="channels")
router.register("sessions", SessionViewSet, basename="sessions")
router.register("orders", OrderViewSet, basename="orders")
router.register("directives", DirectiveViewSet, basename="directives")

urlpatterns = [
    path("health", health_check, name="health-check"),
    path("orders/stream", order_stream_view, name="orders-stream"),
    path("", include(router.urls)),
]
