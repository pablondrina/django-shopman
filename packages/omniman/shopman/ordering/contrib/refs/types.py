"""
RefType definitions.

RefTypes são definidos como dataclasses imutáveis em código (não no banco).
Isso garante versionamento, imutabilidade e previsibilidade.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RefType:
    """
    Definição de um tipo de localizador/etiqueta.

    Attributes:
        slug: Identificador único (ex: "POS_TABLE", "ORDER_NUMBER")
        label: Rótulo para UI (ex: "Mesa", "Número do Pedido")
        target_kind: Tipo de target permitido ("SESSION", "ORDER", "BOTH")
        scope_keys: Chaves obrigatórias no scope (ex: ("store_id", "business_date"))
        unique_while_active: Se True, unicidade só entre Refs ACTIVE
        expires_on_session_close: Se True, desativa Ref quando Session fecha
        copy_to_order: Se True, copia Ref para Order no commit
    """

    slug: str
    label: str
    target_kind: Literal["SESSION", "ORDER", "BOTH"]
    scope_keys: tuple[str, ...]
    unique_while_active: bool = True
    expires_on_session_close: bool = True
    copy_to_order: bool = False

    def __post_init__(self):
        if not self.slug:
            raise ValueError("RefType.slug cannot be empty")
        if not self.slug.replace("_", "").isalnum():
            raise ValueError("RefType.slug must be alphanumeric with underscores")


# =============================================================================
# RefTypes padrão (operacionais)
# =============================================================================

POS_TABLE = RefType(
    slug="POS_TABLE",
    label="Mesa",
    target_kind="SESSION",
    scope_keys=("store_id", "business_date"),
    unique_while_active=True,
    expires_on_session_close=True,
    copy_to_order=False,
)

POS_TAB = RefType(
    slug="POS_TAB",
    label="Comanda",
    target_kind="SESSION",
    scope_keys=("store_id", "business_date"),
    unique_while_active=True,
    expires_on_session_close=True,
    copy_to_order=False,
)

# =============================================================================
# RefTypes padrão (Order)
# =============================================================================

ORDER_REF = RefType(
    slug="ORDER_REF",
    label="Referência do Pedido",
    target_kind="ORDER",
    scope_keys=("store_id",),
    unique_while_active=False,  # Sempre único (não apenas entre ACTIVE)
    expires_on_session_close=False,
    copy_to_order=False,
)

EXTERNAL_ORDER = RefType(
    slug="EXTERNAL_ORDER",
    label="Pedido Externo",
    target_kind="ORDER",
    scope_keys=("channel", "merchant_id"),
    unique_while_active=False,
    expires_on_session_close=False,
    copy_to_order=False,
)


# Lista de todos os tipos padrão para registro automático
DEFAULT_REF_TYPES = [
    POS_TABLE,
    POS_TAB,
    ORDER_REF,
    EXTERNAL_ORDER,
]
