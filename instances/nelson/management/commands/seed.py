"""
Seed de producao — Nelson Boulangerie.

Popula loja (shop), catalogo (offerman), estoque (stockman), receitas (craftsman),
clientes (customers), canais (orderman) e pedidos com dados da Nelson.

Uso:
    python manage.py seed          # seed normal
    python manage.py seed --flush  # apaga tudo e recria

IMPORTANTE — Não-determinismo deliberado:
    Este seed usa random.choice, uuid4 e now() intencionalmente para gerar dados
    realistas a cada execução. Não é adequado como fixture de testes. Para testes
    deterministicos use TestCase com fixtures ou factories dedicadas.
"""
from __future__ import annotations

import os
import random
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

# ── Craftsman (producao) ─────────────────────────────────────────────
from shopman.craftsman.models import Recipe, RecipeItem, WorkOrder, WorkOrderItem

# ── Customers (clientes) ─────────────────────────────────────────────
from shopman.guestman.models import ContactPoint, Customer, CustomerAddress, CustomerGroup

# ── Shopman (orchestrator) ────────────────────────────────────────────
from shopman.shop.models import RuleConfig, Shop
from shopman.backstage.models import (
    CashMovement,
    CashRegisterSession,
    DayClosing,
    KDSInstance,
)
from shopman.storefront.models import Coupon, Promotion

# ── Offerman (catalogo) ──────────────────────────────────────────────
from shopman.offerman.models import (
    Collection,
    CollectionItem,
    Listing,
    ListingItem,
    Product,
    ProductComponent,
)

# ── Orderman (pedidos) ───────────────────────────────────────────────
from shopman.orderman.models import (
    Directive,
    Fulfillment,
    FulfillmentItem,
    Order,
    OrderEvent,
    OrderItem,
    Session,
)

# ── Shop (canais — parte do orquestrador, não do core) ──────────────
from shopman.shop.models import Channel

# ── Payments ─────────────────────────────────────────────────────────
from shopman.payman.models import PaymentIntent, PaymentTransaction

# ── Stockman (estoque) ──────────────────────────────────────────────
from shopman.stockman import stock
from shopman.stockman.models import Position, PositionKind, StockAlert


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
        self._seed_day_closing()
        self._seed_cash_register()

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
                "heading_font": "Instrument Sans",
                "body_font": "Instrument Sans",
                "border_radius": "soft",
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
                "email": "nelson@boulangerie.com.br",
                "default_ddd": "43",
                "social_links": [
                    "https://wa.me/554333231997",
                    "https://instagram.com/example",
                    "https://www.facebook.com/example",
                    "http://www.example.com.br",
                ],
                "opening_hours": {
                    "monday":    {"open": "09:00", "close": "18:00"},
                    "tuesday":   {"open": "09:00", "close": "18:00"},
                    "wednesday": {"open": "09:00", "close": "18:00"},
                    "thursday":  {"open": "09:00", "close": "18:00"},
                    "friday":    {"open": "09:00", "close": "18:00"},
                    "saturday":  {"open": "09:00", "close": "18:00"},
                    # sunday: fechado
                },
                "defaults": {
                    "menu": {
                        "dynamic_collections": ["featured", "fresh_from_oven"],
                    },
                    "notifications": {"backend": "console"},
                    "pickup_slots": [
                        {"ref": "slot-09", "label": "A partir das 09h", "starts_at": "09:00"},
                        {"ref": "slot-12", "label": "A partir das 12h", "starts_at": "12:00"},
                        {"ref": "slot-15", "label": "A partir das 15h", "starts_at": "15:00"},
                    ],
                    "pickup_slot_config": {
                        "rounding_minutes": 30,
                        "history_days": 30,
                        "fallback_slot": "slot-09",
                    },
                    "max_preorder_days": 30,
                    "closed_dates": [
                        {"date": "2026-12-25", "label": "Natal"},
                        {"date": "2026-12-31", "label": "Réveillon"},
                        {"date": "2026-01-01", "label": "Confraternização Universal"},
                    ],
                    "seasons": {
                        "hot":  [10, 11, 12, 1, 2, 3],
                        "mild": [4, 5, 9],
                        "cold": [6, 7, 8],
                    },
                    "high_demand_multiplier": "1.2",
                    "safety_stock_percent": "0.20",
                },
            },
        )
        self.stdout.write("  ✅ Shop criado" if created else "  ✅ Shop atualizado")

    # ────────────────────────────────────────────────────────────────
    # Delivery Zones
    # ────────────────────────────────────────────────────────────────

    def _seed_delivery_zones(self):
        from shopman.storefront.models import DeliveryZone

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
                email="admin@example.com",
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

        # Orderman
        for model in [FulfillmentItem, Fulfillment, Directive, OrderEvent, OrderItem, Order, Session, Channel]:
            model.objects.all().delete()

        # Offerman
        for model in [ListingItem, Listing, CollectionItem, Collection, ProductComponent, Product]:
            model.objects.all().delete()

        # Stockman
        from shopman.stockman.models import Hold, Move, Quant

        for model in [StockAlert, Hold, Move, Quant, Position]:
            model.objects.all().delete()

        # Craftsman
        from shopman.craftsman.models import WorkOrderEvent

        for model in [WorkOrderEvent, WorkOrder, RecipeItem, Recipe]:
            model.objects.all().delete()

        # Customers
        for model in [CustomerAddress, ContactPoint, Customer, CustomerGroup]:
            model.objects.all().delete()

        # KDS
        from shopman.backstage.models import KDSTicket

        KDSTicket.objects.all().delete()
        KDSInstance.objects.all().delete()

        # Cash register
        CashMovement.objects.all().delete()
        CashRegisterSession.objects.all().delete()

        # Day closing
        DayClosing.objects.all().delete()

        # Shop
        Coupon.objects.all().delete()
        Promotion.objects.all().delete()
        Shop.objects.all().delete()

        self.stdout.write("  ✅ Dados limpos")

    # ────────────────────────────────────────────────────────────────
    # Catalogo (Offerman)
    # ────────────────────────────────────────────────────────────────

    def _seed_catalog(self):
        self.stdout.write("  📦 Catalogo...")

        # Catalogo real Nelson Boulangerie
        # Fonte: https://github.com/pablondrina/nb-catalog
        IMG = "https://raw.githubusercontent.com/pablondrina/nb-catalog/main/img/products"

        # (sku, name, short_desc, price_q, unit, shelf_life, available, image, weight_g, storage_tip)
        products_data = [
            # ── Paes Artesanais (fermentacao natural / levain) ──
            ("BAGUETE", "Baguete Francesa", "Pao de tradicao francesa e fermentacao 100% natural (levain)", 1300, "un", 0, True,
             f"{IMG}/bf.jpg", 250, "Congele inteira ou em pedacos. Reaqueça direto do freezer a 200°C por 8min"),
            ("BAGUETE-CAMPAGNE", "Baguette de Campagne", "Baguete de fermentacao natural (levain), trigo 50% integral e centeio organico", 1700, "un", 1, True,
             f"{IMG}/cf.jpg", 280, "Guarde em saco de pano. Congele em ate 2h para melhor resultado"),
            ("BAGUETE-GERGELIM", "Baguete Gergelim", "Baguete com fermentacao 100% natural (levain), toque de azeite e gergelim", 1800, "un", 0, True,
             f"{IMG}/be.jpg", 260, "Congele no mesmo dia. Reaqueça a 200°C por 8min"),
            ("MINI-BAGUETE", "Mini Baguete", "Mini baguete com fermentacao 100% natural (levain) e toque de azeite", 900, "un", 0, True,
             f"{IMG}/bap.jpg", 120, "Congele no mesmo dia. Reaqueça a 200°C por 5min"),
            ("BATARD", "Batard", "Pao de tradicao francesa e fermentacao 100% natural (levain) em formato de filao", 1300, "un", 0, True,
             f"{IMG}/ba.jpg", 350, "Guarde em saco de pano. Congele em ate 2h"),
            ("FENDU", "Fendu", "Paozinho de tradicao francesa e fermentacao 100% natural (levain)", 600, "un", 0, True,
             f"{IMG}/fe.jpg", 100, "Melhor consumido no dia. Congele para ate 30 dias"),
            ("TABATIERE", "Tabatiere", "Paozinho de tradicao francesa e fermentacao 100% natural (levain)", 600, "un", 0, True,
             f"{IMG}/tb.jpg", 100, "Melhor consumido no dia. Congele para ate 30 dias"),
            ("ITALIANO-RUSTICO", "Italiano Rustico", "Pao tradicional com fermentacao 100% natural (levain)", 2200, "un", 1, True,
             f"{IMG}/bax.jpg", 400, "Guarde em saco de pano. Dura ate 3 dias em temperatura ambiente"),
            ("CAMPAGNE-OVAL", "Pain de Campagne (Oval)", "Fermentacao natural (levain), trigo 50% integral e centeio organico", 1800, "un", 2, True,
             f"{IMG}/cgo.jpg", 500, "Guarde em saco de pano. Dura ate 4 dias em temperatura ambiente"),
            ("CAMPAGNE-REDONDO", "Pain de Campagne (Redondo)", "Fermentacao natural (levain), trigo 50% integral e centeio organico", 1800, "un", 2, True,
             f"{IMG}/cgr.jpg", 500, "Guarde em saco de pano. Dura ate 4 dias em temperatura ambiente"),
            ("CAMPAGNE-PASSAS", "Campagne Passas & Castanhas", "Levain, trigo 50% integral e centeio organico, passas, castanhas de caju e do Para", 3300, "un", 3, True,
             f"{IMG}/cpx.jpg", 550, "Guarde em saco de pano. Dura ate 5 dias em temperatura ambiente"),
            ("CIABATTA", "Ciabatta", "Pao aerado, classico italiano com azeite extra virgem, fermentacao 100% natural (levain)", 1400, "un", 0, True,
             f"{IMG}/ci.jpg", 200, "Congele no mesmo dia. Reaqueça a 200°C por 8min"),
            ("PAO-FORMA", "Pao de Forma Artesanal", "Super macio ao estilo japones. Vem com 6 fatias grossas", 1800, "un", 2, True,
             f"{IMG}/fa.jpg", 400, "Mantenha em saco plastico fechado. Congela bem por ate 30 dias"),
            ("CHALLAH", "Challah", "Tranca fofinha e levemente adocicada, decorada com gergelim", 1800, "un", 2, True,
             f"{IMG}/ch.jpg", 350, "Mantenha em saco plastico fechado. Congela bem por ate 30 dias"),
            ("PAO-HAMBURGER", "Pao de Hamburger", "Pao de tradicao francesa e fermentacao 100% natural (levain)", 600, "un", 0, True,
             f"{IMG}/ph.jpg", 100, "Melhor consumido no dia. Congele para ate 30 dias"),
            # ── Focaccias ──
            ("FOCACCIA-ALECRIM", "Focaccia Alecrim & Sal Grosso", "Classico italiano, alecrim fresco e sal grosso, regada com azeite extra virgem", 3100, "un", 0, True,
             f"{IMG}/foa.jpg", 450, "Congele em porcoes. Reaqueça a 200°C por 5min com um fio de azeite"),
            ("FOCACCIA-CEBOLA", "Focaccia Cebola Roxa & Azeitonas", "Cebola roxa e azeitonas pretas, regada com azeite extra virgem", 4000, "un", 0, True,
             f"{IMG}/foc.jpg", 500, "Congele em porcoes. Reaqueça a 200°C por 5min"),
            ("FOCACCIA-BACON", "Focaccia Bacon, Cebola & Tomilho", "Cebola, bacon, tomilho e queijo minas, regada com azeite extra virgem", 4000, "un", 0, True,
             f"{IMG}/cbt.jpg", 500, "Congele em porcoes. Reaqueça a 200°C por 5min"),
            ("MINI-FOCACCIA-ALECRIM", "Mini Focaccia Alecrim & Sal Grosso", "Versao individual, alecrim fresco e sal grosso, regada com azeite extra virgem", 1300, "un", 0, True,
             f"{IMG}/mif.jpg", 150, "Melhor consumida no dia. Reaqueça a 200°C por 3min"),
            ("MINI-FOCACCIA-CEBOLA", "Mini Focaccia Cebola Roxa & Azeitonas", "Versao individual, cebola roxa e azeitonas pretas", 1800, "un", 0, True,
             f"{IMG}/mifoc.jpg", 160, "Melhor consumida no dia. Reaqueça a 200°C por 3min"),
            ("MINI-FOCACCIA-BACON", "Mini Focaccia Bacon, Cebola & Tomilho", "Versao individual, cebola, bacon, tomilho e queijo minas", 1800, "un", 0, True,
             f"{IMG}/micbt.jpg", 160, "Melhor consumida no dia. Reaqueça a 200°C por 3min"),
            # ── Brioches & Paes Especiais ──
            ("BRIOCHE", "Brioche Nanterre", "Super leve e levemente adocicado", 2200, "un", 2, True,
             f"{IMG}/bn.jpg", 350, "Mantenha em saco plastico fechado. Congela bem por ate 30 dias"),
            ("BRIOCHE-BURGER", "Brioche Burger Bun (pc. 2un.)", "Super leve, riquisimo em ovos e manteiga", 1600, "un", 1, True,
             f"{IMG}/bbb.jpg", 200, "Congele no mesmo dia. Reaqueça a 180°C por 5min"),
            ("PAO-HOTDOG", "Pao para Hot Dog (pc. 4un.)", "Pao amanteigado, bom para cachorro quente", 2800, "un", 1, True,
             f"{IMG}/pho.jpg", 320, "Congele no mesmo dia para ate 30 dias"),
            # ── Croissants & Folhados ──
            ("CROISSANT", "Croissant Tradicional", "Classico em pura manteiga. Simples e delicioso. Otimo com geleias!", 1300, "un", 1, True,
             f"{IMG}/ct.jpg", 80, "Reaqueça no forno a 180°C por 5min para recuperar a crocancia"),
            ("PAIN-CHOCOLAT", "Pain au Chocolat", "Croissant recheado com chocolate!", 1500, "un", 1, True,
             f"{IMG}/pc.jpg", 90, "Reaqueça no forno a 180°C por 5min. Evite micro-ondas"),
            ("MINI-CROISSANT", "Mini Croissant", "Delicioso mini croissant com calda doce", 800, "un", 1, True,
             f"{IMG}/cm.jpg", 40, "Consuma no dia. Reaqueça no forno a 180°C por 3min"),
            ("CHAUSSON", "Chausson aux Pommes", "Classico folhado em pura manteiga, recheio de maca & canela da casa", 1800, "un", 1, True,
             f"{IMG}/cn.jpg", 120, "Consuma no dia. Reaqueça no forno a 180°C por 5min"),
            ("BICHON", "Bichon au Citron", "Folhado com creme de limao", 1800, "un", 1, True,
             f"{IMG}/bh.jpg", 110, "Consuma no dia. Reaqueça no forno a 180°C por 5min"),
            # ── Paes Doces & Recheados ──
            ("CORNET-CHOCOLATE", "Cornet Chocolate", "Pao amanteigado em formato de cone, recheio de creme de chocolate", 1100, "un", 1, True,
             f"{IMG}/coc.jpg", 120, "Melhor consumido no dia. Reaqueça a 180°C por 5min"),
            ("CORNET", "Cornet", "Pao amanteigado em formato de cone, recheio de creme", 1000, "un", 1, True,
             f"{IMG}/co.jpg", 120, "Melhor consumido no dia. Reaqueça a 180°C por 5min"),
            ("MELON-PAN", "Melon Pan", "Classico japones amanteigado com cobertura crocante e levemente doce", 1100, "un", 1, True,
             f"{IMG}/me.jpg", 100, "Melhor consumido no dia"),
            ("PAIN-RAISINS", "Pain aux Raisins", "Brioche com creme e uvas passas", 1100, "un", 1, True,
             f"{IMG}/pr.jpg", 110, "Consuma no dia. Reaqueça no forno a 180°C por 5min"),
            ("BRIOCHE-CHOCOLAT", "Brioche Chocolat", "Briochinho super macio com gotas de chocolate", 1000, "un", 1, True,
             f"{IMG}/bch.jpg", 90, "Melhor consumido no dia"),
            ("MADELEINE", "Madeleine", "Bolinho classico frances, simples e delicioso", 600, "un", 2, True,
             f"{IMG}/md.jpg", 40, "Conserve em recipiente fechado por ate 3 dias"),
            # ── Salgados & Recheados ──
            ("DELI", "Deli", "Pao amanteigado recheado com milho, bacon & queijo minas", 1900, "un", 0, True,
             f"{IMG}/dl.jpg", 180, "Melhor consumido quente, no dia"),
            ("HOTDOG", "Hot Dog", "Pao amanteigado recheado com salsicha viena artesanal", 1500, "un", 0, True,
             f"{IMG}/ho.jpg", 180, "Melhor consumido quente, no dia"),
            # ── Lanches (montados na hora) ──
            ("CROQUE-MONSIEUR", "Croque Monsieur", "Classico sanduiche frances gratinado com presunto e queijo gruyere", 2400, "un", 0, True,
             f"{IMG}/cm.jpg", 250, "Servir quente, imediatamente"),
            ("CROQUE-MADAME", "Croque Madame", "Croque monsieur com ovo pochado por cima", 2800, "un", 0, True,
             f"{IMG}/cmd.jpg", 290, "Servir quente, imediatamente"),
            ("QUICHE-LORRAINE", "Quiche Lorraine", "Quiche classica de bacon, queijo e cebola", 1800, "un", 0, True,
             f"{IMG}/ql.jpg", 200, "Melhor consumido quente, no dia"),
            ("QUICHE-LEGUMES", "Quiche de Legumes", "Quiche vegetariana com abobrinha, tomate e queijo", 1800, "un", 0, True,
             f"{IMG}/qv.jpg", 200, "Melhor consumido quente, no dia"),
            ("TARTINE-SAUMON", "Tartine Saumon", "Fatia de campagne com cream cheese, salmao defumado e alcaparras", 2600, "un", 0, True,
             f"{IMG}/ts.jpg", 220, "Servir frio, consumir no dia"),
            ("TARTINE-TOMATE", "Tartine Tomate & Burrata", "Fatia de campagne com tomate, burrata e manjericao", 2200, "un", 0, True,
             f"{IMG}/tt.jpg", 200, "Servir frio, consumir no dia"),
            # ── Cafes e Bebidas ──
            ("ESPRESSO", "Espresso", "Cafe espresso puro, grao especial torrado artesanal", 800, "un", None, True,
             f"{IMG}/es.jpg", 0, ""),
            ("ESPRESSO-DUPLO", "Espresso Duplo", "Dose dupla de espresso", 1000, "un", None, True,
             f"{IMG}/ed.jpg", 0, ""),
            ("CAPPUCCINO", "Cappuccino", "Espresso com leite vaporizado e espuma cremosa", 1200, "un", None, True,
             f"{IMG}/cp.jpg", 0, ""),
            ("LATTE", "Cafe Latte", "Espresso com bastante leite vaporizado", 1200, "un", None, True,
             f"{IMG}/lt.jpg", 0, ""),
            ("CHOCOLATE-QUENTE", "Chocolate Quente", "Chocolate belga com leite vaporizado", 1400, "un", None, True,
             f"{IMG}/cq.jpg", 0, ""),
            ("CHA-EARL-GREY", "Cha Earl Grey", "Cha preto com bergamota, servido em bule", 900, "un", None, True,
             f"{IMG}/ch.jpg", 0, ""),
            ("SUCO-LARANJA", "Suco de Laranja", "Suco natural de laranja espremido na hora", 1200, "un", None, True,
             f"{IMG}/sl.jpg", 0, ""),
        ]

        # Keywords by product (for find_alternatives and search)
        keywords_map = {
            "BAGUETE": ["pao", "frances", "levain", "artesanal", "crocante"],
            "BAGUETE-CAMPAGNE": ["pao", "campagne", "levain", "integral", "centeio"],
            "BAGUETE-GERGELIM": ["pao", "frances", "levain", "gergelim", "azeite"],
            "MINI-BAGUETE": ["pao", "frances", "levain", "mini", "individual"],
            "BATARD": ["pao", "frances", "levain", "filao", "artesanal"],
            "FENDU": ["pao", "frances", "levain", "individual", "artesanal"],
            "TABATIERE": ["pao", "frances", "levain", "individual", "artesanal"],
            "ITALIANO-RUSTICO": ["pao", "italiano", "levain", "rustico", "artesanal"],
            "CAMPAGNE-OVAL": ["pao", "campagne", "levain", "integral", "centeio"],
            "CAMPAGNE-REDONDO": ["pao", "campagne", "levain", "integral", "centeio"],
            "CAMPAGNE-PASSAS": ["pao", "campagne", "levain", "passas", "castanhas", "especial"],
            "CIABATTA": ["pao", "italiano", "levain", "azeite", "aerado"],
            "PAO-FORMA": ["pao", "forma", "japones", "macio", "fatiado"],
            "CHALLAH": ["pao", "tranca", "judaico", "gergelim", "doce"],
            "PAO-HAMBURGER": ["pao", "hamburger", "levain", "individual"],
            "FOCACCIA-ALECRIM": ["focaccia", "italiano", "azeite", "alecrim", "ervas"],
            "FOCACCIA-CEBOLA": ["focaccia", "italiano", "azeite", "cebola", "azeitona"],
            "FOCACCIA-BACON": ["focaccia", "italiano", "azeite", "bacon", "queijo"],
            "MINI-FOCACCIA-ALECRIM": ["focaccia", "italiano", "mini", "alecrim", "individual"],
            "MINI-FOCACCIA-CEBOLA": ["focaccia", "italiano", "mini", "cebola", "azeitona"],
            "MINI-FOCACCIA-BACON": ["focaccia", "italiano", "mini", "bacon", "queijo"],
            "BRIOCHE": ["brioche", "frances", "manteiga", "doce", "macio"],
            "BRIOCHE-BURGER": ["brioche", "hamburger", "manteiga", "ovos"],
            "PAO-HOTDOG": ["pao", "hotdog", "manteiga", "salgado"],
            "CROISSANT": ["croissant", "folhado", "manteiga", "frances"],
            "PAIN-CHOCOLAT": ["croissant", "folhado", "chocolate", "frances"],
            "MINI-CROISSANT": ["croissant", "folhado", "mini", "doce"],
            "CHAUSSON": ["folhado", "maca", "canela", "frances", "doce"],
            "BICHON": ["folhado", "limao", "creme", "frances", "doce"],
            "CORNET-CHOCOLATE": ["pao-doce", "chocolate", "creme", "recheado"],
            "CORNET": ["pao-doce", "creme", "recheado", "amanteigado"],
            "MELON-PAN": ["pao-doce", "japones", "crocante", "amanteigado"],
            "PAIN-RAISINS": ["brioche", "passas", "creme", "frances", "doce"],
            "BRIOCHE-CHOCOLAT": ["brioche", "chocolate", "gotas", "doce", "macio"],
            "MADELEINE": ["bolinho", "frances", "classico", "doce"],
            "DELI": ["salgado", "recheado", "milho", "bacon", "queijo"],
            "HOTDOG": ["salgado", "recheado", "salsicha", "viena", "quente"],
            "CROQUE-MONSIEUR": ["lanche", "sanduiche", "frances", "presunto", "queijo", "gratinado"],
            "CROQUE-MADAME": ["lanche", "sanduiche", "frances", "ovo", "queijo", "gratinado"],
            "QUICHE-LORRAINE": ["lanche", "quiche", "bacon", "queijo", "torta"],
            "QUICHE-LEGUMES": ["lanche", "quiche", "vegetariano", "legumes", "torta"],
            "TARTINE-SAUMON": ["lanche", "tartine", "salmao", "cream-cheese", "frio"],
            "TARTINE-TOMATE": ["lanche", "tartine", "burrata", "tomate", "vegetariano"],
            "ESPRESSO": ["cafe", "espresso", "bebida", "quente"],
            "ESPRESSO-DUPLO": ["cafe", "espresso", "duplo", "bebida", "quente"],
            "CAPPUCCINO": ["cafe", "cappuccino", "leite", "bebida", "quente"],
            "LATTE": ["cafe", "latte", "leite", "bebida", "quente"],
            "CHOCOLATE-QUENTE": ["chocolate", "bebida", "quente", "leite"],
            "CHA-EARL-GREY": ["cha", "earl-grey", "bebida", "quente"],
            "SUCO-LARANJA": ["suco", "laranja", "natural", "bebida", "frio"],
        }

        products = {}
        for sku, name, desc, price_q, unit, shelf_life, sellable, image, weight_g, storage in products_data:
            p, _ = Product.objects.update_or_create(
                sku=sku,
                defaults={
                    "name": name,
                    "short_description": desc,
                    "base_price_q": price_q,
                    "unit": unit,
                    "shelf_life_days": shelf_life,
                    "is_published": True,
                    "is_sellable": sellable,
                    "image_url": image,
                    "unit_weight_g": weight_g,
                    "storage_tip": storage,
                },
            )
            if sku in keywords_map:
                p.keywords.add(*keywords_map[sku])
            products[sku] = p

        # Bundle: Combo Petit Dejeuner (Croissant + Mini Baguete)
        combo, _ = Product.objects.update_or_create(
            sku="COMBO-PETIT-DEJ",
            defaults={
                "name": "Combo Petit Déjeuner",
                "short_description": "Croissant + Mini Baguete (economia de R$ 3,00)",
                "base_price_q": 1900,
                "unit": "un",
                "is_published": True,
                "is_sellable": True,
                "image_url": f"{IMG}/ct.jpg",
            },
        )
        combo.keywords.add("combo", "cafe-da-manha", "promocao")
        products["COMBO-PETIT-DEJ"] = combo

        # Direct-override ingredients + nutrition (products without Recipe).
        # Exercises the "manual override" path of the PDP data schema:
        # ``auto_filled=False`` in nutrition_facts blocks any later derivation.
        DIRECT_OVERRIDES = {
            "SUCO-LARANJA": {
                "ingredients_text": (
                    "Laranja natural. CONTÉM: naturalmente açúcares da fruta. "
                    "Sem adição de açúcar ou conservantes."
                ),
                "nutrition_facts": {
                    "serving_size_g": 200,
                    "servings_per_container": 1,
                    "energy_kcal": 90.0,
                    "carbohydrates_g": 21.0,
                    "sugars_g": 17.0,
                    "proteins_g": 1.4,
                    "total_fat_g": 0.4,
                    "saturated_fat_g": 0.0,
                    "trans_fat_g": 0.0,
                    "fiber_g": 0.5,
                    "sodium_mg": 2.0,
                    "auto_filled": False,
                },
            },
            "CHOCOLATE-QUENTE": {
                "ingredients_text": (
                    "Chocolate belga 54% cacau, leite integral, açúcar. "
                    "CONTÉM: leite, soja. PODE CONTER: glúten, amendoim (contaminação cruzada)."
                ),
                "nutrition_facts": {
                    "serving_size_g": 240,
                    "servings_per_container": 1,
                    "energy_kcal": 310.0,
                    "carbohydrates_g": 36.0,
                    "sugars_g": 30.0,
                    "proteins_g": 8.5,
                    "total_fat_g": 14.0,
                    "saturated_fat_g": 9.0,
                    "trans_fat_g": 0.0,
                    "fiber_g": 2.0,
                    "sodium_mg": 80.0,
                    "auto_filled": False,
                },
            },
        }
        for sku, payload in DIRECT_OVERRIDES.items():
            if sku in products:
                p = products[sku]
                p.ingredients_text = payload["ingredients_text"]
                p.nutrition_facts = payload["nutrition_facts"]
                p.save(update_fields=["ingredients_text", "nutrition_facts"])

        # D-1 eligible: breads that can be sold next day at discount
        d1_skus = ["BAGUETE", "BATARD", "CIABATTA", "FENDU", "TABATIERE", "PAO-HAMBURGER"]
        for sku in d1_skus:
            p = products[sku]
            p.metadata["allows_next_day_sale"] = True
            p.save(update_fields=["metadata"])

        # Bundle components
        ProductComponent.objects.filter(parent=combo).delete()
        ProductComponent.objects.create(parent=combo, component=products["CROISSANT"], qty=Decimal("1"))
        ProductComponent.objects.create(parent=combo, component=products["MINI-BAGUETE"], qty=Decimal("1"))

        # Collections
        col_paes, _ = Collection.objects.update_or_create(
            ref="paes-artesanais",
            defaults={"name": "Pães Artesanais", "is_active": True, "sort_order": 1},
        )
        col_focaccias, _ = Collection.objects.update_or_create(
            ref="focaccias",
            defaults={"name": "Focaccias", "is_active": True, "sort_order": 2},
        )
        col_brioches, _ = Collection.objects.update_or_create(
            ref="brioches",
            defaults={"name": "Brioches & Pães Especiais", "is_active": True, "sort_order": 3},
        )
        col_folhados, _ = Collection.objects.update_or_create(
            ref="croissants-folhados",
            defaults={"name": "Croissants & Folhados", "is_active": True, "sort_order": 4},
        )
        col_doces, _ = Collection.objects.update_or_create(
            ref="paes-doces",
            defaults={"name": "Pães Doces & Recheados", "is_active": True, "sort_order": 5},
        )
        col_salgados, _ = Collection.objects.update_or_create(
            ref="salgados",
            defaults={"name": "Salgados", "is_active": True, "sort_order": 6},
        )
        col_lanches, _ = Collection.objects.update_or_create(
            ref="lanches",
            defaults={"name": "Lanches & Tartines", "is_active": True, "sort_order": 7},
        )
        col_cafes, _ = Collection.objects.update_or_create(
            ref="cafes-bebidas",
            defaults={"name": "Cafes & Bebidas", "is_active": True, "sort_order": 8},
        )
        col_combos, _ = Collection.objects.update_or_create(
            ref="combos",
            defaults={"name": "Combos", "is_active": True, "sort_order": 9},
        )

        all_cols = [col_paes, col_focaccias, col_brioches, col_folhados, col_doces, col_salgados, col_lanches, col_cafes, col_combos]
        CollectionItem.objects.filter(collection__in=all_cols).delete()

        paes_skus = [
            "BAGUETE", "BAGUETE-CAMPAGNE", "BAGUETE-GERGELIM", "MINI-BAGUETE",
            "BATARD", "FENDU", "TABATIERE", "ITALIANO-RUSTICO",
            "CAMPAGNE-OVAL", "CAMPAGNE-REDONDO", "CAMPAGNE-PASSAS",
            "CIABATTA", "PAO-FORMA", "CHALLAH", "PAO-HAMBURGER",
        ]
        for i, sku in enumerate(paes_skus):
            CollectionItem.objects.create(
                collection=col_paes, product=products[sku], sort_order=i, is_primary=True,
            )

        focaccias_skus = [
            "FOCACCIA-ALECRIM", "FOCACCIA-CEBOLA", "FOCACCIA-BACON",
            "MINI-FOCACCIA-ALECRIM", "MINI-FOCACCIA-CEBOLA", "MINI-FOCACCIA-BACON",
        ]
        for i, sku in enumerate(focaccias_skus):
            CollectionItem.objects.create(
                collection=col_focaccias, product=products[sku], sort_order=i, is_primary=True,
            )

        brioches_skus = ["BRIOCHE", "BRIOCHE-BURGER", "PAO-HOTDOG"]
        for i, sku in enumerate(brioches_skus):
            CollectionItem.objects.create(
                collection=col_brioches, product=products[sku], sort_order=i, is_primary=True,
            )

        folhados_skus = ["CROISSANT", "PAIN-CHOCOLAT", "MINI-CROISSANT", "CHAUSSON", "BICHON"]
        for i, sku in enumerate(folhados_skus):
            CollectionItem.objects.create(
                collection=col_folhados, product=products[sku], sort_order=i, is_primary=True,
            )

        doces_skus = ["CORNET-CHOCOLATE", "CORNET", "MELON-PAN", "PAIN-RAISINS", "BRIOCHE-CHOCOLAT", "MADELEINE"]
        for i, sku in enumerate(doces_skus):
            CollectionItem.objects.create(
                collection=col_doces, product=products[sku], sort_order=i, is_primary=True,
            )

        salgados_skus = ["DELI", "HOTDOG"]
        for i, sku in enumerate(salgados_skus):
            CollectionItem.objects.create(
                collection=col_salgados, product=products[sku], sort_order=i, is_primary=True,
            )

        lanches_skus = [
            "CROQUE-MONSIEUR", "CROQUE-MADAME",
            "QUICHE-LORRAINE", "QUICHE-LEGUMES",
            "TARTINE-SAUMON", "TARTINE-TOMATE",
        ]
        for i, sku in enumerate(lanches_skus):
            CollectionItem.objects.create(
                collection=col_lanches, product=products[sku], sort_order=i, is_primary=True,
            )

        cafes_skus = [
            "ESPRESSO", "ESPRESSO-DUPLO", "CAPPUCCINO", "LATTE",
            "CHOCOLATE-QUENTE", "CHA-EARL-GREY", "SUCO-LARANJA",
        ]
        for i, sku in enumerate(cafes_skus):
            CollectionItem.objects.create(
                collection=col_cafes, product=products[sku], sort_order=i, is_primary=True,
            )

        CollectionItem.objects.create(
            collection=col_combos, product=products["COMBO-PETIT-DEJ"], sort_order=0, is_primary=True,
        )

        # Listings
        pdv, _ = Listing.objects.update_or_create(
            ref="pdv",
            defaults={"name": "PDV", "is_active": True, "priority": 10},
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
        # iFood uses pricing.policy="external": the marketplace controls final prices,
        # so listing prices are reference-only — no markup stored on our side.
        markup_map = {"pdv": 0, "delivery": 0, "ifood": 0, "web": 0}
        for listing_obj in [pdv, delivery, ifood, web]:
            ListingItem.objects.filter(listing=listing_obj).delete()
            markup = Decimal(markup_map[listing_obj.ref]) / 100
            for _sku, product in products.items():
                price_q = int(product.base_price_q * (1 + markup))
                ListingItem.objects.create(
                    listing=listing_obj,
                    product=product,
                    price_q=price_q,
                    is_published=True,
                    is_sellable=product.is_sellable,
                )

        self.stdout.write(f"  ✅ {len(products)} produtos ({Product.objects.filter(unit_weight_g__isnull=False).count()} com peso), {len(all_cols)} colecoes, 4 listagens")
        return products

    # ────────────────────────────────────────────────────────────────
    # Estoque (Stockman)
    # ────────────────────────────────────────────────────────────────

    def _seed_positions(self):
        self.stdout.write("  📍 Posicoes de estoque...")

        # Ref "ontem": sobras D-1 apos transferencia manual (fim do dia). Estoque com lote D-1
        # deve ficar aqui — canais remotos usam stock.allowed_positions sem "ontem", entao vitrine
        # API e reservas online ignoram esse saldo; PDV (allowed_positions omitido) ve tudo.
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
            "BAGUETE": 25,
            "BAGUETE-CAMPAGNE": 12,
            "BAGUETE-GERGELIM": 10,
            "MINI-BAGUETE": 30,
            "BATARD": 15,
            "FENDU": 40,
            "TABATIERE": 35,
            "ITALIANO-RUSTICO": 8,
            "CAMPAGNE-OVAL": 10,
            "CAMPAGNE-REDONDO": 10,
            "CIABATTA": 20,
            "PAO-FORMA": 12,
            "CHALLAH": 8,
            "PAO-HAMBURGER": 30,
            "FOCACCIA-ALECRIM": 8,
            "FOCACCIA-CEBOLA": 6,
            "FOCACCIA-BACON": 6,
            "MINI-FOCACCIA-ALECRIM": 15,
            "BRIOCHE": 12,
            "BRIOCHE-BURGER": 15,
            "CROISSANT": 40,
            "PAIN-CHOCOLAT": 30,
            "MINI-CROISSANT": 25,
            "CHAUSSON": 12,
            "BICHON": 10,
            "CORNET-CHOCOLATE": 15,
            "CORNET": 12,
            "MELON-PAN": 10,
            "PAIN-RAISINS": 12,
            "MADELEINE": 20,
            "DELI": 15,
            "HOTDOG": 12,
        }

        for sku, qty in stock_data.items():
            if sku in products:
                stock.receive(
                    quantity=Decimal(str(qty)),
                    sku=sku,
                    position=vitrine,
                    reason=f"Estoque inicial seed Nelson: {sku}",
                )

        # D-1 stock (yesterday's leftovers in "ontem" position)
        d1_position = positions["ontem"]
        d1_items = [
            ("BAGUETE", 4),
            ("BATARD", 2),
            ("FENDU", 5),
            ("TABATIERE", 4),
            ("CIABATTA", 3),
            ("PAO-HAMBURGER", 6),
        ]
        for sku, qty in d1_items:
            if sku in products:
                stock.receive(
                    quantity=Decimal(str(qty)),
                    sku=sku,
                    position=d1_position,
                    reason=f"D-1 sobras seed Nelson: {sku}",
                )

        self.stdout.write(f"  ✅ Estoque para {len(stock_data)} produtos + {len(d1_items)} D-1")

    # ────────────────────────────────────────────────────────────────
    # Receitas (Craftsman)
    # ────────────────────────────────────────────────────────────────

    def _seed_recipes(self):
        self.stdout.write("  📋 Receitas...")

        recipes_data = [
            {
                "ref": "baguete",
                "name": "Baguete Francesa",
                "output_sku": "BAGUETE",
                "batch_size": Decimal("25"),
                "items": [
                    ("INS-FARINHA-T65", Decimal("5.000")),
                    ("INS-AGUA", Decimal("3.500")),
                    ("INS-FERMENTO-NAT", Decimal("1.500")),
                    ("INS-SAL", Decimal("0.100")),
                    ("INS-MALTE", Decimal("0.020")),
                ],
            },
            {
                "ref": "baguete-campagne",
                "name": "Baguette de Campagne",
                "output_sku": "BAGUETE-CAMPAGNE",
                "batch_size": Decimal("12"),
                "items": [
                    ("INS-FARINHA-T65", Decimal("2.000")),
                    ("INS-FARINHA-INT", Decimal("2.000")),
                    ("INS-CENTEIO", Decimal("0.500")),
                    ("INS-AGUA", Decimal("3.000")),
                    ("INS-FERMENTO-NAT", Decimal("1.200")),
                    ("INS-SAL", Decimal("0.080")),
                ],
            },
            {
                "ref": "campagne",
                "name": "Pain de Campagne",
                "output_sku": "CAMPAGNE-OVAL",
                "batch_size": Decimal("10"),
                "items": [
                    ("INS-FARINHA-T65", Decimal("2.500")),
                    ("INS-FARINHA-INT", Decimal("2.500")),
                    ("INS-CENTEIO", Decimal("0.600")),
                    ("INS-AGUA", Decimal("3.500")),
                    ("INS-FERMENTO-NAT", Decimal("1.500")),
                    ("INS-SAL", Decimal("0.100")),
                ],
            },
            {
                "ref": "italiano-rustico",
                "name": "Italiano Rustico",
                "output_sku": "ITALIANO-RUSTICO",
                "batch_size": Decimal("8"),
                "items": [
                    ("INS-FARINHA-T65", Decimal("3.500")),
                    ("INS-AGUA", Decimal("2.500")),
                    ("INS-FERMENTO-NAT", Decimal("1.200")),
                    ("INS-SAL", Decimal("0.080")),
                    ("INS-AZEITE", Decimal("0.100")),
                ],
            },
            {
                "ref": "ciabatta",
                "name": "Ciabatta",
                "output_sku": "CIABATTA",
                "batch_size": Decimal("20"),
                "items": [
                    ("INS-FARINHA-T55", Decimal("3.000")),
                    ("INS-AGUA", Decimal("2.400")),
                    ("INS-AZEITE", Decimal("0.200")),
                    ("INS-FERMENTO-NAT", Decimal("0.900")),
                    ("INS-SAL", Decimal("0.060")),
                ],
            },
            {
                "ref": "focaccia-alecrim",
                "name": "Focaccia Alecrim",
                "output_sku": "FOCACCIA-ALECRIM",
                "batch_size": Decimal("8"),
                "items": [
                    ("INS-FARINHA-T55", Decimal("2.000")),
                    ("INS-AGUA", Decimal("1.500")),
                    ("INS-AZEITE", Decimal("0.300")),
                    ("INS-FERMENTO-NAT", Decimal("0.600")),
                    ("INS-SAL", Decimal("0.040")),
                    ("INS-ALECRIM", Decimal("0.030")),
                ],
            },
            {
                "ref": "focaccia-cebola",
                "name": "Focaccia Cebola Roxa",
                "output_sku": "FOCACCIA-CEBOLA",
                "batch_size": Decimal("6"),
                "items": [
                    ("INS-FARINHA-T55", Decimal("2.000")),
                    ("INS-AGUA", Decimal("1.500")),
                    ("INS-AZEITE", Decimal("0.300")),
                    ("INS-FERMENTO-NAT", Decimal("0.600")),
                    ("INS-CEBOLA-ROXA", Decimal("0.400")),
                    ("INS-AZEITONA", Decimal("0.200")),
                    ("INS-SAL", Decimal("0.040")),
                ],
            },
            {
                "ref": "pao-forma",
                "name": "Pao de Forma Artesanal",
                "output_sku": "PAO-FORMA",
                "batch_size": Decimal("12"),
                "items": [
                    ("INS-FARINHA-T55", Decimal("3.000")),
                    ("INS-MANTEIGA-FR", Decimal("0.400")),
                    ("INS-LEITE", Decimal("1.200")),
                    ("INS-ACUCAR", Decimal("0.200")),
                    ("INS-FERMENTO-BIO", Decimal("0.100")),
                    ("INS-SAL", Decimal("0.060")),
                ],
            },
            {
                "ref": "challah",
                "name": "Challah",
                "output_sku": "CHALLAH",
                "batch_size": Decimal("8"),
                "items": [
                    ("INS-FARINHA-T45", Decimal("2.000")),
                    ("INS-OVOS", Decimal("0.600")),
                    ("INS-ACUCAR", Decimal("0.300")),
                    ("INS-AZEITE", Decimal("0.200")),
                    ("INS-FERMENTO-BIO", Decimal("0.080")),
                    ("INS-SAL", Decimal("0.040")),
                    ("INS-GERGELIM", Decimal("0.050")),
                ],
            },
            {
                "ref": "croissant",
                "name": "Croissant Manteiga",
                "output_sku": "CROISSANT",
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
                "ref": "pain-chocolat",
                "name": "Pain au Chocolat",
                "output_sku": "PAIN-CHOCOLAT",
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
                "ref": "brioche",
                "name": "Brioche Nanterre",
                "output_sku": "BRIOCHE",
                "batch_size": Decimal("12"),
                "items": [
                    ("INS-FARINHA-T45", Decimal("2.000")),
                    ("INS-MANTEIGA-FR", Decimal("1.000")),
                    ("INS-OVOS", Decimal("0.600")),
                    ("INS-ACUCAR", Decimal("0.300")),
                    ("INS-FERMENTO-BIO", Decimal("0.080")),
                    ("INS-SAL", Decimal("0.040")),
                ],
            },
            {
                "ref": "chausson",
                "name": "Chausson aux Pommes",
                "output_sku": "CHAUSSON",
                "batch_size": Decimal("12"),
                "items": [
                    ("INS-FARINHA-T45", Decimal("1.500")),
                    ("INS-MANTEIGA-FR", Decimal("0.800")),
                    ("INS-MACA", Decimal("0.600")),
                    ("INS-ACUCAR", Decimal("0.200")),
                    ("INS-CANELA", Decimal("0.010")),
                ],
            },
            {
                "ref": "madeleine",
                "name": "Madeleine",
                "output_sku": "MADELEINE",
                "batch_size": Decimal("24"),
                "items": [
                    ("INS-FARINHA-T45", Decimal("0.500")),
                    ("INS-MANTEIGA-FR", Decimal("0.500")),
                    ("INS-OVOS", Decimal("0.400")),
                    ("INS-ACUCAR", Decimal("0.300")),
                    ("INS-LIMAO", Decimal("0.020")),
                ],
            },
        ]

        # Perfil nutricional por insumo (valores aproximados por 100g).
        # Alimenta RecipeItem.meta e, via signal, materializa
        # Product.nutrition_facts + Product.ingredients_text no PDP.
        # Ref: TACO / USDA simplificado — valores didáticos.
        INGREDIENT_PROFILES = {
            "INS-FARINHA-T65":  {"label": "Farinha de trigo T65",   "nutrition": {"energy_kcal": 364, "carbohydrates_g": 76, "sugars_g": 0.3, "proteins_g": 10, "total_fat_g": 1.0, "saturated_fat_g": 0.2, "trans_fat_g": 0, "fiber_g": 2.7, "sodium_mg": 2}},
            "INS-FARINHA-T55":  {"label": "Farinha de trigo T55",   "nutrition": {"energy_kcal": 364, "carbohydrates_g": 76, "sugars_g": 0.3, "proteins_g": 10, "total_fat_g": 1.0, "saturated_fat_g": 0.2, "trans_fat_g": 0, "fiber_g": 2.7, "sodium_mg": 2}},
            "INS-FARINHA-T45":  {"label": "Farinha de trigo T45",   "nutrition": {"energy_kcal": 364, "carbohydrates_g": 76, "sugars_g": 0.3, "proteins_g": 10, "total_fat_g": 1.0, "saturated_fat_g": 0.2, "trans_fat_g": 0, "fiber_g": 2.7, "sodium_mg": 2}},
            "INS-FARINHA-INT":  {"label": "Farinha de trigo integral", "nutrition": {"energy_kcal": 340, "carbohydrates_g": 72, "sugars_g": 0.4, "proteins_g": 13, "total_fat_g": 2.5, "saturated_fat_g": 0.4, "trans_fat_g": 0, "fiber_g": 10.7, "sodium_mg": 2}},
            "INS-CENTEIO":      {"label": "Farinha de centeio",     "nutrition": {"energy_kcal": 338, "carbohydrates_g": 76, "sugars_g": 1.0, "proteins_g": 10, "total_fat_g": 1.7, "saturated_fat_g": 0.2, "trans_fat_g": 0, "fiber_g": 15.0, "sodium_mg": 2}},
            "INS-AGUA":         {"label": "Água",                   "nutrition": {"energy_kcal": 0,   "carbohydrates_g": 0,  "sugars_g": 0,   "proteins_g": 0,  "total_fat_g": 0,   "saturated_fat_g": 0,   "trans_fat_g": 0, "fiber_g": 0,    "sodium_mg": 0}},
            "INS-FERMENTO-NAT": {"label": "Fermento natural (levain)", "nutrition": {"energy_kcal": 220, "carbohydrates_g": 45, "sugars_g": 0.5, "proteins_g": 7,  "total_fat_g": 0.5, "saturated_fat_g": 0.1, "trans_fat_g": 0, "fiber_g": 1.8,  "sodium_mg": 5}},
            "INS-FERMENTO-BIO": {"label": "Fermento biológico",     "nutrition": {"energy_kcal": 105, "carbohydrates_g": 12, "sugars_g": 0,   "proteins_g": 13, "total_fat_g": 1.5, "saturated_fat_g": 0.2, "trans_fat_g": 0, "fiber_g": 8.1,  "sodium_mg": 30}},
            "INS-SAL":          {"label": "Sal marinho",            "nutrition": {"energy_kcal": 0,   "carbohydrates_g": 0,  "sugars_g": 0,   "proteins_g": 0,  "total_fat_g": 0,   "saturated_fat_g": 0,   "trans_fat_g": 0, "fiber_g": 0,    "sodium_mg": 38758}},
            "INS-ACUCAR":       {"label": "Açúcar",                 "nutrition": {"energy_kcal": 387, "carbohydrates_g": 100, "sugars_g": 100, "proteins_g": 0, "total_fat_g": 0,   "saturated_fat_g": 0,   "trans_fat_g": 0, "fiber_g": 0,    "sodium_mg": 1}},
            "INS-MANTEIGA-FR":  {"label": "Manteiga francesa",      "nutrition": {"energy_kcal": 717, "carbohydrates_g": 0.1, "sugars_g": 0.1, "proteins_g": 0.9, "total_fat_g": 81, "saturated_fat_g": 51,  "trans_fat_g": 3.3, "fiber_g": 0,  "sodium_mg": 11}},
            "INS-LEITE":        {"label": "Leite integral",         "nutrition": {"energy_kcal": 61,  "carbohydrates_g": 4.8, "sugars_g": 4.8, "proteins_g": 3.2, "total_fat_g": 3.3, "saturated_fat_g": 1.9, "trans_fat_g": 0.1, "fiber_g": 0,  "sodium_mg": 40}},
            "INS-OVOS":         {"label": "Ovos",                   "nutrition": {"energy_kcal": 155, "carbohydrates_g": 1.1, "sugars_g": 1.1, "proteins_g": 13,  "total_fat_g": 11,  "saturated_fat_g": 3.3, "trans_fat_g": 0,   "fiber_g": 0,  "sodium_mg": 124}},
            "INS-AZEITE":       {"label": "Azeite extra virgem",    "nutrition": {"energy_kcal": 884, "carbohydrates_g": 0,   "sugars_g": 0,   "proteins_g": 0,  "total_fat_g": 100, "saturated_fat_g": 14,  "trans_fat_g": 0,   "fiber_g": 0,  "sodium_mg": 2}},
            "INS-MALTE":        {"label": "Malte",                  "nutrition": {"energy_kcal": 360, "carbohydrates_g": 78, "sugars_g": 60,  "proteins_g": 10, "total_fat_g": 1.8, "saturated_fat_g": 0.3, "trans_fat_g": 0,   "fiber_g": 7,  "sodium_mg": 23}},
            "INS-CHOCOLATE-70": {"label": "Chocolate amargo 70%",   "nutrition": {"energy_kcal": 598, "carbohydrates_g": 46, "sugars_g": 24,  "proteins_g": 7.8, "total_fat_g": 43, "saturated_fat_g": 24,  "trans_fat_g": 0,   "fiber_g": 11, "sodium_mg": 20}},
            "INS-CEBOLA-ROXA":  {"label": "Cebola roxa",            "nutrition": {"energy_kcal": 40,  "carbohydrates_g": 9,   "sugars_g": 4.2, "proteins_g": 1.1, "total_fat_g": 0.1, "saturated_fat_g": 0,   "trans_fat_g": 0,   "fiber_g": 1.7, "sodium_mg": 4}},
            "INS-AZEITONA":     {"label": "Azeitonas pretas",       "nutrition": {"energy_kcal": 115, "carbohydrates_g": 6.3, "sugars_g": 0,   "proteins_g": 0.8, "total_fat_g": 10.7, "saturated_fat_g": 1.4, "trans_fat_g": 0,  "fiber_g": 3.2, "sodium_mg": 735}},
            "INS-ALECRIM":      {"label": "Alecrim",                "nutrition": {"energy_kcal": 131, "carbohydrates_g": 21, "sugars_g": 0,   "proteins_g": 3.3, "total_fat_g": 5.9, "saturated_fat_g": 2.8, "trans_fat_g": 0,   "fiber_g": 14, "sodium_mg": 26}},
            "INS-GERGELIM":     {"label": "Gergelim",               "nutrition": {"energy_kcal": 573, "carbohydrates_g": 23, "sugars_g": 0.3, "proteins_g": 18,  "total_fat_g": 50, "saturated_fat_g": 7,   "trans_fat_g": 0,   "fiber_g": 12, "sodium_mg": 11}},
            "INS-MACA":         {"label": "Maçã",                   "nutrition": {"energy_kcal": 52,  "carbohydrates_g": 14, "sugars_g": 10,  "proteins_g": 0.3, "total_fat_g": 0.2, "saturated_fat_g": 0,   "trans_fat_g": 0,   "fiber_g": 2.4, "sodium_mg": 1}},
            "INS-CANELA":       {"label": "Canela",                 "nutrition": {"energy_kcal": 247, "carbohydrates_g": 81, "sugars_g": 2.2, "proteins_g": 4,   "total_fat_g": 1.2, "saturated_fat_g": 0.3, "trans_fat_g": 0,   "fiber_g": 53, "sodium_mg": 10}},
            "INS-LIMAO":        {"label": "Limão",                  "nutrition": {"energy_kcal": 29,  "carbohydrates_g": 9,  "sugars_g": 2.5, "proteins_g": 1.1, "total_fat_g": 0.3, "saturated_fat_g": 0,   "trans_fat_g": 0,   "fiber_g": 2.8, "sodium_mg": 2}},
        }

        for rd in recipes_data:
            recipe, _ = Recipe.objects.update_or_create(
                ref=rd["ref"],
                defaults={
                    "name": rd["name"],
                    "output_sku": rd["output_sku"],
                    "batch_size": rd["batch_size"],
                },
            )
            RecipeItem.objects.filter(recipe=recipe).delete()
            for input_sku, qty in rd["items"]:
                meta = INGREDIENT_PROFILES.get(input_sku, {})
                RecipeItem.objects.create(
                    recipe=recipe,
                    input_sku=input_sku,
                    quantity=qty,
                    meta=meta,
                )

        # Work orders — use CraftService to exercise the full signal chain
        # (production_changed → planned quants → inventory protocol)
        #
        # Nelson's production schedule (realistic):
        #   BAGUETE:           start 04:00, finish ~06:00  → slot-09
        #   BAGUETE-CAMPAGNE:  start 04:00, finish ~06:30  → slot-09
        #   CAMPAGNE-OVAL:     start 03:30, finish ~08:00  → slot-09
        #   ITALIANO-RUSTICO:  start 03:30, finish ~08:30  → slot-09
        #   CIABATTA:          start 05:00, finish ~07:00  → slot-09
        #   PAO-FORMA:         start 05:00, finish ~07:30  → slot-09
        #   CHALLAH:           start 05:00, finish ~08:00  → slot-09
        #   CROISSANT:         start 05:00, finish ~07:30  → slot-09
        #   PAIN-CHOCOLAT:     start 05:00, finish ~08:00  → slot-09
        #   BRIOCHE:           start 05:30, finish ~08:30  → slot-09
        #   FOCACCIA-ALECRIM:  start 07:00, finish ~10:00  → slot-12
        #   FOCACCIA-CEBOLA:   start 07:30, finish ~10:30  → slot-12
        #   CHAUSSON:          start 08:00, finish ~11:00  → slot-12
        #   MADELEINE:         start 09:00, finish ~13:00  → slot-15
        from shopman.craftsman.service import CraftService as craft

        today = date.today()
        tomorrow = today + timedelta(days=1)
        tz_info = timezone.get_current_timezone()

        # Production schedule: (recipe_ref, qty, start_hour, start_min, finish_hour, finish_min)
        PRODUCTION_SCHEDULE = [
            ("baguete",          Decimal("25"),  4, 0,  6, 0),
            ("croissant",        Decimal("48"),  5, 0,  7, 30),
            ("focaccia-alecrim", Decimal("8"),   7, 0,  10, 0),
        ]

        # Typical finish times per SKU (for historical WOs — covers ALL products with recipes)
        TYPICAL_FINISH = {
            "BAGUETE":          (6, 0),
            "BAGUETE-CAMPAGNE": (6, 30),
            "CAMPAGNE-OVAL":    (8, 0),
            "ITALIANO-RUSTICO": (8, 30),
            "CIABATTA":         (7, 0),
            "PAO-FORMA":        (7, 30),
            "CHALLAH":          (8, 0),
            "CROISSANT":        (7, 30),
            "PAIN-CHOCOLAT":    (8, 0),
            "BRIOCHE":          (8, 30),
            "FOCACCIA-ALECRIM": (10, 0),
            "FOCACCIA-CEBOLA":  (10, 30),
            "CHAUSSON":         (11, 0),
            "MADELEINE":        (13, 0),
        }

        wo_count = 0

        # Today: 2 finished (via craft.plan + craft.finish) + 1 planned
        for ref, qty, sh, sm, fh, fm in PRODUCTION_SCHEDULE:
            recipe = Recipe.objects.get(ref=ref)
            existing = WorkOrder.objects.filter(
                recipe=recipe, target_date=today,
            ).first()
            if existing:
                wo_count += 1
                continue

            wo = craft.plan(recipe, quantity=qty, date=today, position_ref="vitrine")
            should_finish = ref != "focaccia-alecrim"  # focaccia still in production
            if should_finish:
                finished = int(qty * Decimal("0.95"))
                craft.finish(wo, finished=finished, actor="seed")
            # Set realistic timestamps
            start_dt = datetime.combine(today, time(sh, sm), tzinfo=tz_info)
            finish_dt = datetime.combine(today, time(fh, fm), tzinfo=tz_info) if should_finish else None
            WorkOrder.objects.filter(pk=wo.pk).update(
                started_at=start_dt,
                **({"finished_at": finish_dt} if finish_dt else {}),
            )
            wo_count += 1

        # Tomorrow: 4 planned orders (via craft.plan → creates planned quants)
        for ref, qty in [
            ("baguete", Decimal("30")),
            ("baguete-campagne", Decimal("15")),
            ("croissant", Decimal("60")),
            ("focaccia-alecrim", Decimal("10")),
        ]:
            recipe = Recipe.objects.get(ref=ref)
            existing = WorkOrder.objects.filter(
                recipe=recipe, target_date=tomorrow,
            ).first()
            if existing:
                wo_count += 1
                continue

            craft.plan(recipe, quantity=qty, date=tomorrow, position_ref="vitrine")
            wo_count += 1

        # Historical production (last 35 days) — one WO per product per day
        # This feeds the pickup slot service's median calculation and craft.suggest()
        recipes_by_output = {r.output_sku: r for r in Recipe.objects.all()}
        history_count = 0
        for days_ago in range(1, 36):
            wo_date = today - timedelta(days=days_ago)
            # Skip Mondays (Nelson está fechado)
            if wo_date.weekday() == 0:
                continue
            for sku, (fh, fm) in TYPICAL_FINISH.items():
                recipe = recipes_by_output.get(sku)
                if not recipe:
                    continue
                if WorkOrder.objects.filter(recipe=recipe, target_date=wo_date).exists():
                    continue
                # Add ±15min jitter to make data realistic
                jitter = random.randint(-15, 15)
                finish_minutes = fh * 60 + fm + jitter
                finish_h = max(0, min(23, finish_minutes // 60))
                finish_m = max(0, min(59, finish_minutes % 60))
                start_h = max(0, finish_h - 2)  # ~2h before finish
                qty = recipe.batch_size or Decimal("20")
                finished = int(qty * Decimal(str(random.uniform(0.90, 0.98))))
                finish_dt = datetime.combine(wo_date, time(finish_h, finish_m), tzinfo=tz_info)

                wo = WorkOrder.objects.create(
                    recipe=recipe,
                    output_sku=sku,
                    quantity=qty,
                    finished=Decimal(str(finished)),
                    status=WorkOrder.Status.FINISHED,
                    target_date=wo_date,
                    started_at=datetime.combine(wo_date, time(start_h, 0), tzinfo=tz_info),
                    finished_at=finish_dt,
                    position_ref=recipe.output_sku,
                )

                # Waste: ~25% of WOs have some waste (5-15% of finished_qty)
                if random.random() < 0.25:
                    waste_qty = Decimal(str(round(finished * random.uniform(0.05, 0.15))))
                    if waste_qty > 0:
                        WorkOrderItem.objects.create(
                            work_order=wo,
                            kind=WorkOrderItem.Kind.WASTE,
                            item_ref=sku,
                            quantity=waste_qty,
                            unit="un",
                            recorded_at=finish_dt,
                            recorded_by="seed",
                            meta={"reason": "perda natural — não vendido"},
                        )

                history_count += 1
            wo_count += 1

        self.stdout.write(
            f"  ✅ {len(recipes_data)} receitas, {wo_count} ordens de producao"
            f" + {history_count} historico (35 dias — pickup slots + suggest)"
        )

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
            extras = {}
            if ref == "CLI-001":
                extras["birthday"] = date.today()
            c, _ = Customer.objects.update_or_create(
                ref=ref,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "customer_type": ctype,
                    "group": group,
                    "phone": phone,
                    **extras,
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
    # Canais (Orderman)
    # ────────────────────────────────────────────────────────────────

    def _seed_channels(self):
        self.stdout.write("  📡 Canais...")

        channels = {}
        _pos_config = {
            "confirmation": {"mode": "immediate"},
            "payment": {"method": "cash", "timing": "external"},
            "stock": {"check_on_commit": True},
            "handle_label": "Comanda",
            "handle_placeholder": "Ex: 42",
        }
        # Remote: D-1 (posição "ontem") é staff-only — visível apenas no balcão.
        # Usamos excluded_positions (denylist) para que posições novas herdem
        # visibilidade automaticamente e só precisemos listar o que é de fato
        # restrito.
        _remote_stock = {
            "excluded_positions": ["ontem"],
            "hold_ttl_minutes": 30,
        }
        _remote_config = {
            "confirmation": {"mode": "auto_confirm", "timeout_minutes": 5},
            "payment": {"method": ["pix", "card"], "timing": "post_commit", "timeout_minutes": 15},
            "stock": _remote_stock,
        }
        _marketplace_config = {
            "confirmation": {"mode": "manual", "stale_new_alert_minutes": 30},
            "payment": {"method": "external", "timing": "external"},
            "stock": {**_remote_stock, "check_on_commit": True},
        }
        _whatsapp_config = {
            "confirmation": {"mode": "auto_confirm", "timeout_minutes": 5},
            "payment": {"method": ["pix", "card"], "timeout_minutes": 15},
            "notifications": {"backend": "manychat"},
            "stock": _remote_stock,
        }
        channels_data = [
            # (ref, name, kind, config_overrides)
            ("pdv", "PDV", "pos", _pos_config),
            ("delivery", "Delivery Proprio", "web", _remote_config),
            ("ifood", "iFood", "ifood", {
                **_marketplace_config,
                "pricing": {"policy": "external"},
                "editing": {"policy": "locked"},
            }),
            ("whatsapp", "WhatsApp", "whatsapp", _whatsapp_config),
            ("web", "E-commerce", "web", _remote_config),
        ]

        for ref, name, kind, config_data in channels_data:
            ch, _ = Channel.objects.update_or_create(
                ref=ref,
                defaults={
                    "name": name,
                    "kind": kind,
                    "is_active": True,
                    "config": config_data,
                },
            )
            channels[ref] = ch

        self.stdout.write(f"  ✅ {len(channels)} canais")
        return channels

    # ────────────────────────────────────────────────────────────────
    # Pedidos (Orderman)
    # ────────────────────────────────────────────────────────────────

    def _seed_orders(self, products, customers, channels):
        self.stdout.write("  🛒 Pedidos...")

        now = timezone.now()
        order_count = 0
        customer_list = list(customers.values())
        product_list = list(products.values())
        channel_list = [channels["pdv"], channels["delivery"], channels["whatsapp"]]

        # Seasonal demand multiplier based on current month
        current_month = now.month
        if current_month in (10, 11, 12, 1, 2, 3):   # hot season
            season_multiplier = 1.1
        elif current_month in (6, 7, 8):               # cold season
            season_multiplier = 1.2
        else:                                           # mild
            season_multiplier = 1.0

        for days_ago in range(35):  # 5 weeks of history
            day = now - timedelta(days=days_ago)
            weekday = day.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun

            # Skip Mondays (boulangerie típica)
            if weekday == 0:
                continue

            # Base order count
            base_orders = random.randint(8, 15) if days_ago < 2 else random.randint(5, 10)

            # Weekday multiplier
            if weekday in (4, 5):    # Fri, Sat — alta demanda
                day_mult = 1.3
            elif weekday == 6:        # Sun — menor demanda e fecha mais cedo
                day_mult = 0.7
            else:
                day_mult = 1.0

            num_orders = max(1, int(base_orders * day_mult * season_multiplier))

            for _ in range(num_orders):
                channel = random.choice(channel_list)
                customer = random.choice(customer_list)
                # Sunday closes at 13:00; others close at 19:00
                max_hour = 12 if weekday == 6 else 18

                if days_ago == 0:
                    # Only completed orders from earlier today (morning hours)
                    morning_ceiling = max(7, now.hour - 2)
                    if morning_ceiling <= 7:
                        continue  # too early in the day — no completed history yet
                    hour = random.randint(7, morning_ceiling)
                    minute = random.randint(0, 59)
                    status = "completed"
                else:
                    hour = random.randint(7, max_hour)
                    minute = random.randint(0, 59)
                    status = "completed"

                order_time = day.replace(hour=hour, minute=minute, second=0, microsecond=0)

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
                    channel_ref=channel.ref,
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

                if status in ("confirmed", "preparing", "ready", "completed"):
                    OrderEvent.objects.create(
                        order=order,
                        type="status_change",
                        seq=1,
                        payload={"new_status": "confirmed"},
                        created_at=order_time + timedelta(minutes=2),
                    )

                if status in ("preparing", "ready", "completed"):
                    OrderEvent.objects.create(
                        order=order,
                        type="status_change",
                        seq=2,
                        payload={"new_status": "preparing"},
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

        # ── Live orders — timestamps in minutes, not hours ────────────────
        # These represent what's happening RIGHT NOW in the kitchen/counter.
        live_specs = [
            ("preparing", random.randint(5, 15)),
            ("preparing", random.randint(5, 15)),
            ("confirmed",  random.randint(2, 5)),
            ("confirmed",  random.randint(2, 5)),
            ("new",        random.randint(1, 3)),
            ("new",        random.randint(1, 4)),
            ("ready",      1),
        ]
        # 50% chance of a pending PIX order
        if random.random() < 0.5:
            live_specs.append(("new", random.randint(3, 5)))

        for live_status, minutes_ago in live_specs:
            channel = random.choice(channel_list)
            customer = random.choice(customer_list)
            order_time = now - timedelta(minutes=minutes_ago)

            num_items = random.randint(1, 3)
            selected_products = random.sample(product_list, min(num_items, len(product_list)))

            items_data = []
            total_q = 0
            for prod in selected_products:
                qty = random.randint(1, 3)
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
            cp = customer.contact_points.filter(type="whatsapp").first()
            handle_ref = cp.value_normalized if cp else ""

            order = Order.objects.create(
                ref=ref,
                channel_ref=channel.ref,
                status=live_status,
                total_q=total_q,
                handle_type="phone",
                handle_ref=handle_ref,
                created_at=order_time,
            )

            for item in items_data:
                OrderItem.objects.create(
                    order=order,
                    line_id=f"L-{uuid.uuid4().hex[:8]}",
                    sku=item["sku"],
                    name=item["name"],
                    qty=Decimal(str(item["qty"])),
                    unit_price_q=item["unit_price_q"],
                    line_total_q=item["line_total_q"],
                )

            # Events: realistic minute progression
            OrderEvent.objects.create(
                order=order,
                type="status_change",
                seq=0,
                payload={"new_status": "new"},
                created_at=order_time,
            )

            if live_status in ("confirmed", "preparing", "ready"):
                OrderEvent.objects.create(
                    order=order,
                    type="status_change",
                    seq=1,
                    payload={"new_status": "confirmed"},
                    created_at=order_time + timedelta(minutes=1),
                )

            if live_status in ("preparing", "ready"):
                OrderEvent.objects.create(
                    order=order,
                    type="status_change",
                    seq=2,
                    payload={"new_status": "preparing"},
                    created_at=order_time + timedelta(minutes=2),
                )

                from shopman.shop.kds_utils import dispatch_to_kds
                tickets = dispatch_to_kds(order)

                if live_status == "ready":
                    OrderEvent.objects.create(
                        order=order,
                        type="status_change",
                        seq=3,
                        payload={"new_status": "ready"},
                        created_at=order_time + timedelta(minutes=3),
                    )
                    for ticket in tickets:
                        ticket.status = "done"
                        ticket.completed_at = order_time + timedelta(minutes=3)
                        ticket.save(update_fields=["status", "completed_at"])

            order_count += 1

        # ── iFood demo orders ─────────────────────────────────────────────────
        if "ifood" in channels:
            ifood_ch = channels["ifood"]
            prod_a = product_list[0]
            prod_b = product_list[1] if len(product_list) > 1 else product_list[0]

            # Order 1: new iFood order (just arrived, awaiting confirmation)
            ref_new = f"NB-{uuid.uuid4().hex[:8].upper()}"
            order_new = Order.objects.create(
                ref=ref_new,
                channel_ref=ifood_ch.ref,
                status="new",
                total_q=prod_a.base_price_q * 2,
                handle_type="phone",
                handle_ref="",
                created_at=now - timedelta(minutes=2),
                data={
                    "customer": {"name": "Camila iFood"},
                    "payment": {"method": "external", "timing": "external"},
                    "fulfillment_type": "delivery",
                    "availability_decision": {"approved": True, "source": "seed", "decisions": []},
                },
            )
            OrderItem.objects.create(
                order=order_new,
                line_id=f"L-{uuid.uuid4().hex[:8]}",
                sku=prod_a.sku,
                name=prod_a.name,
                qty=Decimal("2"),
                unit_price_q=prod_a.base_price_q,
                line_total_q=prod_a.base_price_q * 2,
            )
            OrderEvent.objects.create(
                order=order_new,
                type="status_change",
                seq=0,
                payload={"new_status": "new"},
                created_at=now - timedelta(minutes=2),
            )

            # Order 2: confirmed iFood order (in queue, being handled)
            ref_confirmed = f"NB-{uuid.uuid4().hex[:8].upper()}"
            order_confirmed = Order.objects.create(
                ref=ref_confirmed,
                channel_ref=ifood_ch.ref,
                status="confirmed",
                total_q=prod_b.base_price_q,
                handle_type="phone",
                handle_ref="",
                created_at=now - timedelta(minutes=9),
                data={
                    "customer": {"name": "Rafael iFood"},
                    "payment": {"method": "external", "timing": "external"},
                    "fulfillment_type": "delivery",
                    "availability_decision": {"approved": True, "source": "seed", "decisions": []},
                },
            )
            OrderItem.objects.create(
                order=order_confirmed,
                line_id=f"L-{uuid.uuid4().hex[:8]}",
                sku=prod_b.sku,
                name=prod_b.name,
                qty=Decimal("1"),
                unit_price_q=prod_b.base_price_q,
                line_total_q=prod_b.base_price_q,
            )
            OrderEvent.objects.create(
                order=order_confirmed,
                type="status_change",
                seq=0,
                payload={"new_status": "new"},
                created_at=now - timedelta(minutes=9),
            )
            OrderEvent.objects.create(
                order=order_confirmed,
                type="status_change",
                seq=1,
                payload={"new_status": "confirmed"},
                created_at=now - timedelta(minutes=7),
            )

            order_count += 2
            self.stdout.write("  ✅ 2 pedidos iFood demo adicionados")

        self.stdout.write(f"  ✅ {order_count} pedidos (35 dias + live + iFood)")

    # ────────────────────────────────────────────────────────────────
    # Sessoes abertas (Orderman)
    # ────────────────────────────────────────────────────────────────

    def _seed_sessions(self, channels):
        self.stdout.write("  📝 Sessoes abertas...")

        from shopman.orderman.ids import generate_session_key

        for channel_ref, items in [
            ("pdv", [
                {"line_id": uuid.uuid4().hex[:8], "sku": "CROISSANT", "name": "Croissant Tradicional", "qty": 2, "unit_price_q": 1300, "line_total_q": 2600},
                {"line_id": uuid.uuid4().hex[:8], "sku": "PAIN-CHOCOLAT", "name": "Pain au Chocolat", "qty": 1, "unit_price_q": 1500, "line_total_q": 1500},
            ]),
            ("delivery", [
                {"line_id": uuid.uuid4().hex[:8], "sku": "BAGUETE", "name": "Baguete Francesa", "qty": 3, "unit_price_q": 1300, "line_total_q": 3900},
                {"line_id": uuid.uuid4().hex[:8], "sku": "FOCACCIA-ALECRIM", "name": "Focaccia Alecrim & Sal Grosso", "qty": 1, "unit_price_q": 3100, "line_total_q": 3100},
            ]),
            ("whatsapp", [
                {"line_id": uuid.uuid4().hex[:8], "sku": "BAGUETE", "name": "Baguete Francesa", "qty": 10, "unit_price_q": 1300, "line_total_q": 13000},
                {"line_id": uuid.uuid4().hex[:8], "sku": "CROISSANT", "name": "Croissant Tradicional", "qty": 20, "unit_price_q": 1300, "line_total_q": 26000},
            ]),
        ]:
            ch = channels[channel_ref]
            from shopman.shop.config import ChannelConfig

            cfg = ChannelConfig.for_channel(ch)
            Session.objects.create(
                session_key=generate_session_key(),
                channel_ref=ch.ref,
                state="open",
                pricing_policy=cfg.pricing.policy,
                edit_policy=cfg.editing.policy,
                items=items,
            )

        self.stdout.write("  ✅ 3 sessoes abertas")

    # ────────────────────────────────────────────────────────────────
    # Alertas de estoque (Stockman)
    # ────────────────────────────────────────────────────────────────

    def _seed_stock_alerts(self, products, positions):
        self.stdout.write("  🔔 Alertas de estoque...")

        vitrine = positions["vitrine"]
        alerts_data = [
            ("BAGUETE", 10),
            ("MINI-BAGUETE", 12),
            ("FENDU", 15),
            ("CROISSANT", 15),
            ("PAIN-CHOCOLAT", 12),
            ("BRIOCHE", 6),
            ("FOCACCIA-ALECRIM", 4),
            ("CIABATTA", 8),
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

        # Promotion: Parabéns! — 10% off no dia do aniversário
        Promotion.objects.update_or_create(
            name="Parabéns! Desconto de aniversário",
            defaults={
                "type": Promotion.PERCENT,
                "value": 10,
                "valid_from": now,
                "valid_until": now + timedelta(days=365),
                "birthday_only": True,
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

        self.stdout.write("  ✅ 6 promotions, 3 coupons")

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

            is_delivery = order.channel_ref in ("delivery", "whatsapp", "web")

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

        # Preparing orders: fulfillment in progress
        for order in Order.objects.filter(status="preparing"):
            if Fulfillment.objects.filter(order=order).exists():
                continue

            is_delivery = order.channel_ref in ("delivery", "whatsapp", "web")

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

        # Stock holds and payments are now handled inline (services.availability +
        # services.stock + services.payment), not via directives. Only notification
        # and fulfillment remain as async directives.
        NOTIFICATION_SEND = "notification.send"
        FULFILLMENT_CREATE = "fulfillment.create"

        count = 0
        for order in Order.objects.filter(status__in=["completed", "delivered", "preparing", "confirmed"]):
            if Directive.objects.filter(payload__order_ref=order.ref).exists():
                continue

            is_terminal = order.status in ("completed", "delivered")
            directive_status = "done" if is_terminal else "queued"
            base_time = order.created_at

            Directive.objects.create(
                topic=NOTIFICATION_SEND,
                status=directive_status,
                payload={"order_ref": order.ref, "template": "order_confirmed"},
                available_at=base_time + timedelta(minutes=2),
            )

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
            from shopman.guestman.contrib.loyalty.service import LoyaltyService
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

        # Get collections for KDS routing
        col_lanches = Collection.objects.filter(ref="lanches").first()
        col_salgados = Collection.objects.filter(ref="salgados").first()
        col_cafes = Collection.objects.filter(ref="cafes-bebidas").first()
        col_paes = Collection.objects.filter(ref="paes-artesanais").first()
        col_focaccias = Collection.objects.filter(ref="focaccias").first()
        col_brioches = Collection.objects.filter(ref="brioches").first()
        col_doces = Collection.objects.filter(ref="paes-doces").first()
        col_folhados = Collection.objects.filter(ref="croissants-folhados").first()
        col_combos = Collection.objects.filter(ref="combos").first()

        # Remove old KDS instances that no longer exist
        KDSInstance.objects.filter(ref__in=["paes", "folhados", "salgados"]).delete()

        # KDS Lanches — Prep: montagem de lanches e salgados na hora
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
        kds_lanches.collections.clear()
        for col in [col_lanches, col_salgados, col_combos]:
            if col:
                kds_lanches.collections.add(col)

        # KDS Cafés — Prep: bebidas quentes e frias
        kds_cafes, _ = KDSInstance.objects.update_or_create(
            ref="cafes",
            defaults={
                "name": "Cafés",
                "type": "prep",
                "target_time_minutes": 3,
                "sound_enabled": True,
                "is_active": True,
            },
        )
        kds_cafes.collections.clear()
        if col_cafes:
            kds_cafes.collections.add(col_cafes)

        # KDS Padaria — Prep: pães, folhados, doces de forno
        kds_padaria, _ = KDSInstance.objects.update_or_create(
            ref="padaria",
            defaults={
                "name": "Padaria",
                "type": "prep",
                "target_time_minutes": 5,
                "sound_enabled": True,
                "is_active": True,
            },
        )
        kds_padaria.collections.clear()
        for col in [col_paes, col_focaccias, col_brioches, col_doces, col_folhados]:
            if col:
                kds_padaria.collections.add(col)

        # KDS Encomendas — Picking: pedidos agendados (future-dated)
        KDSInstance.objects.update_or_create(
            ref="encomendas",
            defaults={
                "name": "Encomendas",
                "type": "picking",
                "target_time_minutes": 5,
                "sound_enabled": True,
                "is_active": True,
            },
        )

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

        self.stdout.write("  ✅ 5 estações KDS (Lanches, Cafés, Padaria, Encomendas, Expedição)")

    # ────────────────────────────────────────────────────────────────
    # Notification Templates
    # ────────────────────────────────────────────────────────────────

    def _seed_notification_templates(self):
        self.stdout.write("  📨 Templates de notificação...")

        from shopman.shop.models import NotificationTemplate

        FALLBACK_TEMPLATES = {
            "order_received": {"subject": "Pedido {order_ref} recebido", "body": "Ola{customer_name_greeting}! Recebemos seu pedido *{order_ref}*. Ja estamos olhando com carinho e logo confirmamos. Total: *{total}*."},
            "order_received_outside_hours": {"subject": "Pedido {order_ref} recebido", "body": "Ola{customer_name_greeting}! Recebemos seu pedido *{order_ref}* fora do nosso horario de atendimento. Vamos processar assim que abrirmos. Total: *{total}*."},
            "order_confirmed": {"subject": "Pedido {order_ref} confirmado", "body": "Ola{customer_name_greeting}! Seu pedido *{order_ref}* foi confirmado. Total: *{total}*.\n\nObrigado pela preferencia!"},
            "order_preparing": {"subject": "Pedido {order_ref} em preparo", "body": "Ola{customer_name_greeting}! Seu pedido *{order_ref}* esta sendo preparado.\n\nAvisaremos quando estiver pronto!"},
            "order_ready_pickup": {"subject": "Pedido {order_ref} pronto para retirada", "body": "Ola{customer_name_greeting}! Seu pedido *{order_ref}* esta pronto para retirada! \U0001f389\n\nVenha buscar. Obrigado!"},
            "order_ready_delivery": {"subject": "Pedido {order_ref} pronto para envio", "body": "Ola{customer_name_greeting}! Seu pedido *{order_ref}* esta pronto e sera enviado em breve! \U0001f4e6"},
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
                "rule_path": "shopman.shop.rules.pricing.D1Rule",
                "label": "Desconto D-1 (sobras)",
                "params": {"discount_percent": 50},
                "priority": 15,
            },
            {
                "code": "promotion_discount",
                "rule_path": "shopman.shop.rules.pricing.PromotionRule",
                "label": "Promoções e Cupons",
                "params": {},
                "priority": 20,
            },
            {
                "code": "employee_discount",
                "rule_path": "shopman.shop.rules.pricing.EmployeeRule",
                "label": "Desconto Funcionário",
                "params": {"discount_percent": 20, "group": "staff"},
                "priority": 60,
            },
            {
                "code": "happy_hour",
                "rule_path": "shopman.shop.rules.pricing.HappyHourRule",
                "label": "Hora da Xepa",
                "params": {"discount_percent": 25, "start": "17:30", "end": "18:00"},
                "priority": 65,
            },
            {
                "code": "business_hours",
                "rule_path": "shopman.shop.rules.validation.BusinessHoursRule",
                "label": "Horário de Funcionamento",
                "params": {},
                "priority": 10,
            },
            {
                "code": "minimum_order",
                "rule_path": "shopman.shop.rules.validation.MinimumOrderRule",
                "label": "Pedido Mínimo Delivery",
                "params": {"minimum_q": 2500},
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

    # ────────────────────────────────────────────────────────────────
    # DayClosing (fechamento do dia)
    # ────────────────────────────────────────────────────────────────

    def _seed_day_closing(self):
        self.stdout.write("  📊 Fechamento do dia...")

        yesterday = timezone.localdate() - timedelta(days=1)
        admin = User.objects.filter(is_superuser=True).first()
        if not admin:
            self.stdout.write("  ⏭️  Sem superuser, pulando DayClosing")
            return

        _, created = DayClosing.objects.update_or_create(
            date=yesterday,
            defaults={
                "closed_by": admin,
                "notes": "Fechamento automatico (seed)",
                "data": [
                    {"sku": "BAGUETE", "qty_remaining": 6, "qty_d1": 4, "qty_loss": 2},
                    {"sku": "BATARD", "qty_remaining": 3, "qty_d1": 2, "qty_loss": 1},
                    {"sku": "FENDU", "qty_remaining": 7, "qty_d1": 5, "qty_loss": 2},
                    {"sku": "TABATIERE", "qty_remaining": 5, "qty_d1": 4, "qty_loss": 1},
                    {"sku": "CIABATTA", "qty_remaining": 4, "qty_d1": 3, "qty_loss": 1},
                    {"sku": "PAO-HAMBURGER", "qty_remaining": 8, "qty_d1": 6, "qty_loss": 2},
                ],
            },
        )
        self.stdout.write("  ✅ DayClosing criado" if created else "  ✅ DayClosing atualizado")

    # ────────────────────────────────────────────────────────────────
    # CashRegisterSession (caixa)
    # ────────────────────────────────────────────────────────────────

    def _seed_cash_register(self):
        self.stdout.write("  💵 Sessoes de caixa...")

        admin = User.objects.filter(is_superuser=True).first()
        if not admin:
            self.stdout.write("  ⏭️  Sem superuser, pulando CashRegister")
            return

        yesterday = timezone.localdate() - timedelta(days=1)
        yesterday_open = timezone.make_aware(datetime.combine(yesterday, time(8, 30)))
        yesterday_close = timezone.make_aware(datetime.combine(yesterday, time(18, 15)))

        # Yesterday's closed session
        session_yesterday, _ = CashRegisterSession.objects.update_or_create(
            operator=admin,
            opened_at=yesterday_open,
            defaults={
                "status": "closed",
                "closed_at": yesterday_close,
                "opening_amount_q": 20000,   # R$ 200 fundo de troco
                "closing_amount_q": 89200,   # R$ 892 (reported)
                "expected_amount_q": 89500,  # R$ 895 (calculated)
                "difference_q": -300,        # -R$ 3,00 (small shortage)
                "notes": "Dia tranquilo, faltou R$3 no caixa.",
            },
        )

        # Sangria
        CashMovement.objects.update_or_create(
            session=session_yesterday,
            movement_type="sangria",
            defaults={
                "amount_q": 30000,  # R$ 300
                "reason": "Retirada para deposito",
                "created_at": timezone.make_aware(datetime.combine(yesterday, time(14, 0))),
            },
        )

        # Today's open session
        today_open = timezone.make_aware(datetime.combine(timezone.localdate(), time(8, 45)))
        CashRegisterSession.objects.update_or_create(
            operator=admin,
            opened_at=today_open,
            defaults={
                "status": "open",
                "opening_amount_q": 20000,  # R$ 200 fundo de troco
            },
        )

        self.stdout.write("  ✅ 2 sessoes de caixa (ontem fechada + hoje aberta)")
