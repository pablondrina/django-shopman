"""Settings da SUÍTE DE TESTES — herméticos ao ambiente do desenvolvedor.

``config/settings.py`` lê ``os.environ`` (e o ``.env`` local, via ``load_dotenv``)
no import. Isso é correto para runtime, mas contaminava os testes: um ``.env``
com ``SHOPMAN_REQUIRE_ACTIVE_OPERATOR=true`` derrubava ``test_order_confirm``
(5×403), credenciais reais (Comtele/EFI/iFood) tiravam adapters do modo inerte,
e por aí vai — o resultado da suíte dependia da máquina.

Este módulo (apontado por ``DJANGO_SETTINGS_MODULE`` no ``pyproject.toml``)
importa o settings base e RE-PINA todo valor env-sensível que muda comportamento
testado para o baseline canônico do CI (``.github/workflows/runtime-gate.yml``:
``DJANGO_DEBUG=true`` e nenhuma outra env de comportamento). Assim ``make test``
produz o mesmo resultado em qualquer máquina, com qualquer ``.env``.

O que fica DELIBERADAMENTE sem pino (eixos legítimos de execução, não
contaminação):

* ``DATABASES``/``REDIS_URL`` — o gate de runtime roda a MESMA suíte contra
  PostgreSQL + Redis via ``DATABASE_URL``/``REDIS_URL`` (ver ``make test-runtime``).
* ``SECRET_KEY``/``ALLOWED_HOSTS`` — inertes em teste (o test client usa
  ``testserver``, adicionado por ``setup_test_environment``).
* ``EMAIL_*`` — o test runner do Django força o backend ``locmem``.
* ``LOGGING`` — só formatação; ``caplog`` captura records, não formato.

Os ``@override_settings`` por teste continuam funcionando normalmente: eles
empilham por cima deste baseline e restauram para ele.
"""

from __future__ import annotations

import os

# ── Baseline ANTES do import do settings base ────────────────────────────────
# O settings base decide coisas NO IMPORT a partir destas envs (asserts de
# produção, blocos `if DEBUG:`, init do Sentry). `load_dotenv(override=False)`
# não sobrescreve chaves já presentes em os.environ, então forçar aqui vence
# tanto o shell quanto o `.env` local.
os.environ["DJANGO_DEBUG"] = "true"  # como no runtime-gate.yml
os.environ["SENTRY_DSN"] = ""  # a suíte nunca inicializa o Sentry

from config.settings import *  # noqa: E402,F403 — base primeiro, pinos depois

# ── Flags de comportamento (runtime) ─────────────────────────────────────────
SHOPMAN_ENVIRONMENT = "development"
SHOPMAN_EXPOSE_DEBUG_OTP = True
SHOPMAN_REQUIRE_ACTIVE_OPERATOR = False
SHOPMAN_ADMIN_REQUIRE_2FA = False
SHOPMAN_EMPLOYEE_DISCOUNT_PERCENT = 20
SHOPMAN_POS_DISCOUNT_APPROVAL_THRESHOLD_Q = 0
SHOPMAN_CART_MUTATION_PERF_LOG_MS = 0.0
SHOPMAN_PIX_EXPIRY_SECONDS = 3600
STOREFRONT_TRACKING_POLL_SECONDS = 30
STOCKMAN_ALERT_COOLDOWN_MINUTES = 60
GOOGLE_MAPS_API_KEY = ""

# ── Adapters e seams plugáveis ───────────────────────────────────────────────
SHOPMAN_PAYMENT_ADAPTERS = {
    "pix": "shopman.shop.adapters.payment_mock",
    "card": "shopman.shop.adapters.payment_mock",
    "cash": None,
    "external": None,
}
SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS = False
SHOPMAN_MOCK_PIX_AUTO_CONFIRM = False
SHOPMAN_MOCK_PIX_CONFIRM_DELAY_SECONDS = 10
SHOPMAN_NOTIFICATION_ADAPTERS = {
    "manychat": "shopman.shop.adapters.notification_manychat",
    "email": "shopman.shop.adapters.notification_email",
    "console": "shopman.shop.adapters.notification_console",  # DEBUG=true no CI
}
SHOPMAN_FISCAL_ADAPTER = None
SHOPMAN_FISCAL_EMISSION_RESOLVER = "shopman.shop.fiscal_resolvers.on_request_or_tax_id"
SHOPMAN_COURIER_ADAPTER = None
SHOPMAN_CUSTOMER_STRATEGY_MODULES = []
STOCKMAN["SKU_VALIDATOR"] = "shopman.shop.adapters.sku_validator.ComposedSkuValidator"  # noqa: F405
STOCKMAN["STRICT_SHELF_LIFE_WINDOW"] = False  # noqa: F405
GUESTMAN = {"ORDER_HISTORY_BACKEND": "shopman.guestman.adapters.orderman.OrdermanOrderHistoryBackend"}
OFFERMAN["PROJECTION_BACKENDS"] = {}  # noqa: F405 — IFOOD_CATALOG_PROJECTION desligado

# Trava de segurança dos adapters externos: sem opt-in de envio real na suíte.
SHOPMAN_ALLOW_EXTERNAL_IN_DEBUG = False
SHOPMAN_SMS_ALLOW_IN_DEBUG = False
SHOPMAN_MANYCHAT_ALLOW_IN_DEBUG = False
SHOPMAN_WHATSAPP_ALLOW_IN_DEBUG = False
SHOPMAN_MACHINE_ALLOW_IN_DEBUG = False

# ── Credenciais externas: SEMPRE vazias na suíte (adapters inertes/no-op) ────
MANYCHAT_API_TOKEN = ""
MANYCHAT_WEBHOOK_SECRET = ""
SHOPMAN_MANYCHAT.update(  # noqa: F405
    api_token="",
    base_url="https://api.manychat.com/fb",
    timeout=15,
    resolver="shopman.guestman.contrib.manychat.resolver.ManychatSubscriberResolver.resolve",
)
SHOPMAN_WHATSAPP.update(  # noqa: F405
    VERIFY_TOKEN="",
    STOREFRONT_URL="",
    PHONE_NUMBER_ID="",
    ACCESS_TOKEN="",
    GRAPH_VERSION="v21.0",
    DEFAULT_LANG="pt_BR",
    timeout=15,
    templates={},
)
SHOPMAN_WA_VERIFY.update(  # noqa: F405
    number="",
    access_message_template="Meu código de acesso é {code}",
)
SHOPMAN_SMS.update(  # noqa: F405
    api_key="",
    route="",
    tag="shopman-otp",
    account_sid="",
    auth_token="",
    from_number="",
    messaging_service_sid="",
    code_message="",
    timeout=15,
)
SHOPMAN_IFOOD.update(  # noqa: F405
    webhook_token="",
    merchant_id="",
    client_id="",
    client_secret="",
    api_base="https://merchant-api.ifood.com.br",
    timeout=30,
    catalog_category_map={},
    catalog_default_category="",
    cancellation_default_code="",
    cancellation_default_reason="Problemas de sistema na loja",
    webhook_hmac_secret="",
)
SHOPMAN_MACHINE.update(  # noqa: F405
    base_url="https://api.taximachine.com.br/api/integracao",
    details_base="https://api.taximachine.com.br/integracao/v1",
    username="",
    password="",
    api_key="",
    webhook_token="",
    forma_pagamento="F",
    retorno=False,
    timeout=15,
    cancel_reason_id=1,
)
STRIPE_PUBLISHABLE_KEY = ""
STRIPE_SECRET_KEY = ""
SHOPMAN_STRIPE.update(  # noqa: F405
    publishable_key="",
    secret_key="",
    webhook_secret="",
    capture_method="manual",
    domain="http://localhost:8000",
)
SHOPMAN_EFI.update(  # noqa: F405
    sandbox=True,
    client_id="",
    client_secret="",
    certificate_path="",
    pix_key="",
)
SHOPMAN_EFI_WEBHOOK.update(  # noqa: F405
    webhook_token="",
    mtls_header="HTTP_X_SSL_CLIENT_VERIFY",
)
SHOPMAN_FOCUS_NFE.update(  # noqa: F405
    environment="homologacao",
    token="",
    cnpj_emitente="",
    serie_nfce="",
    completa_nfce="1",
    local_destino_nfce="1",
    presenca_comprador_nfce="1",
    modalidade_frete_nfce="9",
    natureza_operacao="VENDA AO CONSUMIDOR",
    default_cfop_nfce="5102",
    timeout=30,
    base_url="",
)

# ── Doorman (chaves env-derivadas; o resto do dict fica como no base) ────────
DOORMAN.update(  # noqa: F405
    DEFAULT_DOMAIN="localhost:8000",
    USE_HTTPS=False,
    ACCESS_LINK_API_KEY="",
    MESSAGE_SENDER_CLASS="shopman.doorman.senders.ConsoleSender",
    CUSTOMER_RESOLVER_CLASS="shopman.guestman.adapters.auth.CustomerResolver",
    DELIVERY_CHAIN=["sms", "console"],  # DEBUG=true, ambiente development
    ACCESS_LINK_ENTRY_URL="",
)

# ── Superfícies / URLs públicas ──────────────────────────────────────────────
SHOPMAN_STOREFRONT_BASE_URL = ""
SHOPMAN_POS_BASE_URL = ""
SHOPMAN_ORDERS_BASE_URL = ""
SHOPMAN_KDS_BASE_URL = ""
SHOPMAN_PRODUCTION_BASE_URL = ""
SHOPMAN_SURFACE_URLS = {}
SHOPMAN_POS_CHANNEL_REF = "pdv"
SHOPMAN_OPERATOR_COOKIE_DOMAIN = ""
SHOPMAN_OPERATOR_API_HOST = ""

# ── DRF: rate limit no default do CI ─────────────────────────────────────────
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {"anon": "120/minute"}  # noqa: F405
