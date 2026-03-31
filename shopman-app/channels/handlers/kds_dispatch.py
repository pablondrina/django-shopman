"""Dispatch order items to KDS instances based on collection + recipe."""

from __future__ import annotations

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


def dispatch_to_kds(order) -> list:
    """Route order items to matching KDS instances, creating KDSTickets.

    For each OrderItem:
    - If item's product has an active Recipe → type = "prep"
    - Otherwise → type = "picking"
    - Match to KDSInstance by type + collection overlap
    - Fallback: instances with no collections (catch-all)

    Returns list of created KDSTicket instances.
    """
    from shopman.offering.models import CollectionItem

    from shop.models import KDSInstance, KDSTicket

    # 1. Get all active KDS instances (exclude expedition — it's query-based)
    instances = list(
        KDSInstance.objects.filter(is_active=True)
        .exclude(type="expedition")
        .prefetch_related("collections")
    )
    if not instances:
        return []

    # 2. Collect SKUs from order items
    order_items = list(order.items.all())
    if not order_items:
        return []

    skus = [item.sku for item in order_items]

    # 3. Bulk-query primary collections: sku → collection_id
    sku_to_collection = {}
    ci_qs = (
        CollectionItem.objects.filter(product__sku__in=skus, is_primary=True)
        .select_related("collection")
    )
    for ci in ci_qs:
        sku_to_collection[ci.product.sku] = ci.collection_id

    # 4. Bulk-query recipes: set of SKUs that need prep
    try:
        from shopman.crafting.models import Recipe

        prep_skus = set(
            Recipe.objects.filter(output_ref__in=skus, is_active=True)
            .values_list("output_ref", flat=True)
        )
    except ImportError:
        prep_skus = set()

    # 5. Build instance lookup: (type, collection_id) → [instance, ...]
    #    Also track catch-all instances (no collections assigned)
    type_col_map = defaultdict(list)  # (type, col_id) → [instances]
    catchall_map = defaultdict(list)  # type → [instances with no collections]

    for inst in instances:
        col_ids = set(inst.collections.values_list("id", flat=True))
        if not col_ids:
            catchall_map[inst.type].append(inst)
        else:
            for col_id in col_ids:
                type_col_map[(inst.type, col_id)].append(inst)

    # 6. Route each item to its target KDS instance(s)
    instance_items = defaultdict(list)  # instance.pk → [item_dicts]

    for item in order_items:
        item_type = "prep" if item.sku in prep_skus else "picking"
        col_id = sku_to_collection.get(item.sku)

        # Find matching instances
        matched = []
        if col_id:
            matched = type_col_map.get((item_type, col_id), [])
        if not matched:
            matched = catchall_map.get(item_type, [])

        if not matched:
            logger.debug(
                "kds_dispatch: no matching instance for sku=%s type=%s",
                item.sku, item_type,
            )
            continue

        item_dict = {
            "sku": item.sku,
            "name": item.name or item.sku,
            "qty": int(item.qty),
            "notes": item.meta.get("notes", "") if item.meta else "",
            "checked": False,
        }

        for inst in matched:
            instance_items[inst.pk].append(item_dict)

    # 7. Create KDSTickets
    tickets = []
    inst_by_pk = {inst.pk: inst for inst in instances}

    for inst_pk, items in instance_items.items():
        ticket = KDSTicket.objects.create(
            order=order,
            kds_instance=inst_by_pk[inst_pk],
            items=items,
        )
        tickets.append(ticket)

    logger.info(
        "kds_dispatch: created %d tickets for order=%s",
        len(tickets), order.ref,
    )
    return tickets
