"""Storefront authentication command service."""

from __future__ import annotations


def customer_by_uuid(customer_uuid):
    from shopman.guestman.services import customer as customer_service

    return customer_service.get_by_uuid(customer_uuid)


def customer_by_phone(phone: str):
    from shopman.guestman.services import customer as customer_service

    return customer_service.get_by_phone(phone)


def set_missing_first_name(*, phone: str, name: str) -> None:
    customer = customer_by_phone(phone)
    if customer and not customer.first_name:
        customer.first_name = name
        customer.save(update_fields=["first_name"])


def update_customer_name(customer_ref: str, *, first_name: str, last_name: str):
    from shopman.guestman.services import customer as customer_service

    return customer_service.update(customer_ref, first_name=first_name, last_name=last_name)


def trusted_device_prefill(request) -> tuple[str, str]:
    """Return (phone, first_name) from a trusted device cookie when valid."""
    try:
        from shopman.doorman import TrustedDevice
        from shopman.doorman.conf import doorman_settings

        raw_token = request.COOKIES.get(doorman_settings.DEVICE_TRUST_COOKIE_NAME)
        if not raw_token:
            return "", ""
        device = TrustedDevice.verify_token(raw_token)
        if not device:
            return "", ""
        customer = customer_by_uuid(device.customer_id)
        if not customer:
            return "", ""
        return customer.phone or "", customer.first_name or ""
    except Exception:
        return "", ""


def request_code(*, phone: str, delivery_method: str, ip_address: str | None):
    from shopman.doorman import get_auth_service

    AuthService = get_auth_service()
    return AuthService.request_code(
        target_value=phone,
        purpose="login",
        delivery_method=delivery_method,
        ip_address=ip_address,
    )


def request_code_error_message(auth_result) -> str:
    from shopman.doorman.error_codes import ErrorCode

    error_map = {
        ErrorCode.RATE_LIMIT: "Muitas tentativas. Aguarde alguns minutos e tente novamente.",
        ErrorCode.COOLDOWN: "Aguarde antes de solicitar um novo código.",
        ErrorCode.IP_RATE_LIMIT: "Muitas tentativas deste local. Tente mais tarde.",
    }
    return error_map.get(
        auth_result.error_code,
        "Não foi possível enviar o código. Verifique o número e tente novamente.",
    )


def request_code_partial_error_message(auth_result) -> str:
    translations = {
        "Too many attempts. Please wait a few minutes.": "Muitas tentativas. Aguarde alguns minutos.",
        "Please wait before requesting a new code.": "Aguarde antes de solicitar um novo código.",
        "Too many attempts from this location.": "Muitas tentativas deste local.",
        "Failed to send code.": "Falha ao enviar código.",
        "Error sending code.": "Erro ao enviar código.",
    }
    raw = auth_result.error or ""
    return translations.get(raw, raw) or "Erro ao enviar código."


def verify_for_login(*, phone: str, code_input: str, request):
    from shopman.doorman import get_auth_service

    AuthService = get_auth_service()
    return AuthService.verify_for_login(
        target_value=phone,
        code_input=code_input,
        request=request,
    )


def verify_error_message(auth_result) -> str:
    translations = {
        "Incorrect code.": "Código incorreto.",
        "Code expired. Please request a new one.": "Código expirado. Solicite um novo.",
        "Account not found. Please contact support.": "Conta não encontrada.",
    }
    raw_error = auth_result.error or ""
    error_msg = translations.get(raw_error, raw_error) or "Código inválido."
    if auth_result.attempts_remaining is not None and auth_result.attempts_remaining > 0:
        error_msg += f" ({auth_result.attempts_remaining} tentativa(s) restante(s))"
    return error_msg


def confirmed_customer_name(auth_result) -> str:
    try:
        customer = customer_by_uuid(auth_result.customer.uuid)
        return customer.first_name if customer else ""
    except Exception:
        return ""


def exchange_access_link(*, token: str, request):
    from shopman.doorman import get_access_link_service

    AccessLinkService = get_access_link_service()
    return AccessLinkService.exchange(
        token_str=token,
        request=request,
        preserve_session_keys=["cart"],
    )


def safe_redirect_url(next_url: str | None, request) -> str:
    from shopman.doorman.utils import safe_redirect_url as _safe_redirect_url

    return _safe_redirect_url(next_url, request)


def trusted_device_login(request, *, phone: str):
    """Authenticate request through trusted-device flow. Returns customer or None."""
    customer = customer_by_phone(phone)
    if not customer:
        return None

    from django.contrib.auth import login
    from shopman.doorman.protocols.customer import AuthCustomerInfo
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer
    from shopman.doorman.services.device_trust import DeviceTrustService

    if not DeviceTrustService.check_device_trust(request, customer.uuid):
        return None

    customer_info = AuthCustomerInfo(
        uuid=customer.uuid,
        name=customer.name,
        phone=customer.phone,
        email=getattr(customer, "email", None) or None,
        is_active=True,
    )
    user, _ = get_or_create_user_for_customer(customer_info)
    login(request, user, backend="shopman.doorman.backends.PhoneOTPBackend")
    return customer


def trust_device(*, response, customer_id, request) -> None:
    from shopman.doorman.services.device_trust import DeviceTrustService

    DeviceTrustService.trust_device(
        response=response,
        customer_id=customer_id,
        request=request,
    )
