"""Authentication mutation service for customer-facing entry points."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


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
        logger.debug("auth.trusted_device_prefill degraded; using fallback", exc_info=True)
        return "", ""


def client_ip(request) -> str:
    """IP real do cliente para os gates de rate-limit por IP do doorman.

    Atrás do load balancer, ``REMOTE_ADDR`` é o IP do proxy — todos os
    clientes compartilhariam um único bucket (falso bloqueio coletivo).
    Resolve via ``X-Forwarded-For`` com o mesmo ``TRUSTED_PROXY_DEPTH`` que os
    endpoints do doorman já usam.
    """
    import os

    from shopman.doorman.conf import get_doorman_settings
    from shopman.doorman.utils import get_client_ip

    depth = get_doorman_settings().TRUSTED_PROXY_DEPTH
    resolved = get_client_ip(request, depth)
    # Diagnóstico controlado (inerte por padrão): quando SHOPMAN_LOG_CLIENT_IP
    # está ligado, registra a cadeia X-Forwarded-For crua e o IP resolvido, para
    # descobrir a forma real do XFF atrás do proxy (ex.: DO App Platform) e ajustar
    # DOORMAN_TRUSTED_PROXY_DEPTH. Ligar só por uma janela curta em staging: é 1
    # linha de log por request e o XFF pode conter IP de cliente (dado pessoal).
    if os.environ.get("SHOPMAN_LOG_CLIENT_IP", "").lower() in ("true", "1", "yes"):
        logger.info(
            "client_ip.diagnostic xff=%r remote_addr=%r depth=%s resolved=%r",
            request.META.get("HTTP_X_FORWARDED_FOR"),
            request.META.get("REMOTE_ADDR"),
            depth,
            resolved,
        )
    return resolved


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
        count = auth_result.attempts_remaining
        suffix = "tentativa restante" if count == 1 else "tentativas restantes"
        error_msg += f" ({count} {suffix})"
    return error_msg


def confirmed_customer_name(auth_result) -> str:
    try:
        customer = customer_by_uuid(auth_result.customer.uuid)
        return customer.first_name if customer else ""
    except Exception:
        logger.debug("auth.confirmed_customer_name degraded; using fallback", exc_info=True)
        return ""


def preserved_session_values(session) -> dict:
    from shopman.doorman.conf import doorman_settings

    return {
        key: session[key]
        for key in doorman_settings.PRESERVE_SESSION_KEYS
        if key in session
    }


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
    # login() dá flush na sessão quando OUTRO usuário estava logado — a sacola
    # anônima tem que sobreviver à troca, como nos fluxos do Doorman.
    preserved = preserved_session_values(request.session) if hasattr(request, "session") else {}
    login(request, user, backend="shopman.doorman.backends.PhoneOTPBackend")
    for key, value in preserved.items():
        request.session[key] = value
    return customer


def trust_device(*, response, customer_id, request) -> None:
    from shopman.doorman.services.device_trust import DeviceTrustService

    DeviceTrustService.trust_device(
        response=response,
        customer_id=customer_id,
        request=request,
    )


def revoke_current_device(*, request, response) -> None:
    from shopman.doorman.services.device_trust import DeviceTrustService

    DeviceTrustService.revoke_device(request, response)
