"""Reverse-OTP de verificação de número por WhatsApp (via ManyChat).

Modelo invertido: em vez de o servidor *enviar* um código (o que exigiria um
template de Authentication que o ManyChat não emite), é o **cliente** quem envia
uma mensagem contendo um token para o WhatsApp da loja. O WhatsApp entrega ao
ManyChat o número já verificado pela própria infraestrutura da Meta — prova de
posse mais forte que um OTP digitado, custo Meta zero (conversa iniciada pelo
usuário) e sem tocar em template.

Fluxo:
  1. Storefront chama ``start_verification`` → gera token, guarda no cache
     (Valkey/Redis) com TTL, devolve o deep link ``wa.me`` já preenchido.
  2. Cliente toca no link e envia a mensagem. Um Flow no ManyChat casa o token
     e chama ``confirm_verification`` (server-to-server) com {token, phone, name}.
  3. O navegador faz polling em ``verification_status``; quando verificado, a
     sessão do navegador é autenticada com o número que o WhatsApp comprovou.

Divisão de responsabilidade (maturidade):
  - **Handshake efêmero** (token, estado pending/verified) → cache Valkey, TTL.
    Sem migração e sem tocar nos modelos do Core.
  - **Fato durável** ("este número foi verificado via WhatsApp") → persistido em
    Guestman (ContactPoint is_verified), reusando os mesmos serviços que o
    doorman usa no login por código.

Segurança:
  - O ``status`` só autentica a **mesma sessão** que iniciou (bind por
    session_key) — evita fixação de sessão via token de terceiros.
  - O número que a Meta reporta é a fonte da verdade; divergência com o número
    digitado no cadastro é sinalizada (``phone_mismatch``), não silenciada.
  - ``confirm`` tem rate-limit por telefone (defesa em profundidade, além da
    API key server-to-server).
"""

from __future__ import annotations

import logging
import re
import secrets
import urllib.parse

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

# Alfabeto sem caracteres ambíguos (0/O, 1/I/L, 8/B) para o token ser fácil de
# ler/digitar no WhatsApp caso o deep link falhe.
_TOKEN_ALPHABET = "ACDEFGHJKMNPQRSTUVWXYZ2345679"
_CACHE_KEY = "wa_verify:tok:{}"
_CONFIRM_RATE_KEY = "wa_verify:confirmrate:{}"
_CONFIRM_RATE_MAX = 10          # confirmações por telefone
_CONFIRM_RATE_WINDOW = 3600     # por hora


def _config() -> dict:
    return getattr(settings, "SHOPMAN_WA_VERIFY", {}) or {}


def _ttl_seconds() -> int:
    try:
        return int(_config().get("ttl_seconds") or 600)
    except (TypeError, ValueError):
        return 600


def _token_prefix() -> str:
    return str(_config().get("token_prefix") or "V-")


def _new_token(length: int = 6) -> str:
    body = "".join(secrets.choice(_TOKEN_ALPHABET) for _ in range(length))
    return f"{_token_prefix()}{body}"


def _normalize_token(raw: str) -> str:
    """Normaliza o token recebido (do storefront ou do ManyChat).

    ManyChat pode mandar a mensagem inteira do cliente; extraímos o padrão
    ``PREFIXO+corpo`` e normalizamos caixa. Tolerante a espaços e minúsculas.
    """
    text = (raw or "").strip().upper()
    prefix = _token_prefix().upper()
    pattern = re.escape(prefix) + f"[{_TOKEN_ALPHABET}]+"
    match = re.search(pattern, text)
    return match.group(0) if match else text


def _wa_number() -> str:
    """Número (só dígitos, E.164 sem '+') do WhatsApp da loja para o deep link."""
    num = re.sub(r"\D", "", str(_config().get("number") or ""))
    if num:
        return num
    try:
        from shopman.shop.models import Shop

        shop = Shop.objects.first()
        if shop and getattr(shop, "phone", ""):
            return re.sub(r"\D", "", shop.phone)
    except Exception:
        logger.debug("wa_verify: fallback para Shop.phone degradado", exc_info=True)
    return ""


def _safe_next(raw: str) -> str:
    """Destino pós-login. Só caminhos internos (guard de open-redirect): começa com
    '/' e não '//' (protocol-relative). Caso contrário, vazio."""
    value = (raw or "").strip()
    if value.startswith("/") and not value.startswith("//"):
        return value
    return ""


def _return_url(token: str = "", next_path: str = "") -> str:
    """Link de volta para a loja, injetado na resposta do ``confirm`` para o
    ManyChat renderizar um botão.

    - **Com token** (sucesso): ``/entrar?wa=<token>`` — o ``/entrar`` retoma o
      handshake na mesma sessão mesmo se a aba foi reciclada (o ``status`` segue
      bind por sessão; o token não é segredo). Se o cliente iniciou com um destino
      (ex.: checkout), acrescenta ``&next=<destino>`` para cair lá já autenticado.
    - **Sem token** (falha: token expirado/inexistente): ``/entrar`` — recomeça o
      fluxo do zero (gera um código novo).

    Vazio se a base pública da loja (``SHOPMAN_STOREFRONT_BASE_URL``) não estiver
    configurada.
    """
    base = str(getattr(settings, "SHOPMAN_STOREFRONT_BASE_URL", "") or "").rstrip("/")
    if not base:
        return ""
    params = []
    if token:
        params.append(f"wa={urllib.parse.quote(token)}")
    safe_next = _safe_next(next_path)
    if safe_next:
        # Encoda o destino inteiro (safe='') para ser um valor opaco — a '/' e um
        # eventual query interno (?x=1) não colidem com a estrutura da URL externa.
        params.append(f"next={urllib.parse.quote(safe_next, safe='')}")
    query = f"?{'&'.join(params)}" if params else ""
    return f"{base}/entrar{query}"


def return_url(token: str = "", next_path: str = "") -> str:
    """Wrapper público (usado pelo view p/ o caso de payload malformado)."""
    return _return_url(token, next_path)


def _deep_link(token: str) -> str:
    number = _wa_number()
    text = f"Meu código de verificação é {token}"
    query = urllib.parse.quote(text)
    if number:
        return f"https://wa.me/{number}?text={query}"
    # Sem número configurado: devolve o esquema genérico (o cliente escolhe o chat).
    return f"https://wa.me/?text={query}"


def normalize_token(raw: str) -> str:
    """Normalizador público do token (usado pelo view/SSE)."""
    return _normalize_token(raw)


def peek(token: str) -> dict | None:
    """Estado atual do handshake (ou None). Usado pelo view SSE e pelo channel manager."""
    return cache.get(_CACHE_KEY.format(_normalize_token(token)))


def verify_channel(token: str) -> str:
    """Nome do canal SSE para um token."""
    return f"wa-verify-{_normalize_token(token)}"


def _emit_verified(normalized_token: str) -> None:
    """Publica o evento de verificação no canal SSE (push instantâneo).

    Espelha o padrão de shop/handlers/_sse_emitters.py: best-effort, inerte se o
    django_eventstream não estiver instalado. O payload não carrega PII — o login
    acontece no fetch canônico de /status.
    """
    try:
        from django_eventstream import send_event
    except Exception:
        return
    try:
        send_event(f"wa-verify-{normalized_token}", "verified", {"status": "verified"})
    except Exception:
        logger.debug("wa_verify: emit SSE falhou", exc_info=True)


def _normalize_phone(raw: str) -> str:
    from shopman.doorman.conf import get_adapter

    try:
        return get_adapter().normalize_login_target(raw) or ""
    except Exception:
        logger.debug("wa_verify: normalize_login_target degradado", exc_info=True)
        return ""


# ===========================================================================
# API pública
# ===========================================================================


def start_verification(*, phone: str = "", session_key: str | None = None, next_path: str = "") -> dict:
    """Inicia uma verificação. Retorna o token e o deep link do WhatsApp.

    ``next_path`` é o destino interno pós-login (ex.: ``/checkout``); volta no
    ``return_url`` do ``confirm`` para o cliente cair lá já autenticado.
    """
    intended = _normalize_phone(phone) if phone else ""
    token = _new_token()
    data = {
        "intended_phone": intended,
        "session_key": session_key or "",
        "status": "pending",
        "verified_phone": "",
        "wa_name": "",
        "consumed": False,
        "authenticated_uuid": "",
        "next": _safe_next(next_path),
        "created_at": timezone.now().isoformat(),
    }
    cache.set(_CACHE_KEY.format(token), data, timeout=_ttl_seconds())
    logger.info("wa_verify.start token_issued intended=%s bound=%s", bool(intended), bool(session_key))
    return {
        "token": token,
        "deep_link": _deep_link(token),
        "wa_number": _wa_number(),
        "expires_in": _ttl_seconds(),
    }


def confirm_verification(*, token: str, whatsapp_phone: str, name: str = "") -> dict:
    """Confirma o token (chamada server-to-server a partir do ManyChat).

    O ``whatsapp_phone`` é o número que a Meta reporta ao ManyChat — tratado como
    fonte da verdade. ``name`` é o nome do perfil do WhatsApp (opcional), trazido
    como sugestão para o cliente confirmar.
    """
    normalized_token = _normalize_token(token)
    key = _CACHE_KEY.format(normalized_token)
    data = cache.get(key)
    if not data:
        return {"ok": False, "reason": "not_found", "return_url": _return_url()}
    if data.get("status") == "verified":
        return {
            "ok": True,
            "reason": "already_verified",
            "return_url": _return_url(normalized_token, data.get("next", "")),
        }

    phone = _normalize_phone(whatsapp_phone)
    if not phone:
        return {"ok": False, "reason": "invalid_phone", "return_url": _return_url()}

    if not _confirm_rate_ok(phone):
        logger.warning("wa_verify.confirm rate_limited")
        return {"ok": False, "reason": "rate_limited", "return_url": _return_url()}

    intended = data.get("intended_phone") or ""
    data["status"] = "verified"
    data["verified_phone"] = phone
    data["wa_name"] = (name or "").strip()
    cache.set(key, data, timeout=_ttl_seconds())  # refresh TTL: dá janela ao polling
    _emit_verified(normalized_token)  # push SSE instantâneo (poll fica de fallback)
    matched = (not intended) or intended == phone
    logger.info("wa_verify.confirm verified matched=%s has_name=%s", matched, bool(data["wa_name"]))
    return {
        "ok": True,
        "reason": "verified",
        "matched": matched,
        "return_url": _return_url(normalized_token, data.get("next", "")),
    }


def verification_status(*, token: str, request) -> dict:
    """Consulta o status. Ao verificar pela 1ª vez, autentica a sessão (se for a
    mesma que iniciou) e persiste o número como verificado."""
    normalized_token = _normalize_token(token)
    key = _CACHE_KEY.format(normalized_token)
    data = cache.get(key)
    if not data:
        return {"status": "expired", "customer": None}
    if data.get("status") != "verified":
        return {"status": "pending", "customer": None}

    # Bind de sessão (anti-fixação), FAIL-CLOSED e antes de qualquer retorno
    # "verified": só a sessão que iniciou o fluxo vê o resultado / autentica.
    # Sessão ausente ou diferente da que chamou ``start`` → pending. Vale também
    # depois do token consumido (senão terceiros que soubessem o token leriam o
    # cliente). O ``start`` garante o session_key (salva a sessão), então um
    # ``stored_sk`` vazio só ocorre sem sessão — aí não há o que vincular.
    stored_sk = data.get("session_key") or ""
    current_sk = getattr(getattr(request, "session", None), "session_key", None) or ""
    if stored_sk and stored_sk != current_sk:
        logger.info("wa_verify.status session_bind_mismatch")
        return {"status": "pending", "customer": None}

    phone = data.get("verified_phone") or ""
    intended = data.get("intended_phone") or ""
    mismatch = bool(intended and intended != phone)

    # Já consumido (login feito em poll anterior desta sessão): reflete o cliente.
    if data.get("consumed"):
        from shopman.shop.services import auth as auth_service

        cust = None
        if data.get("authenticated_uuid"):
            cust = auth_service.customer_by_uuid(data["authenticated_uuid"])
        return {
            "status": "verified",
            "customer": cust,
            "phone": phone,
            "suggested_name": data.get("wa_name", ""),
            "created": False,
            "phone_mismatch": mismatch,
        }

    login_info = _login_phone(request, phone)
    if login_info is None:
        return {
            "status": "verified",
            "customer": None,
            "phone": phone,
            "suggested_name": data.get("wa_name", ""),
            "created": False,
            "phone_mismatch": mismatch,
        }

    data["consumed"] = True
    customer = login_info["customer"]
    data["authenticated_uuid"] = str(customer.uuid) if customer else ""
    cache.set(key, data, timeout=_ttl_seconds())
    return {
        "status": "verified",
        "customer": customer,
        "phone": phone,
        "suggested_name": data.get("wa_name", ""),
        "created": login_info["created"],
        "phone_mismatch": mismatch,
    }


# ===========================================================================
# Helpers internos
# ===========================================================================


def _confirm_rate_ok(phone: str) -> bool:
    """Rate-limit simples por telefone no confirm (defesa em profundidade)."""
    key = _CONFIRM_RATE_KEY.format(re.sub(r"\D", "", phone))
    try:
        count = cache.get(key, 0)
        if count >= _CONFIRM_RATE_MAX:
            return False
        cache.set(key, count + 1, timeout=_CONFIRM_RATE_WINDOW)
    except Exception:
        logger.debug("wa_verify: rate-limit degradado (cache indisponível)", exc_info=True)
    return True


def _login_phone(request, phone: str):
    """Resolve/cria o cliente pelo número verificado, autentica a sessão e
    persiste o número como verificado. Retorna dict {customer, created} ou None.

    Espelha o final de ``trusted_device_login`` (shop.services.auth), sem o
    gate de device-trust.
    """
    if not phone:
        return None

    from shopman.shop.services import auth as auth_service

    existing = auth_service.customer_by_phone(phone)

    from shopman.doorman.conf import get_adapter
    from shopman.doorman.protocols.customer import AuthCustomerInfo

    adapter = get_adapter()
    created = False
    if existing:
        info = AuthCustomerInfo(
            uuid=existing.uuid,
            name=existing.name,
            phone=existing.phone,
            email=getattr(existing, "email", None) or None,
            is_active=True,
        )
    else:
        if not adapter.should_auto_create_customer():
            logger.info("wa_verify: auto-create desativado; número sem conta")
            return None
        info = adapter.create_customer(phone)
        created = True

    from django.contrib.auth import login
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

    user, _ = get_or_create_user_for_customer(info)
    login(request, user, backend="shopman.doorman.backends.PhoneOTPBackend")

    _persist_verified_whatsapp(info.uuid, phone)

    return {"customer": auth_service.customer_by_uuid(info.uuid), "created": created}


def _persist_verified_whatsapp(customer_uuid, phone: str) -> None:
    """Grava o fato durável: número verificado via WhatsApp (Guestman).

    Espelha o ramo WHATSAPP de ``AuthService._link_verified_identifier`` do
    doorman. Best-effort: nunca derruba o login se o Guestman degradar.
    """
    try:
        from shopman.guestman.contrib.identifiers import IdentifierService, IdentifierType
        from shopman.guestman.models import ContactPoint
        from shopman.guestman.models import Customer as GuestCustomer
        from shopman.guestman.services import identity as identity_service

        guest_customer = GuestCustomer.objects.filter(uuid=customer_uuid, is_active=True).first()
        if not guest_customer:
            return
        identity_service.ensure_contact_point(
            guest_customer,
            type=ContactPoint.Type.WHATSAPP,
            value_normalized=phone,
            is_primary=True,
            is_verified=True,
        )
        IdentifierService.ensure_identifier(
            customer_ref=guest_customer.ref,
            identifier_type=IdentifierType.WHATSAPP,
            identifier_value=phone,
            is_primary=True,
            source_system="whatsapp_verify",
        )
    except Exception:
        logger.exception("wa_verify: falha ao persistir número verificado")
