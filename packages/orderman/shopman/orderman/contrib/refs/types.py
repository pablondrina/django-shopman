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
    label="POS tab",
    allowed_targets=("orderman.Session",),
    scope_keys=("store_id", "business_date"),
    unique_scope="active",
    generator="date_sequence",
    generator_format="{value:03d}",
)

ORDER_REF = RefType(
    slug="ORDER_REF",
    label="Referência do Pedido",
    allowed_targets=("orderman.Order",),
    scope_keys=("channel_ref", "business_date"),
    unique_scope="all",
    normalizer="upper_strip",
    validator=r"^[A-Z0-9][A-Z0-9_-]{1,63}-\d{6}-[A-Z0-9]{4}$",
    generator="short_uuid",
    generator_format="{channel_ref}-{date:%y%m%d}-{code:4}",
)

EXTERNAL_ORDER = RefType(
    slug="EXTERNAL_ORDER",
    label="Pedido Externo",
    allowed_targets=("orderman.Order",),
    scope_keys=("channel", "merchant_id"),
    unique_scope="all",
)

DEFAULT_REF_TYPES = [POS_TABLE, POS_TAB, ORDER_REF, EXTERNAL_ORDER]
