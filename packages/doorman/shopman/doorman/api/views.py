from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ..conf import get_doorman_settings
from ..error_codes import ErrorCode
from ..models import VerificationCode
from ..services.verification import AuthService
from ..utils import get_client_ip
from .serializers import (
    RequestCodeResponseSerializer,
    RequestCodeSerializer,
    VerifyCodeResponseSerializer,
    VerifyCodeSerializer,
)

_RATE_LIMIT_CODES = frozenset({ErrorCode.RATE_LIMIT, ErrorCode.COOLDOWN, ErrorCode.IP_RATE_LIMIT})


class RequestCodeView(APIView):
    """
    POST /api/auth/request-code/

    Request an OTP code for login.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RequestCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        target_raw = serializer.validated_data["target"]
        delivery_method = serializer.validated_data.get("delivery_method", "whatsapp")

        settings = get_doorman_settings()
        result = AuthService.request_code(
            target_value=target_raw,
            purpose=VerificationCode.Purpose.LOGIN,
            delivery_method=delivery_method,
            ip_address=get_client_ip(request, settings.TRUSTED_PROXY_DEPTH),
        )

        if not result.success:
            http_status = (
                status.HTTP_429_TOO_MANY_REQUESTS
                if result.error_code in _RATE_LIMIT_CODES
                else status.HTTP_400_BAD_REQUEST
            )
            return Response(
                {"detail": result.error, "error_code": result.error_code},
                status=http_status,
            )

        data = RequestCodeResponseSerializer(
            {
                "success": True,
                "code_id": result.code_id,
                "expires_at": result.expires_at,
            }
        ).data
        return Response(data, status=status.HTTP_200_OK)


class VerifyCodeView(APIView):
    """
    POST /api/auth/verify-code/

    Verify OTP code and return customer info.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        target_raw = serializer.validated_data["target"]
        code_input = serializer.validated_data["code"]
        result = AuthService.verify_for_login(target_raw, code_input, request)

        if not result.success:
            return Response(
                {
                    "detail": result.error,
                    "error_code": result.error_code,
                    "attempts_remaining": result.attempts_remaining,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = VerifyCodeResponseSerializer(
            {
                "success": True,
                "customer_id": result.customer.uuid,
                "created_customer": result.created_customer,
            }
        ).data
        return Response(data, status=status.HTTP_200_OK)
