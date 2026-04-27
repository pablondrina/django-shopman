"""Auth and welcome intent extraction.

interpret_login()              — LoginView phone + name steps
interpret_request_code()       — RequestCodeView
interpret_verify_code()        — VerifyCodeView
interpret_device_check_login() — DeviceCheckLoginView
interpret_welcome()            — WelcomeView
"""
from __future__ import annotations

import re

from ._phone import normalize_phone_input
from .types import (
    AuthResult,
    DeviceCheckLoginIntent,
    LoginIntent,
    RequestCodeIntent,
    VerifyCodeIntent,
    WelcomeIntent,
)

# ── Name helpers (moved here from views/welcome.py) ───────────────────────────

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002600-\U000026FF"
    "\U00002700-\U000027BF"
    "\U0000FE0F"
    "]+",
    flags=re.UNICODE,
)
_WHITESPACE_RE = re.compile(r"\s+")
_SUSPECT_CHARS = ("&", "+", "|", "/")


def clean_display_name(raw: str) -> str:
    """Strip emojis and normalize whitespace. Does not split first/last."""
    if not raw:
        return ""
    cleaned = _EMOJI_RE.sub("", raw)
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def needs_confirmation(raw: str) -> bool:
    """True when the stored name is empty or looks auto-imported (ManyChat quirks)."""
    if not (raw or "").strip():
        return True
    if _EMOJI_RE.search(raw):
        return True
    if any(ch in raw for ch in _SUSPECT_CHARS):
        return True
    return False


# ── Intent extractors ─────────────────────────────────────────────────────────


def interpret_login(request) -> AuthResult[LoginIntent]:
    """Extract login intent from LoginView.post(), dispatching on step= "phone"|"name"."""
    step = request.POST.get("step", "phone")
    next_url = request.GET.get("next", request.POST.get("next", ""))

    if step == "name":
        return _interpret_login_name(request, next_url)
    return _interpret_login_phone(request, next_url)


def interpret_request_code(request) -> AuthResult[RequestCodeIntent]:
    """Extract RequestCodeIntent from RequestCodeView.post()."""
    phone_raw = request.POST.get("phone", "").strip()
    form_data = {"phone": phone_raw}

    if not phone_raw:
        return AuthResult(
            intent=None,
            errors={"phone": "Telefone não informado."},
            form_data=form_data,
        )

    phone = normalize_phone_input(phone_raw)
    if not phone:
        return AuthResult(
            intent=None,
            errors={"phone": "Telefone inválido."},
            form_data=form_data,
        )

    return AuthResult(
        intent=RequestCodeIntent(phone=phone),
        errors={},
        form_data=form_data,
    )


def interpret_verify_code(request) -> AuthResult[VerifyCodeIntent]:
    """Extract VerifyCodeIntent from VerifyCodeView.post()."""
    phone_raw = request.POST.get("phone", "").strip()
    code_input = request.POST.get("code", "").strip()
    code_digits = re.sub(r"\D", "", code_input)
    form_data = {"phone": phone_raw, "code": code_digits or code_input}

    if not phone_raw or not code_digits:
        return AuthResult(
            intent=None,
            errors={"code": "Código não informado."},
            form_data=form_data,
        )

    if len(code_digits) != 6:
        return AuthResult(
            intent=None,
            errors={"code": "Informe os 6 números do código."},
            form_data=form_data,
        )

    phone = normalize_phone_input(phone_raw)
    if not phone:
        return AuthResult(
            intent=None,
            errors={"phone": "Telefone inválido."},
            form_data=form_data,
        )

    return AuthResult(
        intent=VerifyCodeIntent(phone=phone, code=code_digits),
        errors={},
        form_data=form_data,
    )


def interpret_device_check_login(request) -> AuthResult[DeviceCheckLoginIntent]:
    """Extract DeviceCheckLoginIntent from DeviceCheckLoginView.post()."""
    phone_raw = request.POST.get("phone", "").strip()
    form_data = {"phone": phone_raw}

    if not phone_raw:
        return AuthResult(
            intent=None,
            errors={"phone": "Telefone não informado."},
            form_data=form_data,
        )

    phone = normalize_phone_input(phone_raw)
    if not phone:
        return AuthResult(
            intent=None,
            errors={"phone": "Telefone inválido."},
            form_data=form_data,
        )

    return AuthResult(
        intent=DeviceCheckLoginIntent(phone=phone),
        errors={},
        form_data=form_data,
    )


def interpret_welcome(request) -> AuthResult[WelcomeIntent]:
    """Extract WelcomeIntent from WelcomeView.post()."""
    next_url = request.GET.get("next") or request.POST.get("next") or "/"
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = "/"

    name_raw = request.POST.get("name", "")
    form_data = {"name": name_raw, "next": next_url}

    customer_info = getattr(request, "customer", None)
    if customer_info is None:
        return AuthResult(
            intent=None,
            errors={"auth": "Sessão expirada."},
            form_data=form_data,
        )

    name = clean_display_name(name_raw)
    form_data["name"] = name

    if not name:
        return AuthResult(
            intent=None,
            errors={"name": "Precisamos de um nome para te chamar."},
            form_data=form_data,
        )

    return AuthResult(
        intent=WelcomeIntent(
            name=name,
            next_url=next_url,
            customer_uuid=str(customer_info.uuid),
        ),
        errors={},
        form_data=form_data,
    )


# ── Private helpers ───────────────────────────────────────────────────────────


def _interpret_login_phone(request, next_url: str) -> AuthResult[LoginIntent]:
    phone_raw = request.POST.get("phone", "").strip()
    delivery_method = request.POST.get("delivery_method", "whatsapp")
    if delivery_method not in ("whatsapp", "sms"):
        delivery_method = "whatsapp"

    form_data = {"phone": phone_raw, "delivery_method": delivery_method, "next": next_url}

    if not phone_raw:
        return AuthResult(
            intent=None,
            errors={"phone": "Telefone é obrigatório."},
            form_data=form_data,
        )

    phone = normalize_phone_input(phone_raw)
    if not phone:
        return AuthResult(
            intent=None,
            errors={"phone": "Telefone inválido. Informe com DDD, ex: (43) 99999-9999"},
            form_data=form_data,
        )

    return AuthResult(
        intent=LoginIntent(
            step="phone",
            phone=phone,
            delivery_method=delivery_method,
            name=None,
            next_url=next_url,
        ),
        errors={},
        form_data=form_data,
    )


def _interpret_login_name(request, next_url: str) -> AuthResult[LoginIntent]:
    phone = request.session.get("login_phone", "")
    name = clean_display_name(request.POST.get("name", ""))
    form_data = {"name": name, "phone": phone, "next": next_url}

    if not name:
        return AuthResult(
            intent=None,
            errors={"name": "Como podemos te chamar?"},
            form_data=form_data,
        )

    return AuthResult(
        intent=LoginIntent(
            step="name",
            phone=None,
            delivery_method=None,
            name=name,
            next_url=next_url,
        ),
        errors={},
        form_data=form_data,
    )
