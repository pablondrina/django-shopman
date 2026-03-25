"""
Ordering contrib/refs — Localizadores e etiquetas externas.

Permite associar múltiplas "etiquetas" (mesa, comanda, senha, order number, etc.)
a Sessions e Orders, com controle de unicidade, scope e lifecycle.

Uso:
    from shopman.ordering.contrib.refs.services import attach_ref, resolve_ref, deactivate_refs
    from shopman.ordering.contrib.refs.types import POS_TABLE, PICKUP_TICKET

    # Associar mesa a session
    attach_ref("SESSION", session.id, "POS_TABLE", "12", scope={"store_id": 1, "business_date": date.today()})

    # Buscar session pela mesa
    result = resolve_ref("POS_TABLE", "12", scope={"store_id": 1, "business_date": date.today()})
"""

# Lazy imports to avoid circular dependency during Django startup
# Use: from shopman.ordering.contrib.refs.services import attach_ref
# Or: from shopman.ordering.contrib.refs.exceptions import RefError
