"""
Seed de producao — Nelson Boulangerie.

Popula loja (shop), catalogo (offering), estoque (stocking), receitas (crafting),
clientes (customers), canais (ordering) e pedidos com dados da Nelson.

Uso:
    python manage.py seed          # seed normal
    python manage.py seed --flush  # apaga tudo e recria
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

# ── Crafting (producao) ─────────────────────────────────────────────
from shopman.crafting.models import Recipe, RecipeItem, WorkOrder

# ── Customers (clientes) ─────────────────────────────────────────────
from shopman.customers.models import ContactPoint, Customer, CustomerAddress, CustomerGroup

# ── Shopman (orchestrator) ────────────────────────────────────────────
from shopman.models import Coupon, KDSInstance, Promotion, RuleConfig, Shop

# ── Offering (catalogo) ──────────────────────────────────────────────
from shopman.offering.models import (
    Collection,
    CollectionItem,
    Listing,
    ListingItem,
    Product,
    ProductComponent,
)

# ── Ordering (canais e pedidos) ──────────────────────────────────────
from shopman.ordering.models import (
    Channel,
    Directive,
    Fulfillment,
    FulfillmentItem,
    Order,
    OrderEvent,
    OrderItem,
    Session,
)

# ── Payments ─────────────────────────────────────────────────────────
from shopman.payments.models import PaymentIntent, PaymentTransaction

# ── Stocking (estoque) ──────────────────────────────────────────────
from shopman.stocking import stock
from shopman.stocking.models import Position, PositionKind, StockAlert


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
        self._seed_shop()
        self._seed_delivery_zones()
        products = self._seed_catalog()
        positions = self._seed_positions()
        self._seed_stock(products, positions)
        self._seed_recipes()
        customers = self._seed_customers()
        self._seed_addresses(customers)
        channels = self._seed_channels()
        self._seed_kds()
        self._seed_orders(products, customers, channels)
        self._seed_sessions(channels)
        self._seed_stock_alerts(products, positions)
        self._seed_promotions()
        self._seed_payments()
        self._seed_fulfillments()
        self._seed_directives()
        self._seed_loyalty(customers)
        self._seed_notification_templates()
        self._seed_rule_configs()

        self.stdout.write(self.style.SUCCESS("\n✅ Seed Nelson completo!\n"))

    # ────────────────────────────────────────────────────────────────
    # Shop
    # ────────────────────────────────────────────────────────────────

    def _seed_shop(self):
        _, created = Shop.objects.update_or_create(
            pk=1,
            defaults={
                "name": "Nelson Boulangerie",
                "legal_name": "N.H.K. Panificadora Ltda.",
                "brand_name": "Nelson Boulangerie",
                "short_name": "Nelson",
                "tagline": "Padaria Artesanal",
                "description": "Segue rigorosamente as normas da panificação artesanal francesa.",
                "primary_color": "#C5A55A",
                "secondary_color": "#2C1810",
                "accent_color": "#8B4513",
                "neutral_color": "#F5E6D3",
                "neutral_dark_color": "#1A0F0A",
                "formatted_address": "Av. Madre Leônia Milito, 446 - Bela Suíça, Londrina - PR, 86050-270",
                "route": "Av. Madre Leônia Milito",
                "street_number": "446",
                "neighborhood": "Bela Suíça",
                "city": "Londrina",
                "state_code": "PR",
                "postal_code": "86050-270",
                "country": "Brasil",
                "country_code": "BR",
                "latitude": -23.3045,
                "longitude": -51.1628,
                "phone": "554333231997",
                "email": "contato@nelsonboulangerie.com.br",
                "default_ddd": "43",
                "social_links": [
                    "https://wa.me/554333231997",
                    "https://instagram.com/nelsonboulangerie",
                    "https://www.facebook.com/nelsonboulangerie",
                    "http://www.nelsonboulangerie.com.br",
                ],
                "opening_hours": {
                    "monday":    {"open": "09:00", "close": "18:00"},
                    "tuesday":   {"open": "09:00", "close": "18:00"},
                    "wednesday": {"open": "09:00", "close": "18:00"},
                    "thursday":  {"open": "09:00", "close": "18:00"},
                    "friday":    {"open": "09:00", "close": "18:00"},
                    "saturday":  {"open": "09:00", "close": "18:00"},
                },
                "defaults": {
                    "notifications": {"backend": "console"},
                },
            },
        )
        self.stdout.write("  ✅ Shop criado" if created else "  ✅ Shop atualizado")

    # ────────────────────────────────────────────────────────────────
    # Delivery Zones
    # ────────────────────────────────────────────────────────────────

    def _seed_delivery_zones(self):
        from shopman.models import DeliveryZone

        shop = Shop.objects.get(pk=1)
        # Londrina — CEP prefixes: 860xx e 861xx (regiao metropolitana)
        # https://www.correios.com.br/ — Londrina PR: 86000-000 a 86099-999, 86100-000 a 86199-999
        zones = [
            {
                "name": "Londrina Centro e Norte",
                "zone_type": DeliveryZone.ZONE_TYPE_CEP_PREFIX,
                "match_value": "860",
                "fee_q": 600,   # R$ 6,00
                "sort_order": 10,
            },
            {
                "name": "Londrina Sul e Leste",
                "zone_type": DeliveryZone.ZONE_TYPE_CEP_PREFIX,
                "match_value": "861",
                "fee_q": 800,   # R$ 8,00
                "sort_order": 20,
            },
            {
                "name": "Bairro Bela Suíça (grátis)",
                "zone_type": DeliveryZone.ZONE_TYPE_NEIGHBORHOOD,
                "match_value": "Bela Suíça",
                "fee_q": 0,     # entrega grátis
                "sort_order": 5,
            },
            {
                "name": "Cambé e Ibiporã",
                "zone_type": DeliveryZone.ZONE_TYPE_CEP_PREFIX,
                "match_value": "862",
                "fee_q": 1200,  # R$ 12,00
                "sort_order": 30,
            },
        ]
        created_count = 0
        for data in zones:
            _, created = DeliveryZone.objects.update_or_create(
                shop=shop,
                name=data["name"],
                defaults={k: v for k, v in data.items() if k != "name"},
            )
            if created:
                created_count += 1
        self.stdout.write(
            f"  ✅ Zonas de entrega: {len(zones)} configuradas ({created_count} novas)"
        )

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

        # Payments
        for model in [PaymentTransaction, PaymentIntent]:
            model.objects.all().delete()

        # Ordering
        for model in [FulfillmentItem, Fulfillment, Directive, OrderEvent, OrderItem, Order, Session, Channel]:
            model.objects.all().delete()

        # Offering
        for model in [ListingItem, Listing, CollectionItem, Collection, ProductComponent, Product]:
            model.objects.all().delete()

        # Stocking
        from shopman.stocking.models import Hold, Move, Quant

        for model in [StockAlert, Hold, Move, Quant, Position]:
            model.objects.all().delete()

        # Crafting
        from shopman.crafting.models import WorkOrderEvent

        for model in [WorkOrderEvent, WorkOrder, RecipeItem, Recipe]:
            model.objects.all().delete()

        # Customers
        for model in [CustomerAddress, ContactPoint, Customer, CustomerGroup]:
            model.objects.all().delete()

        # KDS
        from shopman.models import KDSTicket

        KDSTicket.objects.all().delete()
        KDSInstance.objects.all().delete()

        # Shop
        Coupon.objects.all().delete()
        Promotion.objects.all().delete()
        Shop.objects.all().delete()

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
                "short_description": "Croissant + Cafe Espresso (economia de R$ 2,90)",
                "base_price_q": 1290,
                "unit": "un",
                "is_published": True,
                "is_available": True,
                "image_url": "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=400&q=80",
            },
        )
        products["COMBO-MANHA"] = combo

        # D-1 eligible: breads that can be sold next day at discount
        d1_skus = ["PAO-FRANCES", "BAGUETE", "FOCACCIA", "CIABATTA"]
        for sku in d1_skus:
            p = products[sku]
            p.metadata["allows_next_day_sale"] = True
            p.save(update_fields=["metadata"])

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

        # Collection items (first collection per product = is_primary)
        CollectionItem.objects.filter(collection__in=[col_paes, col_confeitaria, col_bebidas, col_combos]).delete()

        paes_skus = ["PAO-FRANCES", "BAGUETE", "FOCACCIA", "CIABATTA", "SOURDOUGH"]
        for i, sku in enumerate(paes_skus):
            CollectionItem.objects.create(
                collection=col_paes, product=products[sku], sort_order=i, is_primary=True,
            )

        confeitaria_skus = ["CROISSANT", "PAIN-CHOCOLAT", "BRIOCHE", "DANISH"]
        for i, sku in enumerate(confeitaria_skus):
            CollectionItem.objects.create(
                collection=col_confeitaria, product=products[sku], sort_order=i, is_primary=True,
            )

        bebidas_skus = ["CAFE-ESPRESSO", "CAFE-LATTE", "SUCO-LARANJA"]
        for i, sku in enumerate(bebidas_skus):
            CollectionItem.objects.create(
                collection=col_bebidas, product=products[sku], sort_order=i, is_primary=True,
            )

        CollectionItem.objects.create(
            collection=col_combos, product=products["COMBO-MANHA"], sort_order=0, is_primary=True,
        )

        # Listings
        balcao, _ = Listing.objects.update_or_create(
            ref="balcao",
            defaults={"name": "Balcao", "is_active": True, "priority": 10},
        )
        delivery, _ = Listing.objects.update_or_create(
            ref="delivery",
            defaults={"name": "Delivery Proprio", "is_active": True, "priority": 5},
        )
        ifood, _ = Listing.objects.update_or_create(
            ref="ifood",
            defaults={"name": "iFood", "is_active": True, "priority": 3},
        )
        web, _ = Listing.objects.update_or_create(
            ref="web",
            defaults={"name": "E-commerce", "is_active": True, "priority": 7},
        )

        # Listing items (all products in all listings)
        # iFood uses pricing_policy="external" (marketplace defines prices),
        # so its listing prices are reference-only. No markup applied.
        markup_map = {"balcao": 0, "delivery": 0, "ifood": 0, "web": 0}
        for listing_obj in [balcao, delivery, ifood, web]:
            ListingItem.objects.filter(listing=listing_obj).delete()
            markup = Decimal(markup_map[listing_obj.ref]) / 100
            for _sku, product in products.items():
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

        # Ref "ontem": sobras D-1 apos transferencia manual (fim do dia). Estoque com lote D-1
        # deve ficar aqui — canais remotos usam stock.allowed_positions sem "ontem", entao vitrine
        # API e reservas online ignoram esse saldo; balcao/PDV (allowed_positions omitido) ve tudo.
        positions = {}
        for ref, name, kind, saleable in [
            ("deposito", "Deposito", PositionKind.PHYSICAL, False),
            ("vitrine", "Vitrine / Exposicao", PositionKind.PHYSICAL, True),
            ("producao", "Area de Producao", PositionKind.PHYSICAL, False),
            ("ontem", "Vitrine D-1 (ontem)", PositionKind.PHYSICAL, True),
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

        self.stdout.write("  ✅ 4 posicoes")
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

        # Work orders — use CraftService to exercise the full signal chain
        # (production_changed → planned quants → inventory protocol)
        from shopman.crafting.service import CraftService as craft

        today = date.today()
        tomorrow = today + timedelta(days=1)

        recipe_pao = Recipe.objects.get(code="pao-frances")
        recipe_croissant = Recipe.objects.get(code="croissant")
        recipe_baguete = Recipe.objects.get(code="baguete")
        recipe_sourdough = Recipe.objects.get(code="sourdough")

        wo_count = 0

        # Today: 2 closed (via craft.plan + craft.close) + 1 open
        for recipe, qty, should_close in [
            (recipe_pao, Decimal("100"), True),
            (recipe_croissant, Decimal("48"), True),
            (recipe_baguete, Decimal("20"), False),
        ]:
            existing = WorkOrder.objects.filter(
                recipe=recipe, scheduled_date=today,
            ).first()
            if existing:
                wo_count += 1
                continue

            wo = craft.plan(recipe, quantity=qty, date=today)
            if should_close:
                produced = int(qty * Decimal("0.95"))
                craft.close(wo, produced=produced, actor="seed")
            wo_count += 1

        # Tomorrow: 4 open (via craft.plan → creates planned quants)
        for recipe, qty in [
            (recipe_pao, Decimal("150")),
            (recipe_croissant, Decimal("96")),
            (recipe_baguete, Decimal("40")),
            (recipe_sourdough, Decimal("16")),
        ]:
            existing = WorkOrder.objects.filter(
                recipe=recipe, scheduled_date=tomorrow,
            ).first()
            if existing:
                wo_count += 1
                continue

            craft.plan(recipe, quantity=qty, date=tomorrow)
            wo_count += 1

        self.stdout.write(f"  ✅ {len(recipes_data)} receitas, {wo_count} ordens de producao")

    # ────────────────────────────────────────────────────────────────
    # Clientes (Customers)
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
        # Flat channel configs (simplified — flows/services handle orchestration in R4+)
        _pos_config = {"flow": "pos", "confirmation_mode": "immediate", "payment": ["counter"]}
        # Remote: não reserva estoque na posição "ontem" (D-1 físico no balcão); balcão usa allowed_positions omitido (= todas).
        _remote_stock = {"allowed_positions": ["deposito", "vitrine", "producao"]}
        _remote_config = {
            "flow": "web",
            "confirmation_mode": "optimistic",
            "confirmation_timeout": 300,
            "payment": ["pix", "card"],
            "stock_hold_ttl": 30,
            "stock": _remote_stock,
        }
        _marketplace_config = {
            "flow": "marketplace",
            "confirmation_mode": "pessimistic",
            "confirmation_timeout": 300,
            "payment": ["external"],
            "stock": _remote_stock,
        }
        _whatsapp_config = {
            "flow": "whatsapp",
            "confirmation_mode": "optimistic",
            "confirmation_timeout": 300,
            "payment": ["pix", "card"],
            "notification_adapter": "manychat",
            "stock": _remote_stock,
        }
        channels_data = [
            # (ref, name, pricing, edit, listing_ref, config)
            ("balcao", "Balcao / PDV", "internal", "open", "balcao", _pos_config),
            ("delivery", "Delivery Proprio", "internal", "open", "delivery", _remote_config),
            ("ifood", "iFood", "external", "locked", "ifood", _marketplace_config),
            ("whatsapp", "WhatsApp", "internal", "open", "web", _whatsapp_config),
            ("web", "E-commerce", "internal", "open", "web", _remote_config),
        ]

        for ref, name, pricing, edit, listing_ref, config in channels_data:
            ch, _ = Channel.objects.update_or_create(
                ref=ref,
                defaults={
                    "name": name,
                    "pricing_policy": pricing,
                    "edit_policy": edit,
                    "listing_ref": listing_ref,
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

                for _idx, item in enumerate(items_data):
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

                # Dispatch KDS tickets for orders that passed through processing
                if status in ("processing", "ready"):
                    from shopman.kds_utils import dispatch_to_kds

                    tickets = dispatch_to_kds(order)
                    # Mark tickets done for orders already past processing
                    if status == "ready":
                        for ticket in tickets:
                            ticket.status = "done"
                            ticket.completed_at = order_time + timedelta(minutes=10)
                            ticket.save(update_fields=["status", "completed_at"])

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

    # ────────────────────────────────────────────────────────────────
    # Enderecos de clientes (Customers)
    # ────────────────────────────────────────────────────────────────

    def _seed_addresses(self, customers):
        self.stdout.write("  📍 Enderecos de clientes...")

        addresses_data = [
            ("CLI-001", [
                {"label": "home", "formatted_address": "Rua Belo Horizonte, 540, Apto 12 - Centro, Londrina - PR, 86020-060",
                 "route": "Rua Belo Horizonte", "street_number": "540", "complement": "Apto 12",
                 "neighborhood": "Centro", "city": "Londrina", "state": "Parana",
                 "state_code": "PR", "postal_code": "86020-060",
                 "latitude": Decimal("-23.3103000"), "longitude": Decimal("-51.1628000"), "is_default": True},
                {"label": "work", "formatted_address": "Av. Higienopolis, 350, Sala 201 - Higienopolis, Londrina - PR, 86020-080",
                 "route": "Av. Higienopolis", "street_number": "350", "complement": "Sala 201",
                 "neighborhood": "Higienopolis", "city": "Londrina", "state": "Parana",
                 "state_code": "PR", "postal_code": "86020-080",
                 "latitude": Decimal("-23.3065000"), "longitude": Decimal("-51.1650000"), "is_default": False},
            ]),
            ("CLI-002", [
                {"label": "work", "formatted_address": "Rua Marselha, 191 - Jardim Piza, Londrina - PR, 86041-140",
                 "route": "Rua Marselha", "street_number": "191", "complement": "",
                 "neighborhood": "Jardim Piza", "city": "Londrina", "state": "Parana",
                 "state_code": "PR", "postal_code": "86041-140",
                 "latitude": Decimal("-23.2960000"), "longitude": Decimal("-51.1520000"), "is_default": True},
            ]),
            ("CLI-003", [
                {"label": "home", "formatted_address": "Rua Paranagua, 800, Bl B Apto 5 - Centro, Londrina - PR, 86020-030",
                 "route": "Rua Paranagua", "street_number": "800", "complement": "Bl B Apto 5",
                 "neighborhood": "Centro", "city": "Londrina", "state": "Parana",
                 "state_code": "PR", "postal_code": "86020-030",
                 "latitude": Decimal("-23.3080000"), "longitude": Decimal("-51.1595000"), "is_default": True},
            ]),
            ("CLI-004", [
                {"label": "work", "formatted_address": "Av. Madre Leonia Milito, 900 - Bela Suica, Londrina - PR, 86050-270",
                 "route": "Av. Madre Leonia Milito", "street_number": "900", "complement": "",
                 "neighborhood": "Bela Suica", "city": "Londrina", "state": "Parana",
                 "state_code": "PR", "postal_code": "86050-270",
                 "latitude": Decimal("-23.3040000"), "longitude": Decimal("-51.1630000"), "is_default": True},
            ]),
            ("CLI-005", [
                {"label": "home", "formatted_address": "Rua Santos, 450, Apto 3 - Centro, Londrina - PR, 86020-040",
                 "route": "Rua Santos", "street_number": "450", "complement": "Apto 3",
                 "neighborhood": "Centro", "city": "Londrina", "state": "Parana",
                 "state_code": "PR", "postal_code": "86020-040",
                 "latitude": Decimal("-23.3115000"), "longitude": Decimal("-51.1610000"), "is_default": True},
                {"label": "other", "label_custom": "Casa da mae",
                 "formatted_address": "Rua Pernambuco, 120 - Centro, Londrina - PR, 86020-120",
                 "route": "Rua Pernambuco", "street_number": "120", "complement": "",
                 "neighborhood": "Centro", "city": "Londrina", "state": "Parana",
                 "state_code": "PR", "postal_code": "86020-120",
                 "latitude": Decimal("-23.3090000"), "longitude": Decimal("-51.1575000"), "is_default": False},
            ]),
            ("CLI-006", [
                {"label": "home", "formatted_address": "Av. Juscelino Kubitschek, 1200 - Ipiranga, Londrina - PR, 86010-540",
                 "route": "Av. Juscelino Kubitschek", "street_number": "1200", "complement": "",
                 "neighborhood": "Ipiranga", "city": "Londrina", "state": "Parana",
                 "state_code": "PR", "postal_code": "86010-540",
                 "latitude": Decimal("-23.3150000"), "longitude": Decimal("-51.1500000"), "is_default": True},
            ]),
            ("CLI-007", [
                {"label": "work", "formatted_address": "Av. Ayrton Senna, 600 - Gleba Palhano, Londrina - PR, 86050-460",
                 "route": "Av. Ayrton Senna", "street_number": "600", "complement": "",
                 "neighborhood": "Gleba Palhano", "city": "Londrina", "state": "Parana",
                 "state_code": "PR", "postal_code": "86050-460",
                 "latitude": Decimal("-23.3280000"), "longitude": Decimal("-51.1870000"), "is_default": True},
            ]),
        ]

        count = 0
        for ref, addrs in addresses_data:
            if ref not in customers:
                continue
            customer = customers[ref]
            for addr in addrs:
                label_custom = addr.pop("label_custom", "")
                _, created = CustomerAddress.objects.get_or_create(
                    customer=customer,
                    formatted_address=addr["formatted_address"],
                    defaults={
                        "label": addr["label"],
                        "label_custom": label_custom,
                        "route": addr["route"],
                        "street_number": addr["street_number"],
                        "complement": addr["complement"],
                        "neighborhood": addr["neighborhood"],
                        "city": addr["city"],
                        "state": addr["state"],
                        "state_code": addr["state_code"],
                        "postal_code": addr["postal_code"],
                        "latitude": addr["latitude"],
                        "longitude": addr["longitude"],
                        "is_default": addr["is_default"],
                    },
                )
                if created:
                    count += 1

        self.stdout.write(f"  ✅ {count} enderecos de clientes")

    # ────────────────────────────────────────────────────────────────
    # Promotions e Coupons (Shop)
    # ────────────────────────────────────────────────────────────────

    def _seed_promotions(self):
        self.stdout.write("  🏷️  Promotions e coupons...")

        now = timezone.now()

        # Promotion 1: Semana do Pao — 15% off paes artesanais
        promo_paes, _ = Promotion.objects.update_or_create(
            name="Semana do Pao",
            defaults={
                "type": Promotion.PERCENT,
                "value": 15,
                "valid_from": now,
                "valid_until": now + timedelta(days=7),
                "collections": ["paes-artesanais"],
                "is_active": True,
            },
        )

        # Promotion 2: Delivery Desconto — R$2 off apenas em pedidos delivery
        promo_delivery, _ = Promotion.objects.update_or_create(
            name="Delivery Desconto",
            defaults={
                "type": Promotion.FIXED,
                "value": 200,
                "valid_from": now,
                "valid_until": now + timedelta(days=30),
                "fulfillment_types": ["delivery"],
                "is_active": True,
            },
        )

        # Promotion for NELSON10 coupon (10% off geral)
        promo_nelson10, _ = Promotion.objects.update_or_create(
            name="Desconto Nelson 10%",
            defaults={
                "type": Promotion.PERCENT,
                "value": 10,
                "valid_from": now,
                "valid_until": now + timedelta(days=30),
                "is_active": True,
            },
        )

        # Promotion for PRIMEIRACOMPRA coupon (R$5 off, min R$30)
        promo_primeira, _ = Promotion.objects.update_or_create(
            name="Primeira Compra",
            defaults={
                "type": Promotion.FIXED,
                "value": 500,
                "valid_from": now,
                "valid_until": now + timedelta(days=30),
                "min_order_q": 3000,
                "is_active": True,
            },
        )

        # Promotion for FUNCIONARIO coupon (20% off, restricted to staff group)
        promo_funcionario, _ = Promotion.objects.update_or_create(
            name="Desconto Funcionario",
            defaults={
                "type": Promotion.PERCENT,
                "value": 20,
                "valid_from": now,
                "valid_until": now + timedelta(days=365),
                "customer_segments": ["staff"],
                "is_active": True,
            },
        )

        # Coupons
        Coupon.objects.update_or_create(
            code="NELSON10",
            defaults={"promotion": promo_nelson10, "max_uses": 1, "is_active": True},
        )
        Coupon.objects.update_or_create(
            code="PRIMEIRACOMPRA",
            defaults={"promotion": promo_primeira, "max_uses": 1, "is_active": True},
        )
        Coupon.objects.update_or_create(
            code="FUNCIONARIO",
            defaults={"promotion": promo_funcionario, "max_uses": 0, "is_active": True},
        )

        self.stdout.write("  ✅ 5 promotions, 3 coupons")

    # ────────────────────────────────────────────────────────────────
    # Payments (PaymentIntent + PaymentTransaction)
    # ────────────────────────────────────────────────────────────────

    def _seed_payments(self):
        self.stdout.write("  💳 Payments...")

        orders = Order.objects.filter(status__in=["completed", "delivered"])
        count = 0

        for i, order in enumerate(orders):
            # Skip if already has payment
            if PaymentIntent.objects.filter(order_ref=order.ref).exists():
                continue

            method = PaymentIntent.Method.PIX if i % 10 < 7 else PaymentIntent.Method.CARD
            gateway = "efi" if method == PaymentIntent.Method.PIX else "stripe"
            intent_ref = f"PI-{uuid.uuid4().hex[:12].upper()}"

            intent = PaymentIntent(
                ref=intent_ref,
                order_ref=order.ref,
                method=method,
                status=PaymentIntent.Status.CAPTURED,
                amount_q=order.total_q,
                gateway=gateway,
                gateway_id=f"gw-{uuid.uuid4().hex[:16]}",
                captured_at=order.created_at + timedelta(minutes=5),
            )
            intent.save()

            PaymentTransaction.objects.create(
                intent=intent,
                type=PaymentTransaction.Type.CAPTURE,
                amount_q=order.total_q,
                gateway_id=intent.gateway_id,
            )
            count += 1

        self.stdout.write(f"  ✅ {count} payment intents + transactions")

    # ────────────────────────────────────────────────────────────────
    # Fulfillments
    # ────────────────────────────────────────────────────────────────

    def _seed_fulfillments(self):
        self.stdout.write("  📦 Fulfillments...")

        count = 0

        # Completed/delivered orders: fulfilled
        for order in Order.objects.filter(status__in=["completed", "delivered"]):
            if Fulfillment.objects.filter(order=order).exists():
                continue

            is_delivery = order.channel.ref in ("delivery", "whatsapp", "web")

            if is_delivery:
                tracking_code = f"BR{uuid.uuid4().hex[:12].upper()}"
                fulfillment = Fulfillment(
                    order=order,
                    status=Fulfillment.Status.DELIVERED,
                    tracking_code=tracking_code,
                    carrier="correios",
                    dispatched_at=order.created_at + timedelta(minutes=10),
                    delivered_at=order.created_at + timedelta(hours=2),
                )
            else:
                fulfillment = Fulfillment(
                    order=order,
                    status=Fulfillment.Status.DELIVERED,
                    delivered_at=order.created_at + timedelta(minutes=15),
                )

            # Bypass transition validation for seed
            fulfillment.save()

            # Create FulfillmentItems
            for item in order.items.all():
                FulfillmentItem.objects.create(
                    fulfillment=fulfillment,
                    order_item=item,
                    qty=item.qty,
                )

            count += 1

        # Processing orders: fulfillment in progress
        for order in Order.objects.filter(status="processing"):
            if Fulfillment.objects.filter(order=order).exists():
                continue

            is_delivery = order.channel.ref in ("delivery", "whatsapp", "web")

            fulfillment = Fulfillment(
                order=order,
                status=Fulfillment.Status.IN_PROGRESS,
            )
            if is_delivery:
                fulfillment.carrier = "correios"

            fulfillment.save()
            count += 1

        self.stdout.write(f"  ✅ {count} fulfillments")

    # ────────────────────────────────────────────────────────────────
    # Directives
    # ────────────────────────────────────────────────────────────────

    def _seed_directives(self):
        self.stdout.write("  📋 Directives...")

        # Directive topics (inline — channels.topics is gone)
        STOCK_HOLD = "stock.hold"
        PAYMENT_CAPTURE = "payment.capture"
        NOTIFICATION_SEND = "notification.send"
        FULFILLMENT_CREATE = "fulfillment.create"

        count = 0
        for order in Order.objects.filter(status__in=["completed", "delivered", "processing", "confirmed"]):
            if Directive.objects.filter(payload__order_ref=order.ref).exists():
                continue

            is_terminal = order.status in ("completed", "delivered")
            directive_status = "done" if is_terminal else "queued"
            base_time = order.created_at

            # stock.hold
            Directive.objects.create(
                topic=STOCK_HOLD,
                status=directive_status,
                payload={"order_ref": order.ref},
                available_at=base_time,
            )

            # payment.capture (for completed/delivered)
            if is_terminal:
                Directive.objects.create(
                    topic=PAYMENT_CAPTURE,
                    status="done",
                    payload={"order_ref": order.ref},
                    available_at=base_time + timedelta(minutes=1),
                )

            # notification.send
            Directive.objects.create(
                topic=NOTIFICATION_SEND,
                status=directive_status,
                payload={"order_ref": order.ref, "template": "order_confirmed"},
                available_at=base_time + timedelta(minutes=2),
            )

            # fulfillment.create (for completed/delivered)
            if is_terminal:
                Directive.objects.create(
                    topic=FULFILLMENT_CREATE,
                    status="done",
                    payload={"order_ref": order.ref},
                    available_at=base_time + timedelta(minutes=3),
                )

            count += 1

        self.stdout.write(f"  ✅ Directives para {count} pedidos")

    # ────────────────────────────────────────────────────────────────
    # Loyalty (fidelidade)
    # ────────────────────────────────────────────────────────────────

    def _seed_loyalty(self, customers):
        self.stdout.write("  🎖️  Loyalty...")

        try:
            from shopman.customers.contrib.loyalty.service import LoyaltyService
        except ImportError:
            self.stdout.write("  ⏭️  Loyalty app nao instalado")
            return

        loyalty_data = [
            # (customer_ref, points_to_earn, stamps, tier_desc, redeem_points)
            ("CLI-001", 350, 7, "frequente", 100),
            ("CLI-002", 200, 4, "atacado", 0),
            ("CLI-003", 120, 3, "regular", 0),
            ("CLI-004", 80, 2, "cafe", 0),
            ("CLI-005", 45, 1, "novo", 0),
        ]

        count = 0
        for ref, points, stamps, _desc, redeem in loyalty_data:
            if ref not in customers:
                continue

            account = LoyaltyService.enroll(ref)
            if account.lifetime_points > 0:
                count += 1
                continue

            # Earn points in batches to simulate history
            batch_size = points // 3 or 1
            remaining = points
            order_num = 1
            while remaining > 0:
                earn = min(batch_size, remaining)
                LoyaltyService.earn_points(
                    customer_ref=ref,
                    points=earn,
                    description=f"Pedido #{order_num}",
                    reference=f"seed:order-{order_num}",
                    created_by="seed",
                )
                remaining -= earn
                order_num += 1

            # Add stamps
            for i in range(stamps):
                LoyaltyService.add_stamp(
                    customer_ref=ref,
                    description=f"Compra #{i + 1}",
                    reference=f"seed:stamp-{i + 1}",
                )

            # Redeem points (if specified)
            if redeem > 0:
                LoyaltyService.redeem_points(
                    customer_ref=ref,
                    points=redeem,
                    description="Resgate de pontos",
                    reference="seed:redeem-1",
                    created_by="seed",
                )

            count += 1

        self.stdout.write(f"  ✅ {count} contas de fidelidade")

    # ────────────────────────────────────────────────────────────────
    # KDS (Kitchen Display System)
    # ────────────────────────────────────────────────────────────────

    def _seed_kds(self):
        self.stdout.write("  🖥️  KDS...")

        # Get collections
        col_paes = Collection.objects.filter(slug="paes-artesanais").first()
        col_confeitaria = Collection.objects.filter(slug="confeitaria").first()
        col_bebidas = Collection.objects.filter(slug="bebidas").first()

        # KDS Pães — Picking: pães e folhados já prontos na vitrine
        # (produzidos em lote via WorkOrder antes da abertura).
        kds_paes, _ = KDSInstance.objects.update_or_create(
            ref="paes",
            defaults={
                "name": "Pães",
                "type": "picking",
                "target_time_minutes": 3,
                "sound_enabled": True,
                "is_active": True,
            },
        )
        kds_paes.collections.clear()
        if col_paes:
            kds_paes.collections.add(col_paes)
        if col_confeitaria:
            kds_paes.collections.add(col_confeitaria)

        # KDS Cafés — Prep: bebidas preparadas na hora (espresso, latte)
        kds_cafes, _ = KDSInstance.objects.update_or_create(
            ref="cafes",
            defaults={
                "name": "Cafés",
                "type": "prep",
                "target_time_minutes": 5,
                "sound_enabled": True,
                "is_active": True,
            },
        )
        kds_cafes.collections.clear()
        if col_bebidas:
            kds_cafes.collections.add(col_bebidas)

        # KDS Lanches — Prep catch-all: salgados e sanduíches preparados
        # na hora. Catch-all para prep items sem estação específica.
        kds_lanches, _ = KDSInstance.objects.update_or_create(
            ref="lanches",
            defaults={
                "name": "Lanches",
                "type": "prep",
                "target_time_minutes": 8,
                "sound_enabled": True,
                "is_active": True,
            },
        )
        kds_lanches.collections.clear()  # catch-all prep

        # KDS Expedição — mostra pedidos prontos (READY)
        KDSInstance.objects.update_or_create(
            ref="expedicao",
            defaults={
                "name": "Expedição",
                "type": "expedition",
                "target_time_minutes": 5,
                "sound_enabled": True,
                "is_active": True,
            },
        )

        self.stdout.write("  ✅ 4 estações KDS (Pães, Cafés, Lanches, Expedição)")

    # ────────────────────────────────────────────────────────────────
    # Notification Templates
    # ────────────────────────────────────────────────────────────────

    def _seed_notification_templates(self):
        self.stdout.write("  📨 Templates de notificação...")

        from shopman.models import NotificationTemplate

        FALLBACK_TEMPLATES = {
            "order_confirmed": {"subject": "Pedido {order_ref} confirmado", "body": "Ola{customer_name_greeting}! Seu pedido *{order_ref}* foi confirmado. Total: *{total}*.\n\nObrigado pela preferencia!"},
            "order_processing": {"subject": "Pedido {order_ref} em preparo", "body": "Ola{customer_name_greeting}! Seu pedido *{order_ref}* esta sendo preparado.\n\nAvisaremos quando estiver pronto!"},
            "order_ready": {"subject": "Pedido {order_ref} pronto para retirada", "body": "Ola{customer_name_greeting}! Seu pedido *{order_ref}* esta pronto!\n\nVenha retirar. Obrigado!"},
            "order_dispatched": {"subject": "Pedido {order_ref} saiu para entrega", "body": "Ola{customer_name_greeting}! Seu pedido *{order_ref}* saiu para entrega!\n\nEm breve estara com voce!"},
            "order_delivered": {"subject": "Pedido {order_ref} entregue", "body": "Ola{customer_name_greeting}! Seu pedido *{order_ref}* foi entregue.\n\nEsperamos que tenha gostado! Obrigado pela preferencia."},
            "order_cancelled": {"subject": "Pedido {order_ref} cancelado", "body": "Ola{customer_name_greeting}! Seu pedido *{order_ref}* foi cancelado.\n\nEm caso de duvidas, entre em contato."},
            "payment_confirmed": {"subject": "Pagamento do pedido {order_ref} confirmado", "body": "Ola{customer_name_greeting}! O pagamento do pedido *{order_ref}* foi recebido.\n\nValor: *{total}*\n\nSeu pedido sera preparado em breve. Obrigado!"},
            "payment_refunded": {"subject": "Reembolso do pedido {order_ref} processado", "body": "Ola{customer_name_greeting}! O reembolso do pedido *{order_ref}* foi processado.\n\nValor: *{total}*"},
            "loyalty_earned": {"subject": "Voce ganhou pontos de fidelidade!", "body": "Ola{customer_name_greeting}! Voce ganhou pontos de fidelidade com o pedido *{order_ref}*!"},
        }

        count = 0
        for event, tpl in FALLBACK_TEMPLATES.items():
            _, created = NotificationTemplate.objects.update_or_create(
                event=event,
                defaults={
                    "subject": tpl["subject"],
                    "body": tpl["body"],
                    "is_active": True,
                },
            )
            if created:
                count += 1

        self.stdout.write(f"  ✅ {len(FALLBACK_TEMPLATES)} templates de notificação ({count} novos)")

    def _seed_rule_configs(self):
        self.stdout.write("  ⚙️  Rule configs...")

        RULE_CONFIGS = [
            {
                "code": "d1_discount",
                "rule_path": "shopman.rules.pricing.D1Rule",
                "label": "Desconto D-1 (sobras)",
                "params": {"discount_percent": 50},
                "priority": 15,
            },
            {
                "code": "promotion_discount",
                "rule_path": "shopman.rules.pricing.PromotionRule",
                "label": "Promoções e Cupons",
                "params": {},
                "priority": 20,
            },
            {
                "code": "employee_discount",
                "rule_path": "shopman.rules.pricing.EmployeeRule",
                "label": "Desconto Funcionário",
                "params": {"discount_percent": 20, "group": "staff"},
                "priority": 60,
            },
            {
                "code": "happy_hour",
                "rule_path": "shopman.rules.pricing.HappyHourRule",
                "label": "Happy Hour",
                "params": {"discount_percent": 10, "start": "16:00", "end": "18:00"},
                "priority": 65,
            },
            {
                "code": "business_hours",
                "rule_path": "shopman.rules.validation.BusinessHoursRule",
                "label": "Horário de Funcionamento",
                "params": {},
                "priority": 10,
            },
            {
                "code": "minimum_order",
                "rule_path": "shopman.rules.validation.MinimumOrderRule",
                "label": "Pedido Mínimo Delivery",
                "params": {"minimum_q": 1000},
                "priority": 20,
            },
        ]

        count = 0
        for rc in RULE_CONFIGS:
            _, created = RuleConfig.objects.update_or_create(
                code=rc["code"],
                defaults={
                    "rule_path": rc["rule_path"],
                    "label": rc["label"],
                    "params": rc["params"],
                    "priority": rc["priority"],
                    "enabled": True,
                },
            )
            if created:
                count += 1

        self.stdout.write(f"  ✅ {len(RULE_CONFIGS)} rule configs ({count} novos)")
