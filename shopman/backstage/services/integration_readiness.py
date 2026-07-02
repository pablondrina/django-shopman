"""Provider readiness facts for operational backstage surfaces."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from django.conf import settings

logger = logging.getLogger(__name__)

ReadinessMode = Literal["runtime", "staging"]

_PRODUCTION_NAMES = {"producao", "produção", "production", "prod", "live"}


@dataclass(frozen=True)
class ProviderReadiness:
    provider: str
    label: str
    kind: str
    environment: str
    status: str
    message: str
    missing: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    def as_projection(self) -> dict:
        data = {
            "provider": self.provider,
            "label": self.label,
            "kind": self.kind,
            "environment": self.environment,
            "status": self.status,
            "message": self.message,
        }
        if self.missing:
            data["missing"] = list(self.missing)
        return data


def build_provider_readiness(*, mode: ReadinessMode = "runtime") -> tuple[ProviderReadiness, ...]:
    """Return non-secret provider readiness facts for POS/payment/fiscal surfaces."""
    return (
        focus_nfe_readiness(mode=mode),
        efi_pix_readiness(mode=mode),
        stripe_card_readiness(mode=mode),
    )


def focus_nfe_readiness(*, mode: ReadinessMode = "runtime") -> ProviderReadiness:
    config = dict(getattr(settings, "SHOPMAN_FOCUS_NFE", {}) or {})
    adapter_path = getattr(settings, "SHOPMAN_FISCAL_ADAPTER", None)
    environment = _normalized_environment(config.get("environment") or "homologacao")
    base_url = str(config.get("base_url") or "").strip().lower()
    missing: list[str] = []
    unsafe: list[str] = []

    if not _path_contains(adapter_path, "shopman.shop.adapters.fiscal_focusnfe.FocusNFeBackend"):
        missing.append("SHOPMAN_FISCAL_ADAPTER")
    if not str(config.get("token") or "").strip():
        missing.append("FOCUS_NFE_TOKEN")
    if not _focus_cnpj_emitente(config):
        missing.append("FOCUS_NFE_CNPJ_EMITENTE_or_Shop.document")

    if _requires_staging_safety(mode):
        if _is_production_name(environment):
            unsafe.append("FOCUS_NFE_ENVIRONMENT_homologacao")
        if base_url and "homologacao.focusnfe.com.br" not in base_url:
            unsafe.append("FOCUS_NFE_BASE_URL_homologacao")
    elif _requires_production_safety(mode) and not _is_production_name(environment):
        unsafe.append("FOCUS_NFE_ENVIRONMENT_producao")

    # Gate de catálogo: vendável sem NCM = primeira venda fiscal dele falha.
    # Só cobra quando a configuração base existe (senão o ruído esconde o resto).
    if not missing:
        ncm_gap = _sellable_products_without_ncm()
        if ncm_gap:
            missing.append(f"NCM_faltando_em_{ncm_gap}_produtos")

    issues = tuple(missing + unsafe)
    status = _status(missing=missing, unsafe=unsafe)
    return ProviderReadiness(
        provider="focus_nfe",
        label="Focus NFe / NFC-e",
        kind="fiscal_nfce",
        environment=environment,
        status=status,
        message=_readiness_message(
            status=status,
            environment=environment,
            ready="NFC-e configurada para emissão.",
            missing=issues,
        ),
        missing=issues,
    )


def _sellable_products_without_ncm() -> int:
    """Quantos produtos vendáveis/publicados não têm NCM em metadata.fiscal."""
    try:
        from shopman.offerman.models import Product

        count = 0
        for product in Product.objects.filter(is_sellable=True, is_published=True).only("metadata"):
            fiscal = (product.metadata or {}).get("fiscal") or {}
            if not str(fiscal.get("ncm") or "").strip():
                count += 1
        return count
    except Exception:
        logger.debug("focus_nfe_readiness: ncm scan failed", exc_info=True)
        return 0


def efi_pix_readiness(*, mode: ReadinessMode = "runtime") -> ProviderReadiness:
    payment_adapters = getattr(settings, "SHOPMAN_PAYMENT_ADAPTERS", {}) or {}
    config = dict(getattr(settings, "SHOPMAN_EFI", {}) or {})
    webhook = dict(getattr(settings, "SHOPMAN_EFI_WEBHOOK", {}) or {})
    sandbox = bool(config.get("sandbox", True))
    environment = "homologacao" if sandbox else "producao"
    missing: list[str] = []
    unsafe: list[str] = []

    if not _payment_adapter_contains(payment_adapters, "pix", "shopman.shop.adapters.payment_efi"):
        missing.append("SHOPMAN_PIX_ADAPTER")
    for name, env_name in (
        ("client_id", "EFI_CLIENT_ID"),
        ("client_secret", "EFI_CLIENT_SECRET"),
        ("certificate_path", "EFI_CERTIFICATE_PATH"),
        ("pix_key", "EFI_PIX_KEY"),
    ):
        if not str(config.get(name) or "").strip():
            missing.append(env_name)
    certificate_path = str(config.get("certificate_path") or "").strip()
    if certificate_path and not Path(certificate_path).exists():
        missing.append("EFI_CERTIFICATE_PATH_exists")
    if not str(webhook.get("webhook_token") or "").strip():
        missing.append("EFI_WEBHOOK_TOKEN")

    if _requires_staging_safety(mode) and not sandbox:
        unsafe.append("EFI_SANDBOX_true")
    elif _requires_production_safety(mode) and sandbox:
        unsafe.append("EFI_SANDBOX_false")

    issues = tuple(missing + unsafe)
    status = _status(missing=missing, unsafe=unsafe)
    return ProviderReadiness(
        provider="efi_pix",
        label="Efí PIX",
        kind="payment_pix",
        environment=environment,
        status=status,
        message=_readiness_message(
            status=status,
            environment=environment,
            ready="PIX Efí configurado para cobranças e webhooks.",
            missing=issues,
        ),
        missing=issues,
    )


def stripe_card_readiness(*, mode: ReadinessMode = "runtime") -> ProviderReadiness:
    payment_adapters = getattr(settings, "SHOPMAN_PAYMENT_ADAPTERS", {}) or {}
    config = dict(getattr(settings, "SHOPMAN_STRIPE", {}) or {})
    secret_key = str(config.get("secret_key") or "").strip()
    publishable_key = str(config.get("publishable_key") or "").strip()
    domain = str(config.get("domain") or "").strip()
    environment = _stripe_environment(secret_key)
    missing: list[str] = []
    unsafe: list[str] = []

    if not _payment_adapter_contains(payment_adapters, "card", "shopman.shop.adapters.payment_stripe"):
        missing.append("SHOPMAN_CARD_ADAPTER")
    if not secret_key:
        missing.append("STRIPE_SECRET_KEY")
    if not str(config.get("webhook_secret") or "").strip():
        missing.append("STRIPE_WEBHOOK_SECRET")
    if domain and not domain.startswith(("http://", "https://")):
        missing.append("SHOPMAN_DOMAIN_http")

    if _requires_staging_safety(mode):
        if secret_key and not secret_key.startswith("sk_test_"):
            unsafe.append("STRIPE_SECRET_KEY_test")
        if publishable_key and not publishable_key.startswith("pk_test_"):
            unsafe.append("STRIPE_PUBLISHABLE_KEY_test")
    elif _requires_production_safety(mode):
        if secret_key and not secret_key.startswith("sk_live_"):
            unsafe.append("STRIPE_SECRET_KEY_live")
        if publishable_key and not publishable_key.startswith("pk_live_"):
            unsafe.append("STRIPE_PUBLISHABLE_KEY_live")

    issues = tuple(missing + unsafe)
    status = _status(missing=missing, unsafe=unsafe)
    return ProviderReadiness(
        provider="stripe_card",
        label="Stripe cartões",
        kind="payment_card",
        environment=environment,
        status=status,
        message=_readiness_message(
            status=status,
            environment=environment,
            ready="Stripe Checkout configurado para cartões e webhooks.",
            missing=issues,
        ),
        missing=issues,
    )


def staging_missing(provider: str) -> list[str]:
    readiness = {
        "focus_nfe": focus_nfe_readiness,
        "efi_pix": efi_pix_readiness,
        "stripe_card": stripe_card_readiness,
    }[provider](mode="staging")
    return list(readiness.missing)


def _status(*, missing: list[str], unsafe: list[str]) -> str:
    if unsafe:
        return "error"
    if missing:
        return "warning"
    return "ready"


def _readiness_message(*, status: str, environment: str, ready: str, missing: tuple[str, ...]) -> str:
    if status == "ready":
        return f"{environment}: {ready}"
    prefix = "configuração insegura" if status == "error" else "falta configuração"
    return f"{environment}: {prefix}: {', '.join(missing)}"


def _requires_staging_safety(mode: ReadinessMode) -> bool:
    if mode == "staging":
        return True
    return not _requires_production_safety(mode)


def _requires_production_safety(mode: ReadinessMode) -> bool:
    if mode == "staging":
        return False
    return _is_production_name(getattr(settings, "SHOPMAN_ENVIRONMENT", "development"))


def _normalized_environment(value: object) -> str:
    return str(value or "").strip().lower() or "development"


def _is_production_name(value: object) -> bool:
    return _normalized_environment(value) in _PRODUCTION_NAMES


def _stripe_environment(secret_key: str) -> str:
    if secret_key.startswith("sk_live_"):
        return "producao"
    if secret_key.startswith("sk_test_"):
        return "test"
    return "test"


def _payment_adapter_contains(setting: object, method: str, expected: str) -> bool:
    if isinstance(setting, dict):
        return _path_contains(setting.get(method), expected)
    return _path_contains(setting, expected)


def _focus_cnpj_emitente(config: dict) -> str:
    configured = _digits(config.get("cnpj_emitente"))
    if configured:
        return configured
    return _digits(_shop_document())


def _shop_document() -> str:
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        return str(getattr(shop, "document", "") or "")
    except Exception:
        logger.debug("integration_readiness: Shop document lookup failed", exc_info=True)
        return ""


def _path_contains(value: object, expected: str) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, tuple, set)):
        return any(_path_contains(item, expected) for item in value)
    return expected in str(value)


def _digits(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())
