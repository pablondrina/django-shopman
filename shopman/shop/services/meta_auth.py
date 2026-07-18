"""Meta (Facebook/Instagram) Graph auth — System User token para o Commerce Catalog.

Diferente do iFood (OAuth ``client_credentials`` trocado em runtime), o Meta usa um
**System User access token** de longa duração emitido no Business Manager: o token
JÁ É a credencial, não há troca. Este módulo só monta os headers (Bearer) a partir
do ``settings.SHOPMAN_META`` e é **inerte** (retorna ``None``) sem token/catalog_id —
mesmo contrato do :mod:`shopman.shop.services.ifood_auth`.

⚠️ Token no header ``Authorization: Bearer``, nunca na query string (segredo não vai
em URL). Config via env (``META_ACCESS_TOKEN``/``META_CATALOG_ID``). Live só quando o
Pablo prover as credenciais do Business Manager; sem elas, o adapter roda em dry-run.
"""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

USER_AGENT = "django-shopman/meta-integration"


def _cfg() -> dict:
    return getattr(settings, "SHOPMAN_META", {}) or {}


def is_configured() -> bool:
    """True quando há token + catalog_id (o mínimo p/ falar com o Graph)."""
    cfg = _cfg()
    return bool(str(cfg.get("access_token") or "").strip() and str(cfg.get("catalog_id") or "").strip())


def authorized_headers(extra: dict | None = None) -> dict | None:
    """Headers (Bearer + User-Agent) p/ as chamadas ao Graph, ou None sem credencial."""
    cfg = _cfg()
    token = str(cfg.get("access_token") or "").strip()
    if not (token and str(cfg.get("catalog_id") or "").strip()):
        logger.warning("Meta não configurado (access_token/catalog_id)")
        return None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    if extra:
        headers.update(extra)
    return headers


__all__ = ["authorized_headers", "is_configured", "USER_AGENT"]
