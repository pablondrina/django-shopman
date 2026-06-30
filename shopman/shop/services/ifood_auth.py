"""iFood OAuth — serviço de token (client_credentials) para as APIs Merchant/Order/Catalog.

Contrato verificado ao vivo (2026-06-30):
``POST {base}/authentication/v1.0/oauth/token``, body form-urlencoded
``grantType=client_credentials`` + ``clientId`` + ``clientSecret`` → ``{"accessToken", "expiresIn"}``
(~6h). ⚠️ O WAF do iFood bloqueia User-Agent genérico (ex.: python-requests/urllib) com 403 —
um User-Agent próprio é obrigatório. Token cacheado em processo até pouco antes de expirar.

Config em ``settings.SHOPMAN_IFOOD`` (env-driven). Inerte (retorna None) sem client_id/secret.
"""

from __future__ import annotations

import logging
import threading
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_TOKEN_PATH = "/authentication/v1.0/oauth/token"
USER_AGENT = "django-shopman/ifood-integration"
_EXPIRY_SKEW_SECONDS = 300  # renova 5 min antes do prazo informado pelo iFood

_lock = threading.Lock()
_cache: dict = {"token": None, "expires_at": 0.0}


def _cfg() -> dict:
    return getattr(settings, "SHOPMAN_IFOOD", {}) or {}


def _base_url() -> str:
    return str(_cfg().get("api_base") or "https://merchant-api.ifood.com.br").rstrip("/")


def get_access_token(*, force: bool = False) -> str | None:
    """Retorna um Bearer token válido (cacheado), ou None se inerte/erro."""
    cfg = _cfg()
    client_id = str(cfg.get("client_id") or "").strip()
    client_secret = str(cfg.get("client_secret") or "").strip()
    if not (client_id and client_secret):
        logger.warning("iFood OAuth não configurado (client_id/client_secret)")
        return None

    with _lock:
        now = time.monotonic()
        if not force and _cache["token"] and now < _cache["expires_at"]:
            return _cache["token"]

        try:
            resp = requests.post(
                f"{_base_url()}{_TOKEN_PATH}",
                data={
                    "grantType": "client_credentials",
                    "clientId": client_id,
                    "clientSecret": client_secret,
                },
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": USER_AGENT,
                },
                timeout=int(cfg.get("timeout") or 30),
            )
        except requests.RequestException as exc:
            logger.warning("iFood OAuth: request falhou: %s", exc)
            return None

        if resp.status_code != 200:
            logger.warning("iFood OAuth: HTTP %s: %s", resp.status_code, resp.text[:300])
            return None

        try:
            body = resp.json()
        except ValueError:
            logger.warning("iFood OAuth: resposta não-JSON")
            return None

        token = body.get("accessToken") or body.get("access_token")
        expires_in = int(body.get("expiresIn") or body.get("expires_in") or 0)
        if not token:
            logger.warning("iFood OAuth: resposta sem accessToken: %s", str(body)[:200])
            return None

        _cache["token"] = token
        _cache["expires_at"] = now + max(0, expires_in - _EXPIRY_SKEW_SECONDS)
        logger.info("iFood OAuth: token renovado (expira em %ss)", expires_in)
        return token


def authorized_headers(extra: dict | None = None) -> dict | None:
    """Headers (Bearer + User-Agent) prontos para as chamadas à API do iFood, ou None sem token."""
    token = get_access_token()
    if not token:
        return None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    if extra:
        headers.update(extra)
    return headers


def reset_cache() -> None:
    """Limpa o token cacheado (testes / refresh forçado)."""
    with _lock:
        _cache["token"] = None
        _cache["expires_at"] = 0.0


__all__ = ["get_access_token", "authorized_headers", "reset_cache", "USER_AGENT"]
