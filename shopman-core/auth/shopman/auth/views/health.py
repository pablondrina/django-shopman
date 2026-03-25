"""
Health check view for load balancers and container orchestration.
"""

from django.db import connection
from django.http import JsonResponse
from django.views import View


class HealthCheckView(View):
    """
    GET /doorman/health/

    Returns {"status": "ok"} with a quick DB connectivity check.
    Useful for load balancers, Docker HEALTHCHECK, and Kubernetes probes.
    """

    def get(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({"status": "ok"})
