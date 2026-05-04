"""
Access link views.
"""

import json
import logging
import secrets as secrets_mod
from urllib.parse import urlencode

from django.conf import settings as django_settings
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from ..conf import get_customer_resolver, get_doorman_settings
from ..models import AccessLink
from ..services.access_link import AccessLinkService
from ..utils import normalize_phone, safe_redirect_url

logger = logging.getLogger("shopman.doorman.views.access_link")


@method_decorator(csrf_exempt, name="dispatch")
class AccessLinkCreateView(View):
    """
    Create an access link.

    POST /api/auth/access/create/  (application API)
    POST /auth/access/create/      (package-level include, when not shadowed)

    Request body:
    {
        "customer_id": "uuid",
        "subscriber_id": "manychat-id",
        "manychat_id": "manychat-id",
        "subscriber": {"id": "manychat-id", "first_name": "Ana", "whatsapp_id": "5543..."},
        "whatsapp_id": "5543...",
        "email": "ana@example.com",
        "audience": "web_checkout|web_account|web_support|web_general",
        "source": "manychat|api|internal",
        "ttl_minutes": 5,
        "next": "/pedido/ORD-001/",
        "metadata": {}
    }

    Response:
    {
        "access_url": "https://.../a/?t=...&next=...",
        "token": "...",
        "expires_at": "..."
    }
    """

    def post(self, request):
        # Authenticate via API key (H05)
        settings = get_doorman_settings()
        api_key = settings.ACCESS_LINK_API_KEY
        if not api_key and not django_settings.DEBUG:
            logger.error("AccessLinkCreateView: ACCESS_LINK_API_KEY is not configured — rejecting request.")
            return JsonResponse({"error": "Access link API not configured"}, status=503)
        if api_key:
            auth_header = request.META.get("HTTP_AUTHORIZATION", "")
            x_api_key = request.META.get("HTTP_X_API_KEY", "")
            provided_key = ""
            if auth_header.startswith("Bearer "):
                provided_key = auth_header[7:]
            elif x_api_key:
                provided_key = x_api_key

            if not provided_key or not secrets_mod.compare_digest(provided_key, api_key):
                return JsonResponse({"error": "Unauthorized"}, status=401)

        # Parse JSON
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        resolver = get_customer_resolver()
        customer, error_response = self._resolve_customer(data, resolver)
        if error_response:
            return error_response
        if not customer:
            return JsonResponse({"error": "Customer not found"}, status=404)

        if not customer.is_active:
            return JsonResponse({"error": "Customer inactive"}, status=400)

        # Create token
        result = AccessLinkService.create_token(
            customer=customer,
            audience=data.get("audience", AccessLink.Audience.WEB_GENERAL),
            source=data.get("source", AccessLink.Source.MANYCHAT),
            ttl_minutes=data.get("ttl_minutes"),
            metadata=data.get("metadata"),
        )
        if not result.success:
            return JsonResponse(
                {"error": result.error, "error_code": result.error_code},
                status=400,
            )

        next_url = self._next_url(data)
        access_url = self._build_access_url(
            request,
            result.token,
            next_url,
        )

        response_data = {
            "access_url": access_url,
            "token": result.token,
            "expires_at": result.expires_at,
        }

        return JsonResponse(response_data)

    @staticmethod
    def _next_url(data: dict) -> str | None:
        return data.get("next")

    @staticmethod
    def _build_access_url(request, token: str | None, next_url: str | None) -> str:
        params = {"t": token}
        if next_url:
            params["next"] = safe_redirect_url(next_url, request)
        return f"{request.build_absolute_uri('/a/')}?{urlencode(params)}"

    @classmethod
    def _resolve_customer(cls, data: dict, resolver):
        customer_id = data.get("customer_id")
        source = data.get("source", AccessLink.Source.MANYCHAT)
        manychat_id = data.get("manychat_id") or data.get("subscriber_id")

        if customer_id:
            payload, error_response = cls._access_identity_payload(data, manychat_id)
            if error_response:
                return None, error_response
            if payload:
                error_response = cls._manychat_whatsapp_id_guard(
                    source=source,
                    channel=cls._source_channel(data),
                    payload=payload,
                )
                if error_response:
                    return None, error_response
                if not hasattr(resolver, "upsert_access_link_customer"):
                    return None, JsonResponse({"error": "Access-link customer enrichment unsupported"}, status=400)
                try:
                    customer = resolver.upsert_access_link_customer(customer_id, payload)
                except ValueError as exc:
                    logger.warning("Access-link customer enrichment rejected: %s", exc)
                    return None, JsonResponse({"error": str(exc)}, status=409)
                return cls._guard_resolved_manychat_customer(data, source, customer)
            customer = resolver.get_by_uuid(customer_id)
            return cls._guard_resolved_manychat_customer(data, source, customer)

        subscriber = (
            data.get("subscriber")
            or data.get("manychat_subscriber")
            or cls._subscriber_from_top_level(data, manychat_id)
        )

        if source == AccessLink.Source.MANYCHAT and subscriber:
            if not isinstance(subscriber, dict):
                return None, JsonResponse({"error": "subscriber must be an object"}, status=400)
            subscriber = {**subscriber}
            if manychat_id and not subscriber.get("id"):
                subscriber["id"] = manychat_id
            if not subscriber.get("id"):
                return None, JsonResponse({"error": "subscriber.id required"}, status=400)
            if not hasattr(resolver, "upsert_manychat_subscriber"):
                return None, JsonResponse({"error": "ManyChat subscriber resolution unsupported"}, status=400)
            error_response = cls._manychat_whatsapp_id_guard(
                source=source,
                channel=cls._source_channel(data),
                payload=subscriber,
            )
            if error_response:
                return None, error_response
            try:
                customer = resolver.upsert_manychat_subscriber(subscriber)
            except ValueError as exc:
                logger.warning("ManyChat subscriber resolution rejected: %s", exc)
                return None, JsonResponse({"error": str(exc)}, status=409)
            return cls._guard_resolved_manychat_customer(data, source, customer)

        if source == AccessLink.Source.MANYCHAT and manychat_id:
            if not hasattr(resolver, "get_by_identifier"):
                return None, JsonResponse({"error": "ManyChat identifier resolution unsupported"}, status=400)
            customer = resolver.get_by_identifier("manychat", manychat_id)
            return cls._guard_resolved_manychat_customer(data, source, customer)

        email = data.get("email")
        if email:
            return resolver.get_by_email(email), None

        return None, JsonResponse(
            {"error": "customer_id, subscriber_id, manychat_id, whatsapp_id or email required"},
            status=400,
        )

    @staticmethod
    def _access_identity_payload(data: dict, manychat_id: str | None):
        subscriber = data.get("subscriber") or data.get("manychat_subscriber")
        if subscriber is not None and not isinstance(subscriber, dict):
            return None, JsonResponse({"error": "subscriber must be an object"}, status=400)

        payload = {**subscriber} if isinstance(subscriber, dict) else {}
        if manychat_id and not payload.get("id"):
            payload["id"] = manychat_id

        fields = (
            "whatsapp_id",
            "first_name",
            "last_name",
            "email",
            "ig_id",
            "ig_username",
            "fb_id",
            "tg_id",
            "custom_fields",
        )
        for field in fields:
            if data.get(field) is not None:
                payload[field] = data[field]

        return (payload or None), None

    @classmethod
    def _manychat_whatsapp_id_guard(
        cls,
        *,
        source: str,
        channel: str,
        payload: dict | None,
    ):
        if source != AccessLink.Source.MANYCHAT:
            return None
        if channel == "instagram":
            return None
        if cls._payload_whatsapp_id(payload or {}):
            return None
        return JsonResponse(
            {"error": "ManyChat WhatsApp access link requires a valid whatsapp_id."},
            status=422,
        )

    @classmethod
    def _guard_resolved_manychat_customer(cls, data: dict, source: str, customer):
        if (
            source == AccessLink.Source.MANYCHAT
            and cls._source_channel(data) != "instagram"
            and customer
            and not customer.phone
        ):
            return None, JsonResponse(
                {"error": "ManyChat customer has no persisted phone."},
                status=422,
            )
        return customer, None

    @staticmethod
    def _source_channel(data: dict) -> str:
        metadata = data.get("metadata") or {}
        if not isinstance(metadata, dict):
            return ""
        return str(metadata.get("channel") or "").strip().lower()

    @staticmethod
    def _payload_whatsapp_id(payload: dict) -> str:
        return normalize_phone(str(payload.get("whatsapp_id") or ""))

    @staticmethod
    def _subscriber_from_top_level(data: dict, manychat_id: str | None) -> dict | None:
        if not manychat_id:
            return None
        fields = (
            "whatsapp_id",
            "first_name",
            "last_name",
            "email",
            "ig_id",
            "ig_username",
            "fb_id",
            "tg_id",
            "custom_fields",
        )
        subscriber = {"id": manychat_id}
        for field in fields:
            if data.get(field) is not None:
                subscriber[field] = data[field]
        return subscriber


class AccessLinkExchangeView(View):
    """
    Exchange an access link for a session.

    GET /auth/access/?t=TOKEN

    On success: Redirects to LOGIN_REDIRECT_URL
    On failure: Renders access_link_invalid.html
    """

    def get_template_name(self):
        """Get template name from settings."""
        settings = get_doorman_settings()
        return settings.TEMPLATE_ACCESS_LINK_INVALID

    def get(self, request):
        settings = get_doorman_settings()
        token = request.GET.get("t")
        if not token:
            return render(
                request,
                self.get_template_name(),
                {"error": str(_("Token não informado."))},
            )

        result = AccessLinkService.exchange(
            token,
            request,
            preserve_session_keys=settings.PRESERVE_SESSION_KEYS,
        )

        if result.success:
            next_url = safe_redirect_url(request.GET.get("next"), request)
            return redirect(next_url)
        else:
            return render(
                request,
                self.get_template_name(),
                {"error": result.error},
            )
