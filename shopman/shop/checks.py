"""
Django system checks for Shopman.

Registered in ShopmanConfig.ready() via checks.register().

Errors (block runserver/migrate --deploy in production):
  SHOPMAN_E001  SECRET_KEY is the development default
  SHOPMAN_E002  ALLOWED_HOSTS is empty or contains '*'
  SHOPMAN_E003  PIX or CARD payment adapter is payment_mock
  SHOPMAN_E004  A webhook integration has no token configured
  SHOPMAN_E005  Guestman (Manychat) webhook secret not configured

Warnings (non-blocking, logged at startup):
  SHOPMAN_W001  Database backend is SQLite
  SHOPMAN_W002  Notification backend is console while DEBUG=False
  SHOPMAN_W003  No fiscal adapter configured while a fiscal-enabled channel exists
  SHOPMAN_W004  OFFERMAN pricing backend not configured
"""

from __future__ import annotations

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
    errors = []
    if not settings.DEBUG:
        adapters = getattr(settings, "SHOPMAN_PAYMENT_ADAPTERS", {})
        for method in ("pix", "card"):
            path = adapters.get(method, "")
            if not path or "payment_mock" in path:
                errors.append(
                    Error(
                        f"Adapter de pagamento para método '{method}' aponta para payment_mock em produção.",
                        hint=(
                            f"Defina SHOPMAN_PAYMENT_ADAPTERS['{method}'] com o adapter real "
                            f"(ex: shopman.adapters.payment_efi ou shopman.adapters.payment_stripe)."
                        ),
                        id="SHOPMAN_E003",
                    )
                )
    return errors


@register(deploy=True)
def check_webhook_tokens(app_configs, **kwargs):
    """Require a webhook token for every inbound integration.

    The runtime rejects unauthenticated requests in every environment already
    (there is no ``SKIP_SIGNATURE`` bypass). This check exists to fail early
    at ``manage.py check --deploy`` time with a clear message, so prod deploys
    do not ship with a silently broken webhook.
    """
    errors = []
    if settings.DEBUG:
        return errors

    # (settings_attr, persona, env_var)
    integrations = [
        ("SHOPMAN_EFI_WEBHOOK", "EFI", "EFI_WEBHOOK_TOKEN"),
        ("SHOPMAN_IFOOD", "iFood", "IFOOD_WEBHOOK_TOKEN"),
    ]
    for attr, name, env_var in integrations:
        cfg = getattr(settings, attr, {}) or {}
        if not cfg.get("webhook_token"):
            errors.append(
                Error(
                    f"{attr}['webhook_token'] não está configurado em produção.",
                    hint=(
                        f"{name} authentication uses the same code path in "
                        f"dev and prod. Defina {env_var} via variável de "
                        f"ambiente — mesmo em dev, para que o caminho de "
                        f"verificação seja exercitado localmente."
                    ),
                    id="SHOPMAN_E004",
                )
            )
    return errors


@register()
def check_database_backend(app_configs, **kwargs):
    warnings = []
    default_db = settings.DATABASES.get("default", {})
    engine = default_db.get("ENGINE", "")
    if "sqlite3" in engine:
        warnings.append(
            Warning(
                "O banco de dados padrão é SQLite.",
                hint="SQLite não suporta operações concorrentes adequadamente. Use PostgreSQL em produção.",
                id="SHOPMAN_W001",
            )
        )
    return warnings


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
                    id="SHOPMAN_W004",
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
