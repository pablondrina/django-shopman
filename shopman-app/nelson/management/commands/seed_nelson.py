"""
Seed de producao — Nelson Boulangerie.

Popula catalogo (offering), estoque (stocking), receitas (crafting),
clientes (attending), canais (ordering) e pedidos com dados da Nelson.

Uso:
    python manage.py seed_nelson          # seed normal
    python manage.py seed_nelson --flush  # apaga tudo e recria
"""
from __future__ import annotations

import os
import random
import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

# ── Offering (catalogo) ──────────────────────────────────────────────
from shopman.offering.models import (
    Collection,
    CollectionItem,
    Listing,
    ListingItem,
    Product,
    ProductComponent,
)

# ── Stocking (estoque) ──────────────────────────────────────────────
from shopman.stocking import stock
from shopman.stocking.models import Position, PositionKind, StockAlert

# ── Crafting (producao) ─────────────────────────────────────────────
from shopman.crafting.models import Recipe, RecipeItem, WorkOrder

# ── Attending (clientes) ─────────────────────────────────────────────
from shopman.attending.models import ContactPoint, Customer, CustomerGroup

# ── Ordering (canais e pedidos) ──────────────────────────────────────
from shopman.ordering.models import (
    Channel,
    Directive,
    Order,
    OrderEvent,
    OrderItem,
    Session,
)


class Command(BaseCommand):
    help = "Popula o banco com dados de producao da Nelson Boulangerie"

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Apaga todos os dados antes de popular",
        )

    def handle(self, *args, **options):
        if options["flush"]:
            self._flush()

        self.stdout.write(self.style.MIGRATE_HEADING("\n🥐 Populando Nelson Boulangerie...\n"))

        self._create_superuser()
        products = self._seed_catalog()
        positions = self._seed_positions()
        self._seed_stock(products, positions)
        self._seed_recipes()
        customers = self._seed_customers()
        channels = self._seed_channels()
        self._seed_orders(products, customers, channels)
        self._seed_sessions(channels)
        self._seed_stock_alerts(products, positions)

        self.stdout.write(self.style.SUCCESS("\n✅ Seed Nelson completo!\n"))

    # ────────────────────────────────────────────────────────────────
    # Superuser
    # ────────────────────────────────────────────────────────────────

    def _create_superuser(self):
        password = os.environ.get("ADMIN_PASSWORD", "admin")
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser(
                username="admin",
                email="admin@nelson.com.br",
                password=password,
            )
            self.stdout.write("  ✅ Superuser 'admin' criado")
        else:
            self.stdout.write("  ⏭️  Superuser 'admin' ja existe")

    # ────────────────────────────────────────────────────────────────
    # Flush
    # ────────────────────────────────────────────────────────────────

    def _flush(self):
        self.stdout.write("  Limpando dados anteriores...")

        # Ordering
        for model in [Directive, OrderEvent, OrderItem, Order, Session, Channel]:
            model.objects.all().delete()

        # Offering
        for model in [ListingItem, Listing, CollectionItem, Collection, ProductComponent, Product]:
            model.objects.all().delete()

        # Stocking
        from shopman.stocking.models import Move, Quant, Hold

        for model in [StockAlert, Hold, Move, Quant, Position]:
            model.objects.all().delete()

        # Crafting
        from shopman.crafting.models import WorkOrderEvent

        for model in [WorkOrderEvent, WorkOrder, RecipeItem, Recipe]:
            model.objects.all().delete()

        # Attending
        for model in [ContactPoint, Customer, CustomerGroup]:
            model.objects.all().delete()

        self.stdout.write("  ✅ Dados limpos")

    # ────────────────────────────────────────────────────────────────
    # Catalogo (Offering)
    # ────────────────────────────────────────────────────────────────

    def _seed_catalog(self):
        self.stdout.write("  📦 Catalogo...")

        products_data = [
            # (sku, name, short_description, base_price_q, unit, shelf_life_days, is_available, image_url)
            ("PAO-FRANCES", "Pao Frances Artesanal", "Fermentacao natural, crosta crocante", 150, "un", 0, True, "https://images.unsplash.com/photo-1549931319-a545dcf3bc73?w=400&q=80"),
            ("BAGUETE", "Baguete Tradicional", "Receita francesa classica, 60cm", 850, "un", 0, True, "https://images.unsplash.com/photo-1568471173242-461f0a730452?w=400&q=80"),
            ("CROISSANT", "Croissant Manteiga", "Folhado com manteiga francesa, 72h de fermentacao", 890, "un", 1, True, "https://images.unsplash.com/photo-1623334044303-241021148842?w=400&q=80"),
            ("PAIN-CHOCOLAT", "Pain au Chocolat", "Folhado com chocolate belga 70%", 1090, "un", 1, True, "https://images.unsplash.com/photo-1530610476181-d83430b64dcd?w=400&q=80"),
            ("BRIOCHE", "Brioche Nanterre", "Brioche classico, massa amanteigada", 990, "un", 2, True, "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=400&q=80"),
            ("FOCACCIA", "Focaccia Alecrim", "Azeite extra-virgem e alecrim fresco", 1490, "un", 0, True, "https://images.unsplash.com/photo-1586444248902-2f64eddc13df?w=400&q=80"),
            ("CIABATTA", "Ciabatta Italiana", "Massa hidratada, miolo aerado", 750, "un", 0, True, "https://images.unsplash.com/photo-1608198093002-ad4e005484ec?w=400&q=80"),
            ("SOURDOUGH", "Sourdough Integral", "Levain natural, farinha integral organica", 1690, "un", 3, True, "https://images.unsplash.com/photo-1589367920969-ab8e050bbb04?w=400&q=80"),
            ("DANISH", "Danish de Frutas", "Folhado com creme e frutas da estacao", 1290, "un", 1, True, "https://images.unsplash.com/photo-1509365390695-33aee754301f?w=400&q=80"),
            ("CAFE-ESPRESSO", "Cafe Espresso", "Blend especial, torra media", 690, "un", 0, True, "https://images.unsplash.com/photo-1510707577719-ae7c14805e3a?w=400&q=80"),
            ("CAFE-LATTE", "Cafe Latte", "Espresso com leite vaporizado", 990, "un", 0, True, "https://images.unsplash.com/photo-1534778101976-62847782c213?w=400&q=80"),
            ("SUCO-LARANJA", "Suco de Laranja Natural", "Laranja pera, sem acucar", 890, "un", 0, True, "https://images.unsplash.com/photo-1621506289937-a8e4df240d0b?w=400&q=80"),
        ]

        products = {}
        for sku, name, desc, price_q, unit, shelf_life, available, image in products_data:
            p, _ = Product.objects.update_or_create(
                sku=sku,
                defaults={
                    "name": name,
                    "short_description": desc,
                    "base_price_q": price_q,
                    "unit": unit,
                    "shelf_life_days": shelf_life,
                    "is_published": True,
                    "is_available": available,
                    "image_url": image,
                },
            )
            products[sku] = p

        # Bundle: Combo Cafe da Manha
        combo, _ = Product.objects.update_or_create(
            sku="COMBO-MANHA",
            defaults={
                "name": "Combo Cafe da Manha",
                "short_description": "Croissant + Cafe Espresso (economia de R$ 2,80)",
                "base_price_q": 1290,
                "unit": "un",
                "is_published": True,
                "is_available": True,
                "image_url": "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=400&q=80",
            },
        )
        products["COMBO-MANHA"] = combo

        # Bundle components
        ProductComponent.objects.filter(parent=combo).delete()
        ProductComponent.objects.create(parent=combo, component=products["CROISSANT"], qty=Decimal("1"))
        ProductComponent.objects.create(parent=combo, component=products["CAFE-ESPRESSO"], qty=Decimal("1"))

        # Collections
        col_paes, _ = Collection.objects.update_or_create(
            slug="paes-artesanais",
            defaults={"name": "Paes Artesanais", "is_active": True, "sort_order": 1},
        )
        col_confeitaria, _ = Collection.objects.update_or_create(
            slug="confeitaria",
            defaults={"name": "Confeitaria & Folhados", "is_active": True, "sort_order": 2},
        )
        col_bebidas, _ = Collection.objects.update_or_create(
            slug="bebidas",
            defaults={"name": "Bebidas", "is_active": True, "sort_order": 3},
        )
        col_combos, _ = Collection.objects.update_or_create(
            slug="combos",
            defaults={"name": "Combos", "is_active": True, "sort_order": 4},
        )

        # Collection items
        CollectionItem.objects.filter(collection__in=[col_paes, col_confeitaria, col_bebidas, col_combos]).delete()

        paes_skus = ["PAO-FRANCES", "BAGUETE", "FOCACCIA", "CIABATTA", "SOURDOUGH"]
        for i, sku in enumerate(paes_skus):
            CollectionItem.objects.create(collection=col_paes, product=products[sku], sort_order=i)

        confeitaria_skus = ["CROISSANT", "PAIN-CHOCOLAT", "BRIOCHE", "DANISH"]
        for i, sku in enumerate(confeitaria_skus):
            CollectionItem.objects.create(collection=col_confeitaria, product=products[sku], sort_order=i)

        bebidas_skus = ["CAFE-ESPRESSO", "CAFE-LATTE", "SUCO-LARANJA"]
        for i, sku in enumerate(bebidas_skus):
            CollectionItem.objects.create(collection=col_bebidas, product=products[sku], sort_order=i)

        CollectionItem.objects.create(collection=col_combos, product=products["COMBO-MANHA"], sort_order=0)

        # Listings
        balcao, _ = Listing.objects.update_or_create(
            code="balcao",
            defaults={"name": "Balcao", "is_active": True, "priority": 10},
        )
        delivery, _ = Listing.objects.update_or_create(
            code="delivery",
            defaults={"name": "Delivery Proprio", "is_active": True, "priority": 5},
        )
        ifood, _ = Listing.objects.update_or_create(
            code="ifood",
            defaults={"name": "iFood", "is_active": True, "priority": 3},
        )
        web, _ = Listing.objects.update_or_create(
            code="web",
            defaults={"name": "E-commerce", "is_active": True, "priority": 7},
        )

        # Listing items (all products in all listings)
        markup_map = {"balcao": 0, "delivery": 0, "ifood": 30, "web": 0}
        for listing_obj in [balcao, delivery, ifood, web]:
            ListingItem.objects.filter(listing=listing_obj).delete()
            markup = Decimal(markup_map[listing_obj.code]) / 100
            for sku, product in products.items():
                price_q = int(product.base_price_q * (1 + markup))
                ListingItem.objects.create(
                    listing=listing_obj,
                    product=product,
                    price_q=price_q,
                    is_published=True,
                    is_available=product.is_available,
                )

        self.stdout.write(f"  ✅ {len(products)} produtos, 4 colecoes, 4 listagens")
        return products

    # ────────────────────────────────────────────────────────────────
    # Estoque (Stocking)
    # ────────────────────────────────────────────────────────────────

    def _seed_positions(self):
        self.stdout.write("  📍 Posicoes de estoque...")

        positions = {}
        for ref, name, kind, saleable in [
            ("deposito", "Deposito", PositionKind.PHYSICAL, False),
            ("vitrine", "Vitrine / Exposicao", PositionKind.PHYSICAL, True),
            ("producao", "Area de Producao", PositionKind.PHYSICAL, False),
        ]:
            p, _ = Position.objects.update_or_create(
                ref=ref,
                defaults={
                    "name": name,
                    "kind": kind,
                    "is_saleable": saleable,
                },
            )
            positions[ref] = p

        self.stdout.write("  ✅ 3 posicoes")
        return positions

    def _seed_stock(self, products, positions):
        self.stdout.write("  📊 Estoque inicial...")

        vitrine = positions["vitrine"]
        stock_data = {
            "PAO-FRANCES": 120,
            "BAGUETE": 25,
            "CROISSANT": 40,
            "PAIN-CHOCOLAT": 30,
            "BRIOCHE": 20,
            "FOCACCIA": 15,
            "CIABATTA": 30,
            "SOURDOUGH": 12,
            "DANISH": 24,
        }

        for sku, qty in stock_data.items():
            if sku in products:
                stock.receive(
                    quantity=Decimal(str(qty)),
                    sku=sku,
                    position=vitrine,
                    reason=f"Estoque inicial seed Nelson: {sku}",
                )

        self.stdout.write(f"  ✅ Estoque para {len(stock_data)} produtos")

    # ────────────────────────────────────────────────────────────────
    # Receitas (Crafting)
    # ────────────────────────────────────────────────────────────────

    def _seed_recipes(self):
        self.stdout.write("  📋 Receitas...")

        recipes_data = [
            {
                "code": "pao-frances",
                "name": "Pao Frances Artesanal",
                "output_ref": "PAO-FRANCES",
                "batch_size": Decimal("50"),
                "items": [
                    ("INS-FARINHA-T55", Decimal("5.000")),
                    ("INS-AGUA", Decimal("3.250")),
                    ("INS-FERMENTO-NAT", Decimal("1.500")),
                    ("INS-SAL", Decimal("0.100")),
                ],
            },
            {
                "code": "baguete",
                "name": "Baguete Tradicional",
                "output_ref": "BAGUETE",
                "batch_size": Decimal("20"),
                "items": [
                    ("INS-FARINHA-T65", Decimal("4.000")),
                    ("INS-AGUA", Decimal("2.800")),
                    ("INS-FERMENTO-NAT", Decimal("1.200")),
                    ("INS-SAL", Decimal("0.080")),
                    ("INS-MALTE", Decimal("0.020")),
                ],
            },
            {
                "code": "croissant",
                "name": "Croissant Manteiga",
                "output_ref": "CROISSANT",
                "batch_size": Decimal("48"),
                "items": [
                    ("INS-FARINHA-T45", Decimal("3.000")),
                    ("INS-MANTEIGA-FR", Decimal("1.500")),
                    ("INS-LEITE", Decimal("0.750")),
                    ("INS-ACUCAR", Decimal("0.300")),
                    ("INS-FERMENTO-BIO", Decimal("0.120")),
                    ("INS-SAL", Decimal("0.060")),
                    ("INS-OVOS", Decimal("0.200")),
                ],
            },
            {
                "code": "pain-chocolat",
                "name": "Pain au Chocolat",
                "output_ref": "PAIN-CHOCOLAT",
                "batch_size": Decimal("36"),
                "items": [
                    ("INS-FARINHA-T45", Decimal("2.500")),
                    ("INS-MANTEIGA-FR", Decimal("1.200")),
                    ("INS-CHOCOLATE-70", Decimal("0.720")),
                    ("INS-LEITE", Decimal("0.600")),
                    ("INS-ACUCAR", Decimal("0.250")),
                    ("INS-FERMENTO-BIO", Decimal("0.100")),
                    ("INS-SAL", Decimal("0.050")),
                    ("INS-OVOS", Decimal("0.160")),
                ],
            },
            {
                "code": "focaccia",
                "name": "Focaccia Alecrim",
                "output_ref": "FOCACCIA",
                "batch_size": Decimal("10"),
                "items": [
                    ("INS-FARINHA-T55", Decimal("2.000")),
                    ("INS-AGUA", Decimal("1.500")),
                    ("INS-AZEITE", Decimal("0.200")),
                    ("INS-FERMENTO-NAT", Decimal("0.600")),
                    ("INS-SAL", Decimal("0.040")),
                    ("INS-ALECRIM", Decimal("0.030")),
                ],
            },
            {
                "code": "sourdough",
                "name": "Sourdough Integral",
                "output_ref": "SOURDOUGH",
                "batch_size": Decimal("8"),
                "items": [
                    ("INS-FARINHA-INT", Decimal("2.400")),
                    ("INS-FARINHA-T65", Decimal("1.600")),
                    ("INS-AGUA", Decimal("3.000")),
                    ("INS-FERMENTO-NAT", Decimal("1.200")),
                    ("INS-SAL", Decimal("0.080")),
                ],
            },
        ]

        for rd in recipes_data:
            recipe, _ = Recipe.objects.update_or_create(
                code=rd["code"],
                defaults={
                    "name": rd["name"],
                    "output_ref": rd["output_ref"],
                    "batch_size": rd["batch_size"],
                },
            )
            RecipeItem.objects.filter(recipe=recipe).delete()
            for input_ref, qty in rd["items"]:
                RecipeItem.objects.create(
                    recipe=recipe,
                    input_ref=input_ref,
                    quantity=qty,
                )

        # Work orders
        today = date.today()
        tomorrow = today + timedelta(days=1)

        recipe_pao = Recipe.objects.get(code="pao-frances")
        recipe_croissant = Recipe.objects.get(code="croissant")
        recipe_baguete = Recipe.objects.get(code="baguete")
        recipe_sourdough = Recipe.objects.get(code="sourdough")

        # Today: 2 done + 1 open
        for recipe, qty, status in [
            (recipe_pao, Decimal("100"), WorkOrder.Status.DONE),
            (recipe_croissant, Decimal("48"), WorkOrder.Status.DONE),
            (recipe_baguete, Decimal("20"), WorkOrder.Status.OPEN),
        ]:
            WorkOrder.objects.get_or_create(
                recipe=recipe,
                scheduled_date=today,
                defaults={
                    "output_ref": recipe.output_ref,
                    "quantity": qty,
                    "produced": qty if status == WorkOrder.Status.DONE else None,
                    "status": status,
                    "started_at": timezone.now() if status != WorkOrder.Status.OPEN else None,
                    "finished_at": timezone.now() if status == WorkOrder.Status.DONE else None,
                },
            )

        # Tomorrow: 4 open
        for recipe, qty in [
            (recipe_pao, Decimal("150")),
            (recipe_croissant, Decimal("96")),
            (recipe_baguete, Decimal("40")),
            (recipe_sourdough, Decimal("16")),
        ]:
            WorkOrder.objects.get_or_create(
                recipe=recipe,
                scheduled_date=tomorrow,
                defaults={
                    "output_ref": recipe.output_ref,
                    "quantity": qty,
                    "status": WorkOrder.Status.OPEN,
                },
            )

        self.stdout.write(f"  ✅ {len(recipes_data)} receitas, 7 ordens de producao")

    # ────────────────────────────────────────────────────────────────
    # Clientes (Attending)
    # ────────────────────────────────────────────────────────────────

    def _seed_customers(self):
        self.stdout.write("  👥 Clientes...")

        # Groups
        varejo, _ = CustomerGroup.objects.update_or_create(
            ref="varejo",
            defaults={"name": "Varejo"},
        )
        atacado, _ = CustomerGroup.objects.update_or_create(
            ref="atacado",
            defaults={"name": "Atacado"},
        )
        staff_group, _ = CustomerGroup.objects.update_or_create(
            ref="staff",
            defaults={"name": "Funcionarios"},
        )

        customers_data = [
            ("CLI-001", "Maria", "Santos", "individual", varejo, "+5543991111111"),
            ("CLI-002", "Restaurante", "Sabor da Terra", "business", atacado, "+5543992222222"),
            ("CLI-003", "Joao", "Oliveira", "individual", varejo, "+5543993333333"),
            ("CLI-004", "Cafe", "Parisiense", "business", atacado, "+5543994444444"),
            ("CLI-005", "Ana", "Ferreira", "individual", varejo, "+5543995555555"),
            ("CLI-006", "Carlos", "Silva", "individual", staff_group, "+5543996666666"),
            ("CLI-007", "Padaria", "do Bairro", "business", atacado, "+5543997777777"),
        ]

        customers = {}
        for ref, first, last, ctype, group, phone in customers_data:
            c, _ = Customer.objects.update_or_create(
                ref=ref,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "customer_type": ctype,
                    "group": group,
                    "phone": phone,
                },
            )
            ContactPoint.objects.update_or_create(
                customer=c,
                type="whatsapp",
                value_normalized=phone,
                defaults={
                    "is_primary": True,
                    "value_display": phone,
                },
            )
            customers[ref] = c

        self.stdout.write(f"  ✅ {len(customers)} clientes, 3 grupos")
        return customers

    # ────────────────────────────────────────────────────────────────
    # Canais (Ordering)
    # ────────────────────────────────────────────────────────────────

    def _seed_channels(self):
        self.stdout.write("  📡 Canais...")

        channels = {}
        channels_data = [
            ("balcao", "Balcao / PDV", "internal", "open",
             {"post_commit_directives": ["stock.hold", "notification.send"]}),
            ("delivery", "Delivery Proprio", "internal", "open",
             {"post_commit_directives": ["customer.ensure", "stock.hold", "notification.send"]}),
            ("ifood", "iFood", "external", "locked",
             {"post_commit_directives": ["notification.send"]}),
            ("whatsapp", "WhatsApp", "internal", "open",
             {"post_commit_directives": ["customer.ensure", "stock.hold", "notification.send"]}),
            ("web", "E-commerce", "internal", "open",
             {"post_commit_directives": ["customer.ensure", "stock.hold", "notification.send"]}),
        ]

        for ref, name, pricing, edit, config in channels_data:
            ch, _ = Channel.objects.update_or_create(
                ref=ref,
                defaults={
                    "name": name,
                    "pricing_policy": pricing,
                    "edit_policy": edit,
                    "is_active": True,
                    "config": config,
                },
            )
            channels[ref] = ch

        self.stdout.write(f"  ✅ {len(channels)} canais")
        return channels

    # ────────────────────────────────────────────────────────────────
    # Pedidos (Ordering)
    # ────────────────────────────────────────────────────────────────

    def _seed_orders(self, products, customers, channels):
        self.stdout.write("  🛒 Pedidos...")

        now = timezone.now()
        order_count = 0
        customer_list = list(customers.values())
        product_list = list(products.values())
        channel_list = [channels["balcao"], channels["delivery"], channels["whatsapp"]]

        for days_ago in range(7):
            day = now - timedelta(days=days_ago)
            num_orders = random.randint(8, 15) if days_ago < 2 else random.randint(5, 10)

            for _ in range(num_orders):
                channel = random.choice(channel_list)
                customer = random.choice(customer_list)
                hour = random.randint(6, 19)
                minute = random.randint(0, 59)
                order_time = day.replace(hour=hour, minute=minute, second=0, microsecond=0)

                # Determine status based on age
                if days_ago == 0:
                    status = random.choice(["new", "confirmed", "processing", "ready"])
                elif days_ago == 1:
                    status = random.choice(["completed", "completed", "completed", "completed"])
                else:
                    status = "completed"

                # Random items
                num_items = random.randint(1, 4)
                selected_products = random.sample(product_list, min(num_items, len(product_list)))

                items_data = []
                total_q = 0
                for prod in selected_products:
                    qty = random.randint(1, 5)
                    price_q = prod.base_price_q
                    line_total_q = price_q * qty
                    total_q += line_total_q
                    items_data.append({
                        "sku": prod.sku,
                        "name": prod.name,
                        "qty": qty,
                        "unit_price_q": price_q,
                        "line_total_q": line_total_q,
                    })

                ref = f"NB-{uuid.uuid4().hex[:8].upper()}"

                # Get customer phone from contact points
                cp = customer.contact_points.filter(type="whatsapp").first()
                handle_ref = cp.value_normalized if cp else ""

                order = Order.objects.create(
                    ref=ref,
                    channel=channel,
                    status=status,
                    total_q=total_q,
                    handle_type="phone",
                    handle_ref=handle_ref,
                    created_at=order_time,
                )

                for idx, item in enumerate(items_data):
                    OrderItem.objects.create(
                        order=order,
                        line_id=f"L-{uuid.uuid4().hex[:8]}",
                        sku=item["sku"],
                        name=item["name"],
                        qty=Decimal(str(item["qty"])),
                        unit_price_q=item["unit_price_q"],
                        line_total_q=item["line_total_q"],
                    )

                # Create events
                OrderEvent.objects.create(
                    order=order,
                    type="status_change",
                    seq=0,
                    payload={"new_status": "new"},
                    created_at=order_time,
                )

                if status in ("confirmed", "processing", "ready", "completed"):
                    OrderEvent.objects.create(
                        order=order,
                        type="status_change",
                        seq=1,
                        payload={"new_status": "confirmed"},
                        created_at=order_time + timedelta(minutes=2),
                    )

                if status in ("processing", "ready", "completed"):
                    OrderEvent.objects.create(
                        order=order,
                        type="status_change",
                        seq=2,
                        payload={"new_status": "processing"},
                        created_at=order_time + timedelta(minutes=5),
                    )

                if status == "completed":
                    OrderEvent.objects.create(
                        order=order,
                        type="status_change",
                        seq=3,
                        payload={"new_status": "completed"},
                        created_at=order_time + timedelta(minutes=15),
                    )

                order_count += 1

        self.stdout.write(f"  ✅ {order_count} pedidos (7 dias)")

    # ────────────────────────────────────────────────────────────────
    # Sessoes abertas (Ordering)
    # ────────────────────────────────────────────────────────────────

    def _seed_sessions(self, channels):
        self.stdout.write("  📝 Sessoes abertas...")

        from shopman.ordering.ids import generate_session_key

        for channel_ref, items in [
            ("balcao", [
                {"line_id": uuid.uuid4().hex[:8], "sku": "CROISSANT", "name": "Croissant Manteiga", "qty": 2, "unit_price_q": 890, "line_total_q": 1780},
                {"line_id": uuid.uuid4().hex[:8], "sku": "CAFE-ESPRESSO", "name": "Cafe Espresso", "qty": 1, "unit_price_q": 690, "line_total_q": 690},
            ]),
            ("delivery", [
                {"line_id": uuid.uuid4().hex[:8], "sku": "PAO-FRANCES", "name": "Pao Frances Artesanal", "qty": 10, "unit_price_q": 150, "line_total_q": 1500},
                {"line_id": uuid.uuid4().hex[:8], "sku": "BAGUETE", "name": "Baguete Tradicional", "qty": 3, "unit_price_q": 850, "line_total_q": 2550},
            ]),
            ("whatsapp", [
                {"line_id": uuid.uuid4().hex[:8], "sku": "PAO-FRANCES", "name": "Pao Frances Artesanal", "qty": 100, "unit_price_q": 150, "line_total_q": 15000},
                {"line_id": uuid.uuid4().hex[:8], "sku": "CROISSANT", "name": "Croissant Manteiga", "qty": 50, "unit_price_q": 890, "line_total_q": 44500},
            ]),
        ]:
            ch = channels[channel_ref]
            Session.objects.create(
                session_key=generate_session_key(),
                channel=ch,
                state="open",
                pricing_policy=ch.pricing_policy,
                edit_policy=ch.edit_policy,
                items=items,
            )

        self.stdout.write("  ✅ 3 sessoes abertas")

    # ────────────────────────────────────────────────────────────────
    # Alertas de estoque (Stocking)
    # ────────────────────────────────────────────────────────────────

    def _seed_stock_alerts(self, products, positions):
        self.stdout.write("  🔔 Alertas de estoque...")

        vitrine = positions["vitrine"]
        alerts_data = [
            ("PAO-FRANCES", 50),
            ("BAGUETE", 10),
            ("CROISSANT", 15),
            ("PAIN-CHOCOLAT", 12),
            ("BRIOCHE", 10),
            ("FOCACCIA", 8),
            ("SOURDOUGH", 6),
        ]

        for sku, min_qty in alerts_data:
            if sku in products:
                StockAlert.objects.update_or_create(
                    sku=sku,
                    position=vitrine,
                    defaults={
                        "min_quantity": Decimal(str(min_qty)),
                    },
                )

        self.stdout.write(f"  ✅ {len(alerts_data)} alertas configurados")
