"""Server-side geocoding endpoints.

Reverse geocoding is done here (not in the browser) so the Maps key is never
exposed to clients for that path. The client-side Places Autocomplete loader
keeps using the public key, which must be domain-restricted in Google Cloud.
"""

from __future__ import annotations

from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.services.geocoding import GeocodingError, reverse_geocode


@extend_schema_view(
    post=extend_schema(tags=["geocode"], summary="Reverse geocode (server-side)"),
)
@method_decorator(
    ratelimit(key="user_or_ip", rate="30/m", method="POST", block=False),
    name="dispatch",
)
class ReverseGeocodeView(APIView):
    """
    POST /api/geocode/reverse

    Body: {"lat": float, "lng": float}

    Returns canonical structured address (same shape the storefront stores
    in `delivery_address_structured`). Never exposes the Maps API key.
    """

    permission_classes = [AllowAny]
    authentication_classes = []  # public; rate-limited by IP/user.

    def post(self, request):
        if getattr(request, "limited", False):
            return Response(
                {"detail": "Muitas requisições. Aguarde um instante."},
                status=429,
            )

        data = request.data or {}
        try:
            lat = float(data.get("lat"))
            lng = float(data.get("lng"))
        except (TypeError, ValueError):
            return Response({"detail": "lat e lng numéricos são obrigatórios."}, status=400)

        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            return Response({"detail": "Coordenadas fora do intervalo."}, status=400)

        try:
            result = reverse_geocode(lat, lng)
        except GeocodingError as exc:
            return Response({"detail": str(exc)}, status=502)

        return Response(result.to_dict())
