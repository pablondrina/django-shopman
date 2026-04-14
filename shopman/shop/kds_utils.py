"""KDS dispatch utility — routes order items to KDS instances.

Bundles (combos) are exploded into their components so each component
routes to the correct KDS station independently.

TODO WP-R3: migrate to shopman.services.kds
"""

from __future__ import annotations

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


def dispatch_to_kds(order) -> list:
    """Route order items to matching KDS instances, creating KDSTickets.

    For each OrderItem:
    - If bundle: explode into components, route each component
    - If component has active Recipe -> type = "prep"
    - Otherwise -> type = "picking"
    - Match to KDSInstance by collection first, then type
    - Fallback: catch-all instances (no collections assigned)

    Returns list of created KDSTicket instances.
    """
    from shopman.offerman.models import CollectionItem, ProductComponent

    from shopman.shop.models import KDSInstance, KDSTicket

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

    # 3. Explode bundles: find components for any bundle SKUs
    bundle_components = defaultdict(list)  # parent_sku -> [(component_sku, component_name, qty)]
    components_qs = (
        ProductComponent.objects
        .filter(parent__sku__in=skus)
        .select_related("component")
    )
    for pc in components_qs:
        bundle_components[pc.parent.sku].append((
            pc.component.sku,
            pc.component.name,
            pc.qty,
        ))

    # Build flat list of routable items (exploding bundles)
    routable_items = []  # [(sku, name, qty, notes, is_component_of)]
    for item in order_items:
        if item.sku in bundle_components:
            # Bundle: route each component separately
            for comp_sku, comp_name, comp_qty in bundle_components[item.sku]:
                routable_items.append((
                    comp_sku,
                    f"{comp_name} ({item.name or item.sku})",
                    int(item.qty * comp_qty),
                    item.meta.get("notes", "") if item.meta else "",
                    item.sku,
                ))
        else:
            routable_items.append((
                item.sku,
                item.name or item.sku,
                int(item.qty),
                item.meta.get("notes", "") if item.meta else "",
                None,
            ))

    # 4. Collect all SKUs to route (including exploded components)
    all_skus = list({sku for sku, *_ in routable_items})

    # 5. Bulk-query primary collections: sku -> collection_id
    sku_to_collection = {}
    ci_qs = (
        CollectionItem.objects.filter(product__sku__in=all_skus, is_primary=True)
        .select_related("collection")
    )
    for ci in ci_qs:
        sku_to_collection[ci.product.sku] = ci.collection_id

    # 6. Bulk-query recipes: set of SKUs that need prep
    try:
        from shopman.craftsman.models import Recipe

        prep_skus = set(
            Recipe.objects.filter(output_ref__in=all_skus, is_active=True)
            .values_list("output_ref", flat=True)
        )
    except ImportError:
        prep_skus = set()

    # 7. Build instance lookup
    col_map = defaultdict(list)       # col_id -> [instances]
    type_col_map = defaultdict(list)  # (type, col_id) -> [instances]
    catchall_map = defaultdict(list)  # type -> [instances with no collections]

    for inst in instances:
        col_ids = set(inst.collections.values_list("id", flat=True))
        if not col_ids:
            catchall_map[inst.type].append(inst)
        else:
            for col_id in col_ids:
                col_map[col_id].append(inst)
                type_col_map[(inst.type, col_id)].append(inst)

    # 8. Route each item to its target KDS instance(s)
    instance_items = defaultdict(list)  # instance.pk -> [item_dicts]

    for sku, name, qty, notes, parent_sku in routable_items:
        item_type = "prep" if sku in prep_skus else "picking"
        col_id = sku_to_collection.get(sku)

        matched = []
        if col_id:
            matched = type_col_map.get((item_type, col_id), [])
            if not matched:
                matched = col_map.get(col_id, [])
        if not matched:
            matched = catchall_map.get(item_type, [])

        if not matched:
            logger.debug(
                "kds_dispatch: no matching instance for sku=%s type=%s parent=%s",
                sku, item_type, parent_sku or "-",
            )
            continue

        item_dict = {
            "sku": sku,
            "name": name,
            "qty": qty,
            "notes": notes,
            "checked": False,
        }

        for inst in matched:
            instance_items[inst.pk].append(item_dict)

    # 9. Create KDSTickets
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
