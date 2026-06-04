from __future__ import annotations

from datetime import date

from django.db import migrations

COLLECTIONS = [
    {
        "ref": "paes-artesanais",
        "name": "Pães Artesanais",
        "description": "",
        "sort_order": 1,
        "is_active": False,
    },
    {"ref": "rusticos", "name": "Rústicos", "description": "", "sort_order": 1, "is_active": True},
    {"ref": "focaccias", "name": "Focaccias", "description": "", "sort_order": 2, "is_active": False},
    {"ref": "macios", "name": "Macios", "description": "", "sort_order": 2, "is_active": True},
    {
        "ref": "brioches",
        "name": "Brioches & Pães Especiais",
        "description": "",
        "sort_order": 3,
        "is_active": False,
    },
    {"ref": "folhados", "name": "Folhados", "description": "", "sort_order": 3, "is_active": True},
    {
        "ref": "croissants-folhados",
        "name": "Croissants & Folhados",
        "description": "",
        "sort_order": 4,
        "is_active": False,
    },
    {"ref": "doces", "name": "Doces", "description": "", "sort_order": 4, "is_active": True},
    {
        "ref": "paes-doces",
        "name": "Pães Doces & Recheados",
        "description": "",
        "sort_order": 5,
        "is_active": False,
    },
    {"ref": "salgados", "name": "Salgados", "description": "", "sort_order": 5, "is_active": True},
    {
        "ref": "bebidas-quentes",
        "name": "Bebidas quentes",
        "description": "",
        "sort_order": 6,
        "is_active": True,
    },
    {
        "ref": "bebidas-geladas",
        "name": "Bebidas geladas",
        "description": "",
        "sort_order": 7,
        "is_active": True,
    },
    {
        "ref": "lanches",
        "name": "Lanches & Tartines",
        "description": "",
        "sort_order": 7,
        "is_active": False,
    },
    {
        "ref": "cafes-bebidas",
        "name": "Cafés & Bebidas",
        "description": "",
        "sort_order": 8,
        "is_active": False,
    },
    {"ref": "combos", "name": "Combos", "description": "", "sort_order": 9, "is_active": False},
]


COLLECTION_ITEMS = [
    ("rusticos", "BAGUETE", 0, True),
    ("rusticos", "BAGUETE-CAMPAGNE", 1, True),
    ("rusticos", "BAGUETE-GERGELIM", 2, True),
    ("rusticos", "MINI-BAGUETE", 3, True),
    ("rusticos", "BATARD", 4, True),
    ("rusticos", "FENDU", 5, True),
    ("rusticos", "TABATIERE", 6, True),
    ("rusticos", "ITALIANO-RUSTICO", 7, True),
    ("rusticos", "CAMPAGNE-OVAL", 8, True),
    ("rusticos", "CAMPAGNE-REDONDO", 9, True),
    ("rusticos", "CAMPAGNE-PASSAS", 10, True),
    ("rusticos", "CIABATTA", 11, True),
    ("rusticos", "PAO-HAMBURGER", 12, True),
    ("rusticos", "FOCACCIA-ALECRIM", 13, True),
    ("rusticos", "FOCACCIA-CEBOLA", 14, True),
    ("rusticos", "FOCACCIA-BACON", 15, True),
    ("rusticos", "MINI-FOCACCIA-ALECRIM", 16, True),
    ("rusticos", "MINI-FOCACCIA-CEBOLA", 17, True),
    ("rusticos", "MINI-FOCACCIA-BACON", 18, True),
    ("rusticos", "WP05-SMOKE-BREAD", 99, True),
    ("macios", "PAO-FORMA", 0, True),
    ("macios", "CHALLAH", 1, True),
    ("macios", "BRIOCHE", 2, True),
    ("macios", "BRIOCHE-BURGER", 3, True),
    ("macios", "PAO-HOTDOG", 4, True),
    ("folhados", "CROISSANT", 0, True),
    ("folhados", "PAIN-CHOCOLAT", 1, True),
    ("folhados", "MINI-CROISSANT", 2, True),
    ("folhados", "CHAUSSON", 3, True),
    ("folhados", "BICHON", 4, True),
    ("doces", "CORNET-CHOCOLATE", 0, True),
    ("doces", "CORNET", 1, True),
    ("doces", "MELON-PAN", 2, True),
    ("doces", "PAIN-RAISINS", 3, True),
    ("doces", "BRIOCHE-CHOCOLAT", 4, True),
    ("doces", "MADELEINE", 5, True),
    ("doces", "COMBO-PETIT-DEJ", 6, True),
    ("salgados", "DELI", 0, True),
    ("salgados", "HOTDOG", 1, True),
    ("salgados", "CROQUE-MONSIEUR", 2, True),
    ("salgados", "CROQUE-MADAME", 3, True),
    ("salgados", "QUICHE-LORRAINE", 4, True),
    ("salgados", "QUICHE-LEGUMES", 5, True),
    ("salgados", "TARTINE-SAUMON", 6, True),
    ("salgados", "TARTINE-TOMATE", 7, True),
    ("bebidas-quentes", "ESPRESSO", 0, True),
    ("bebidas-quentes", "ESPRESSO-DUPLO", 1, True),
    ("bebidas-quentes", "CAPPUCCINO", 2, True),
    ("bebidas-quentes", "LATTE", 3, True),
    ("bebidas-quentes", "CHOCOLATE-QUENTE", 4, True),
    ("bebidas-quentes", "CHA-EARL-GREY", 5, True),
    ("bebidas-geladas", "SUCO-LARANJA", 0, True),
]


KDS_ROUTES = {
    "lanches": ["salgados"],
    "cafes": ["bebidas-geladas", "bebidas-quentes"],
}


def _date(value):
    return date.fromisoformat(value) if value else None


def sync_collection_taxonomy(apps, schema_editor):
    Collection = apps.get_model("offerman", "Collection")
    CollectionItem = apps.get_model("offerman", "CollectionItem")
    Product = apps.get_model("offerman", "Product")
    KDSInstance = apps.get_model("backstage", "KDSInstance")

    synced_refs = [payload["ref"] for payload in COLLECTIONS]
    collection_by_ref = {}

    for payload in COLLECTIONS:
        collection, _ = Collection.objects.update_or_create(
            ref=payload["ref"],
            defaults={
                "name": payload["name"],
                "description": payload["description"],
                "valid_from": _date(payload.get("valid_from")),
                "valid_until": _date(payload.get("valid_until")),
                "sort_order": payload["sort_order"],
                "is_active": payload["is_active"],
                "parent": None,
            },
        )
        collection_by_ref[payload["ref"]] = collection

    CollectionItem.objects.filter(collection__ref__in=synced_refs).delete()

    desired_skus = {sku for _, sku, _, _ in COLLECTION_ITEMS}
    existing_products = {
        product.sku: product
        for product in Product.objects.filter(sku__in=desired_skus)
    }
    existing_collections = {
        collection.ref: collection
        for collection in Collection.objects.filter(ref__in={ref for ref, _, _, _ in COLLECTION_ITEMS})
    }

    primary_skus = {sku for _, sku, _, is_primary in COLLECTION_ITEMS if is_primary}
    CollectionItem.objects.filter(product__sku__in=primary_skus, is_primary=True).update(is_primary=False)

    for collection_ref, sku, sort_order, is_primary in COLLECTION_ITEMS:
        product = existing_products.get(sku)
        collection = existing_collections.get(collection_ref)
        if product is None or collection is None:
            continue
        CollectionItem.objects.create(
            collection=collection,
            product=product,
            sort_order=sort_order,
            is_primary=is_primary,
        )

    # Preserve historical tickets, but hide legacy stations that no longer match routing.
    KDSInstance.objects.filter(ref__in=["paes", "folhados", "salgados"]).update(is_active=False)
    for kds_ref, collection_refs in KDS_ROUTES.items():
        kds = KDSInstance.objects.filter(ref=kds_ref).first()
        if not kds:
            continue
        kds.collections.set(Collection.objects.filter(ref__in=collection_refs))


class Migration(migrations.Migration):
    dependencies = [
        ("offerman", "0005_listing_projection_metadata"),
        ("backstage", "0010_kdsticket_cancelled_at_and_status"),
    ]

    operations = [
        migrations.RunPython(sync_collection_taxonomy, migrations.RunPython.noop),
    ]
