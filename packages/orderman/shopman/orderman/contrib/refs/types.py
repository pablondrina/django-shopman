"""
Orderman-specific RefTypes.

These types are registered in shopman.refs via OrdermanConfig.ready().
"""

from shopman.refs.types import RefType

POS_TABLE = RefType(
    slug="POS_TABLE",
    label="Mesa",
    allowed_targets=("orderman.Session",),
    scope_keys=("store_id", "business_date"),
    unique_scope="active",
)

POS_TAB = RefType(
    slug="POS_TAB",
    label="Comanda",
    allowed_targets=("orderman.Session",),
    scope_keys=("store_id", "business_date"),
    unique_scope="active",
)

ORDER_REF = RefType(
    slug="ORDER_REF",
    label="Referencia do Pedido",
    allowed_targets=("orderman.Order",),
    scope_keys=("store_id",),
    unique_scope="all",
)

EXTERNAL_ORDER = RefType(
    slug="EXTERNAL_ORDER",
    label="Pedido Externo",
    allowed_targets=("orderman.Order",),
    scope_keys=("channel", "merchant_id"),
    unique_scope="all",
)

DEFAULT_REF_TYPES = [POS_TABLE, POS_TAB, ORDER_REF, EXTERNAL_ORDER]
