"""
Django system checks for Shopman.

Registered in ShopmanConfig.ready() via checks.register().

Errors (block runserver/migrate --deploy in production):
  SHOPMAN_E001  SECRET_KEY is the development default
  SHOPMAN_E002  ALLOWED_HOSTS is empty or contains '*'
  SHOPMAN_E003  PIX or CARD payment adapter is missing or payment_mock without explicit staging allowance
  SHOPMAN_E004  A webhook integration has no token configured
  SHOPMAN_E005  Guestman (Manychat) webhook secret not configured
  SHOPMAN_E006  Shared Redis cache is not configured
  SHOPMAN_E007  Database backend is SQLite in production
  SHOPMAN_E008  Doorman access-link API key is not configured
  SHOPMAN_E009  Real payment adapter is missing required credentials/files
  SHOPMAN_E010  Debug OTP exposure enabled outside non-production
  SHOPMAN_E011  Machine courier adapter enabled without API credentials

Warnings (non-blocking, logged at startup):
  SHOPMAN_W001  Database backend is SQLite in local/debug mode
  SHOPMAN_W002  Notification backend is console while DEBUG=False
  SHOPMAN_W003  No fiscal adapter configured while a fiscal-enabled channel exists
  SHOPMAN_W004  Listing.ref has no matching Channel.ref
  SHOPMAN_W005  OFFERMAN pricing backend not configured
  SHOPMAN_W006  Mock payment adapter explicitly allowed outside DEBUG
  SHOPMAN_W007  Debug OTP exposure explicitly allowed in staging
  SHOPMAN_W010  Machine courier enabled without webhook token (status via polling only)
"""

from __future__ import annotations

import os

from django.conf import settings
from django.core.checks import Error, Warning, register

_DEV_SECRET_KEY = "dev-secret-key-not-for-production"


@register(deploy=True)
def check_secret_key(app_configs, **kwargs):
    errors = []
    if not settings.DEBUG:
        key = getattr(settings, "SECRET_KEY", "")
        if key == _DEV_SECRET_KEY or not key:
            errors.append(
                Error(
                    "SECRET_KEY está no valor default de desenvolvimento.",
                    hint="Defina DJANGO_SECRET_KEY com um valor aleatório seguro via variável de ambiente.",
                    id="SHOPMAN_E001",
                )
            )
    return errors


@register(deploy=True)
def check_allowed_hosts(app_configs, **kwargs):
    errors = []
    if not settings.DEBUG:
        hosts = getattr(settings, "ALLOWED_HOSTS", [])
        if not hosts or "*" in hosts:
            errors.append(
                Error(
                    "ALLOWED_HOSTS está vazio ou contém '*' em produção.",
                    hint="Defina DJANGO_ALLOWED_HOSTS com os domínios reais da aplicação.",
                    id="SHOPMAN_E002",
                )
            )
    return errors


@register(deploy=True)
def check_payment_adapters(app_configs, **kwargs):
    messages = []
    if settings.DEBUG:
        return messages

    adapters = getattr(settings, "SHOPMAN_PAYMENT_ADAPTERS", {}) or {}
    allow_mock = bool(getattr(settings, "SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS", False))
    for method in ("pix", "card"):
        path = adapters.get(method, "")
        if not path:
            messages.append(
                Error(
                    f"Adapter de pagamento para método '{method}' não está configurado fora de DEBUG.",
                    hint=f"Defina SHOPMAN_{method.upper()}_ADAPTER com um adapter real ou habilite mock explicitamente em staging técnico.",
                    id="SHOPMAN_E003",
                )
            )
            continue

        if "payment_mock" in path:
            if allow_mock:
                messages.append(
                    Warning(
                        f"Adapter de pagamento para método '{method}' está usando payment_mock fora de DEBUG.",
                        hint=(
                            "Isto só é aceitável em staging/teste operacional sem credenciais sandbox reais. "
                            "Antes de go-live, remova SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS e configure o gateway real."
                        ),
                        id="SHOPMAN_W006",
                    )
                )
            else:
                messages.append(
                    Error(
                        f"Adapter de pagamento para método '{method}' aponta para payment_mock fora de DEBUG.",
                        hint=(
                            f"Defina SHOPMAN_{method.upper()}_ADAPTER com um adapter real "
                            "ou habilite SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=true apenas em staging técnico."
                        ),
                        id="SHOPMAN_E003",
                    )
                )
            continue

        if "payment_efi" in path:
            messages.extend(_check_efi_payment_credentials(method=method))
        if "payment_stripe" in path:
            messages.extend(_check_stripe_payment_credentials(method=method))
    return messages


def _check_efi_payment_credentials(*, method: str):
    cfg = getattr(settings, "SHOPMAN_EFI", {}) or {}
    missing = []
    for key, label in (
        ("client_id", "EFI_CLIENT_ID"),
        ("client_secret", "EFI_CLIENT_SECRET"),
        ("certificate_path", "EFI_CERTIFICATE_PATH"),
        ("pix_key", "EFI_PIX_KEY"),
    ):
        if not cfg.get(key):
            missing.append(label)

    certificate_path = cfg.get("certificate_path")
    if certificate_path and not os.path.exists(certificate_path):
        missing.append("EFI_CERTIFICATE_PATH arquivo existente no container")

    if not missing:
        return []

    return [
        Error(
            f"Adapter EFI configurado para '{method}', mas credenciais/arquivos obrigatórios estão ausentes.",
            hint="Configure: " + ", ".join(missing) + ".",
            id="SHOPMAN_E009",
        )
    ]


def _check_stripe_payment_credentials(*, method: str):
    cfg = getattr(settings, "SHOPMAN_STRIPE", {}) or {}
    missing = []
    if not cfg.get("secret_key"):
        missing.append("STRIPE_SECRET_KEY")
    if not cfg.get("webhook_secret"):
        missing.append("STRIPE_WEBHOOK_SECRET")

    if not missing:
        return []

    return [
        Error(
            f"Adapter Stripe configurado para '{method}', mas credenciais obrigatórias estão ausentes.",
            hint="Configure: " + ", ".join(missing) + ".",
            id="SHOPMAN_E009",
        )
    ]


@register(deploy=True)
def check_webhook_tokens(app_configs, **kwargs):
    """Validate inbound-integration webhook tokens.

    Every endpoint already fails CLOSED without a token (rejects all requests —
    there is no bypass). The severity here reflects the CONSEQUENCE of a missing
    token, not a security risk:

    - EFI (``critical=True``) → **Error**: the PIX confirmation webhook is in
      active use; without the token real payments silently never confirm. Block
      the deploy.
    - iFood (``critical=False``) → **Warning**: fail-closed, mas NÃO é "opcional"
      se você recebe pedidos por webhook. ``/api/webhooks/ifood/`` ingere o pedido
      no canal iFood; sem o token, TODO callback do iFood toma 403 e nenhum pedido
      entra. É Warning (não Error) só porque um deployment que não usa iFood deve
      poder subir sem ele — mas se usa, este token é obrigatório.
    """
    messages = []
    if settings.DEBUG:
        return messages

    # (settings_attr, persona, env_var, critical)
    integrations = [
        ("SHOPMAN_EFI_WEBHOOK", "EFI", "EFI_WEBHOOK_TOKEN", True),
        ("SHOPMAN_IFOOD", "iFood", "IFOOD_WEBHOOK_TOKEN", False),
    ]
    for attr, name, env_var, critical in integrations:
        cfg = getattr(settings, attr, {}) or {}
        if cfg.get("webhook_token"):
            continue
        if critical:
            messages.append(
                Error(
                    f"{attr}['webhook_token'] não está configurado em produção.",
                    hint=(
                        f"{name} confirma pagamento real via webhook; sem o token "
                        f"a confirmação nunca chega e o pagamento trava. Defina "
                        f"{env_var} via variável de ambiente."
                    ),
                    id="SHOPMAN_E004",
                )
            )
        else:
            messages.append(
                Warning(
                    f"{attr}['webhook_token'] não configurado — o webhook {name} "
                    f"(/api/webhooks/ifood/) rejeita TODO callback com 403.",
                    hint=(
                        f"Se você recebe pedidos {name} por webhook, eles NÃO entram "
                        f"sem este token — o endpoint ingere o pedido no canal {name}, "
                        f"mas sem {env_var} (igual ao configurado no portal {name}) "
                        f"todo callback toma 403. Defina {env_var}. Deixe vazio só se "
                        f"não usa o webhook {name}."
                    ),
                    id="SHOPMAN_W008",
                )
            )
    return messages


@register()
def check_database_backend(app_configs, **kwargs):
    messages = []
    default_db = settings.DATABASES.get("default", {})
    engine = default_db.get("ENGINE", "")
    if "sqlite3" in engine:
        if settings.DEBUG:
            messages.append(
                Warning(
                    "O banco de dados padrão é SQLite.",
                    hint="SQLite não suporta operações concorrentes adequadamente. Use PostgreSQL em produção.",
                    id="SHOPMAN_W001",
                )
            )
        else:
            messages.append(
                Error(
                    "O banco de dados padrão é SQLite fora do modo DEBUG.",
                    hint="Defina DATABASE_URL com PostgreSQL antes de qualquer ambiente público.",
                    id="SHOPMAN_E007",
                )
            )
    return messages


@register()
def check_notification_backend(app_configs, **kwargs):
    warnings = []
    if not settings.DEBUG:
        adapters = getattr(settings, "SHOPMAN_NOTIFICATION_ADAPTERS", {})
        if not adapters:
            return warnings
        for method, path in adapters.items():
            if path and "notification_console" in path:
                warnings.append(
                    Warning(
                        f"Adapter de notificação para '{method}' é console fora do modo DEBUG.",
                        hint="Configure SHOPMAN_NOTIFICATION_ADAPTERS com um backend real (email, SMS, WhatsApp).",
                        id="SHOPMAN_W002",
                    )
                )
    return warnings


@register(deploy=True)
def check_guestman_webhook_secret(app_configs, **kwargs):
    """ManyChat inbound webhook secret.

    O endpoint falha FECHADO sem a secret (rejeita payloads não assinados — ver
    guestman Gates.provider_event_authenticity com allow_unsigned=DEBUG). Logo,
    faltar a secret NÃO é insegurança: só desativa o sync inbound de assinantes.
    Warning (não bloqueia o deploy) — configure só se usar o fluxo inbound.
    """
    messages = []
    if not settings.DEBUG:
        secret = getattr(settings, "MANYCHAT_WEBHOOK_SECRET", "")
        if not secret:
            messages.append(
                Warning(
                    "MANYCHAT_WEBHOOK_SECRET não configurado — webhook inbound do "
                    "ManyChat inativo (rejeita tudo).",
                    hint=(
                        "Sem a secret o endpoint falha fechado (seguro). Defina "
                        "MANYCHAT_WEBHOOK_SECRET (mesmo valor no webhook do ManyChat) "
                        "apenas se usar o sync inbound de assinantes."
                    ),
                    id="SHOPMAN_W009",
                )
            )
    return messages


@register(deploy=True)
def check_courier_credentials(app_configs, **kwargs):
    """Machine courier: credenciais obrigatórias quando o adapter real está ligado.

    Fora do check_webhook_tokens porque a severidade é condicional ao adapter:
    sem SHOPMAN_COURIER_ADAPTER apontando para courier_machine, nada aqui se
    aplica (deployment sem courier sobe limpo). Com o adapter ligado:
    - sem username/password/api_key → Error (todo despacho automático falharia);
    - sem webhook_token → Warning (o polling cobre o status, com latência).
    """
    messages = []
    if settings.DEBUG:
        return messages

    adapter_path = getattr(settings, "SHOPMAN_COURIER_ADAPTER", None) or ""
    if "courier_machine" not in adapter_path:
        return messages

    cfg = getattr(settings, "SHOPMAN_MACHINE", {}) or {}
    missing = [
        env
        for key, env in (
            ("username", "MACHINE_API_USER"),
            ("password", "MACHINE_API_PASSWORD"),
            ("api_key", "MACHINE_API_KEY"),
        )
        if not cfg.get(key)
    ]
    if missing:
        messages.append(
            Error(
                "SHOPMAN_COURIER_ADAPTER aponta para courier_machine sem credenciais: "
                f"faltam {', '.join(missing)}.",
                hint=(
                    "O despacho automático de entregadores falharia em toda corrida. "
                    "Defina as variáveis de ambiente da Machine ou remova "
                    "SHOPMAN_COURIER_ADAPTER."
                ),
                id="SHOPMAN_E011",
            )
        )
    if not cfg.get("webhook_token"):
        messages.append(
            Warning(
                "SHOPMAN_MACHINE['webhook_token'] não configurado — status da corrida "
                "só por polling (latência de até courier_poll_seconds).",
                hint=(
                    "Defina MACHINE_WEBHOOK_TOKEN e cadastre o endpoint com "
                    "`manage.py machine_register_webhook` para receber status em push."
                ),
                id="SHOPMAN_W010",
            )
        )
    return messages


@register(deploy=True)
def check_doorman_access_link_api_key(app_configs, **kwargs):
    errors = []
    if settings.DEBUG:
        return errors

    doorman = getattr(settings, "DOORMAN", {}) or {}
    if not doorman.get("ACCESS_LINK_API_KEY"):
        errors.append(
            Error(
                "DOORMAN['ACCESS_LINK_API_KEY'] não está configurado em produção.",
                hint=(
                    "Defina DOORMAN_ACCESS_LINK_API_KEY. O endpoint de criação "
                    "de access links é CSRF-exempt por ser integração servidor-servidor "
                    "e deve falhar fechado fora de DEBUG."
                ),
                id="SHOPMAN_E008",
            )
        )
    return errors


@register(deploy=True)
def check_debug_otp_exposure(app_configs, **kwargs):
    messages = []
    if not getattr(settings, "SHOPMAN_EXPOSE_DEBUG_OTP", False):
        return messages

    environment = str(getattr(settings, "SHOPMAN_ENVIRONMENT", "production")).strip().lower()
    if environment not in {"development", "dev", "local", "staging"}:
        messages.append(
            Error(
                "SHOPMAN_EXPOSE_DEBUG_OTP está habilitado fora de ambiente não produtivo.",
                hint=(
                    "Desabilite SHOPMAN_EXPOSE_DEBUG_OTP antes de produção. "
                    "O código OTP debug só pode aparecer em desenvolvimento ou staging técnico."
                ),
                id="SHOPMAN_E010",
            )
        )
    elif not settings.DEBUG:
        messages.append(
            Warning(
                "OTP debug está exposto em ambiente não-DEBUG.",
                hint=(
                    "Permitido apenas para staging técnico. Remova "
                    "SHOPMAN_EXPOSE_DEBUG_OTP antes de go-live."
                ),
                id="SHOPMAN_W007",
            )
        )
    return messages


@register(deploy=True)
def check_shared_cache_backend(app_configs, **kwargs):
    errors = []
    if settings.DEBUG:
        return errors

    backend = settings.CACHES.get("default", {}).get("BACKEND", "")
    if backend != "django.core.cache.backends.redis.RedisCache":
        errors.append(
            Error(
                "Cache compartilhado Redis não está configurado em produção.",
                hint=(
                    "Defina REDIS_URL. O Shopman usa cache compartilhado para "
                    "django-ratelimit, caches operacionais curtos e fanout SSE "
                    "multi-worker via django-eventstream."
                ),
                id="SHOPMAN_E006",
            )
        )
    return errors


@register()
def check_pricing_backend(app_configs, **kwargs):
    warnings = []
    if not settings.DEBUG:
        offerman = getattr(settings, "OFFERMAN", {}) or {}
        if not offerman.get("PRICING_BACKEND"):
            warnings.append(
                Warning(
                    "OFFERMAN['PRICING_BACKEND'] não está configurado.",
                    hint="Defina OFFERMAN['PRICING_BACKEND'] com o backend de precificação contextual (ex: shopman.shop.adapters.pricing.StorefrontPricingBackend).",
                    id="SHOPMAN_W005",
                )
            )
    return warnings


@register()
def check_fiscal_adapter(app_configs, **kwargs):
    warnings = []
    fiscal_adapter = getattr(settings, "SHOPMAN_FISCAL_ADAPTER", None)
    if fiscal_adapter:
        return warnings

    from django.db.utils import OperationalError, ProgrammingError

    from shopman.shop.models import Channel

    try:
        channels = list(Channel.objects.all())
    except (OperationalError, ProgrammingError):
        return warnings  # tables not ready (initial migration)

    for channel in channels:
        data = channel.config or {}
        fiscal = data.get("fiscal", {})
        if fiscal.get("enabled"):
            warnings.append(
                Warning(
                    f"Canal '{channel.ref}' tem fiscal ativo mas nenhum adapter fiscal está configurado.",
                    hint="Defina SHOPMAN_FISCAL_ADAPTER em settings ou desative fiscal neste canal.",
                    id="SHOPMAN_W003",
                )
            )

    return warnings


@register()
def check_listing_channel_parity(app_configs, **kwargs):
    """Warn when a Listing.ref has no matching Channel.ref (convention: channel.ref == listing.ref)."""
    warnings = []

    from django.db.utils import OperationalError, ProgrammingError

    try:
        from shopman.offerman.models import Listing

        from shopman.shop.models import Channel

        listing_refs = set(Listing.objects.filter(is_active=True).values_list("ref", flat=True))
        channel_refs = set(Channel.objects.values_list("ref", flat=True))

        orphans = listing_refs - channel_refs
        for ref in sorted(orphans):
            warnings.append(
                Warning(
                    f"Listing '{ref}' não tem Channel com ref correspondente.",
                    hint=(
                        "A convenção do Shopman é channel.ref == listing.ref. "
                        "Crie um Channel com este ref ou desative o Listing."
                    ),
                    id="SHOPMAN_W004",
                )
            )
    except (OperationalError, ProgrammingError, ImportError):
        pass  # tables not ready or offerman not installed

    return warnings
