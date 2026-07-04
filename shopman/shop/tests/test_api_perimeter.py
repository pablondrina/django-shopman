"""Perímetro das APIs do kernel — guardrail de segurança.

Os pacotes do kernel (orderman, offerman, stockman, craftsman, guestman, payman)
expõem ViewSets DRF de CRUD com o default global `IsAuthenticated`. Como clientes
do storefront viram usuários Django autenticados (login OTP chama `login()`), montar
essas rotas no deployment deixaria qualquer cliente logado ler/mutar dados do kernel
(sessões e comandas POS, base de PII, ledger de estoque, BOM, payment intents).

Nenhuma superfície consome essas rotas — os apps Nuxt entram por `api/v1/` (storefront)
e `api/v1/backstage/` (projections gateadas por permissão). Elas foram desmontadas do
`config/urls.py`. Este teste trava a re-introdução silenciosa.

Contrato: se um dia uma dessas superfícies ganhar consumidor real, ela volta COM
permissão explícita (`IsAdminUser`/`DjangoModelPermissions`) e este guardrail é
atualizado deliberadamente — nunca por reflexo.
"""

import pytest
from django.urls import get_resolver

# Prefixos de CRUD do kernel que NÃO podem estar montados no deployment.
UNMOUNTED_KERNEL_API_PREFIXES = [
    "api/orderman/",
    "api/offerman/",
    "api/stockman/",
    "api/craftsman/",
    "api/customers/",
    "api/payments/",
]

# Prefixos que DEVEM continuar montados (consumidos pelas superfícies/BFF).
MOUNTED_SURFACE_API_PREFIXES = [
    "api/v1/",          # storefront headless (BFF do cliente)
    "api/v1/backstage/",  # projections gateadas dos apps operador (Nuxt)
]


def _mounted_prefixes() -> set[str]:
    """Coleta os prefixos de include de 1º nível do ROOT_URLCONF (regex → texto)."""
    prefixes = set()
    for pattern in get_resolver().url_patterns:
        # URLResolver (include) tem .url_patterns; extraímos o prefixo textual do regex.
        regex = getattr(pattern.pattern, "regex", None)
        if regex is None:
            continue
        # `^api/orderman/` → `api/orderman/`
        prefixes.add(regex.pattern.lstrip("^"))
    return prefixes


@pytest.mark.parametrize("prefix", UNMOUNTED_KERNEL_API_PREFIXES)
def test_kernel_crud_api_is_not_mounted(prefix):
    """Nenhum include do ROOT_URLCONF cobre um prefixo de CRUD do kernel."""
    mounted = _mounted_prefixes()
    assert prefix not in mounted, (
        f"{prefix} está montado no config/urls.py. APIs de CRUD do kernel não podem "
        "ser expostas no deployment — são superfície de ataque sem consumidor "
        "(clientes têm sessão Django). Ver test_api_perimeter."
    )


@pytest.mark.parametrize("prefix", MOUNTED_SURFACE_API_PREFIXES)
def test_surface_api_stays_mounted(prefix):
    """As APIs de superfície seguem montadas — pega remoção acidental."""
    mounted = _mounted_prefixes()
    assert prefix in mounted, (
        f"{prefix} não está mais montado no config/urls.py — uma superfície viva "
        "(BFF/Nuxt) foi desmontada por engano."
    )
