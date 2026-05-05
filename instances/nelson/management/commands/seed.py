"""
Seed de produção — Nelson Boulangerie.

Popula loja (shop), catálogo (offerman), estoque (stockman), receitas (craftsman),
clientes (customers), canais (orderman) e pedidos com dados da Nelson.

Uso:
    python manage.py seed          # seed normal
    python manage.py seed --flush  # apaga tudo e recria

IMPORTANTE — Não-determinismo deliberado:
    Este seed usa random.choice, uuid4 e now() intencionalmente para gerar dados
    realistas a cada execução. Não é adequado como fixture de testes. Para testes
    determinísticos use TestCase com fixtures ou factories dedicadas.
"""
from __future__ import annotations

import os
import random
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from shopman.craftsman.models import Recipe, RecipeItem, WorkOrder, WorkOrderItem
from shopman.guestman.models import ContactPoint, Customer, CustomerAddress, CustomerGroup
from shopman.offerman.models import (
    AvailabilityPolicy,
    Collection,
    CollectionItem,
    Listing,
    ListingItem,
    Product,
    ProductComponent,
)
from shopman.orderman.ids import generate_order_ref, generate_session_key
from shopman.orderman.models import (
    Directive,
    Fulfillment,
    FulfillmentItem,
    IdempotencyKey,
    Order,
    OrderEvent,
    OrderItem,
    Session,
    SessionItem,
)
from shopman.payman.models import PaymentIntent, PaymentTransaction
from shopman.stockman import stock
from shopman.stockman.models import Position, PositionKind, StockAlert

from shopman.backstage.models import (
    CashMovement,
    CashRegisterSession,
    DayClosing,
    KDSInstance,
    OperatorAlert,
    POSTab,
)
from shopman.shop.models import Channel, OmotenashiCopy, RuleConfig, Shop
from shopman.shop.services.nutrition_from_recipe import fill_nutrition_from_recipe
from shopman.storefront.models import Coupon, Promotion


class Command(BaseCommand):
    help = "Popula o banco com dados de produção da Nelson Boulangerie"

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
        self._assert_catalog_remote_purchase_data()
        customers = self._seed_customers()
        self._seed_addresses(customers)
        channels = self._seed_channels()
        self._assert_storefront_products_orderable()
        self._seed_kds()
        self._seed_pos_tabs()
        self._seed_orders(products, customers, channels)
        self._seed_security_reliability_edges(products, customers, channels)
        self._seed_sessions(channels)
        self._seed_stock_alerts(products, positions)
        self._seed_operator_alerts()
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
                "food_safety_notice": (
                    "Produzido em cozinha compartilhada. Pode conter traços de leite, ovos, "
                    "castanha-do-brasil, castanha de caju, gergelim e pimenta-do-reino."
                ),
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

        def hard_delete(model):
            return model._base_manager.all()._raw_delete(model._base_manager.db)

        # Audit tables are data too in local seeds; keep --flush actually clean.
        for model in [
            Product.history.model,
            ListingItem.history.model,
            RuleConfig.history.model,
            OmotenashiCopy.history.model,
        ]:
            model.objects.all().delete()

        # Payments
        hard_delete(PaymentTransaction)
        PaymentIntent.objects.all().delete()

        # Orderman
        for model in [
            FulfillmentItem,
            Fulfillment,
            Directive,
            OrderEvent,
            OrderItem,
            Order,
            SessionItem,
            Session,
            Channel,
        ]:
            model.objects.all().delete()

        # Offerman
        for model in [ListingItem, Listing, CollectionItem, Collection, ProductComponent, Product]:
            model.objects.all().delete()

        # Stockman
        from shopman.stockman.models import Hold, Move, Quant

        hard_delete(Move)
        for model in [StockAlert, Hold, Quant, Position]:
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

        OperatorAlert.objects.all().delete()
        KDSTicket.objects.all().delete()
        KDSInstance.objects.all().delete()
        POSTab.objects.all().delete()

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
    # Catálogo (Offerman)
    # ────────────────────────────────────────────────────────────────

    def _seed_catalog(self):
        self.stdout.write("  📦 Catálogo...")

        # Catálogo real Nelson Boulangerie
        # Fonte: https://github.com/pablondrina/nb-catalog
        IMG = "https://raw.githubusercontent.com/pablondrina/nb-catalog/main/img/products"
        UNSPLASH = "https://images.unsplash.com"

        def unsplash(photo_id: str) -> str:
            return f"{UNSPLASH}/{photo_id}?auto=format&fit=crop&w=900&q=80"

        # (sku, name, short_desc, price_q, unit, shelf_life, available, image, weight_g, storage_tip)
        products_data = [
            # ── Pães Artesanais (fermentação natural / levain) ──
            ("BAGUETE", "Baguete Francesa", "Pão de tradição francesa e fermentação 100% natural (levain)", 1300, "un", 0, True,
             f"{IMG}/bf.jpg", 250, "Congele inteira ou em pedaços. Reaqueça direto do freezer a 200°C por 8min"),
            ("BAGUETE-CAMPAGNE", "Baguette de Campagne", "Baguete de fermentação natural (levain), trigo 50% integral e centeio orgânico", 1700, "un", 1, True,
             f"{IMG}/cf.jpg", 280, "Guarde em saco de pano. Congele em até 2h para melhor resultado"),
            ("BAGUETE-GERGELIM", "Baguete Gergelim", "Baguete com fermentação 100% natural (levain), toque de azeite e gergelim", 1800, "un", 0, True,
             f"{IMG}/be.jpg", 260, "Congele no mesmo dia. Reaqueça a 200°C por 8min"),
            ("MINI-BAGUETE", "Mini Baguete", "Mini baguete com fermentação 100% natural (levain) e toque de azeite", 900, "un", 0, True,
             f"{IMG}/bap.jpg", 120, "Congele no mesmo dia. Reaqueça a 200°C por 5min"),
            ("BATARD", "Bâtard", "Pão de tradição francesa e fermentação 100% natural (levain) em formato de filão", 1300, "un", 0, True,
             f"{IMG}/ba.jpg", 350, "Guarde em saco de pano. Congele em até 2h"),
            ("FENDU", "Fendu", "Pãozinho de tradição francesa e fermentação 100% natural (levain)", 600, "un", 0, True,
             f"{IMG}/fe.jpg", 100, "Melhor consumido no dia. Congele por até 30 dias"),
            ("TABATIERE", "Tabatiere", "Pãozinho de tradição francesa e fermentação 100% natural (levain)", 600, "un", 0, True,
             f"{IMG}/tb.jpg", 100, "Melhor consumido no dia. Congele por até 30 dias"),
            ("ITALIANO-RUSTICO", "Italiano Rústico", "Pão tradicional com fermentação 100% natural (levain)", 2200, "un", 1, True,
             f"{IMG}/bax.jpg", 400, "Guarde em saco de pano. Dura até 3 dias em temperatura ambiente"),
            ("CAMPAGNE-OVAL", "Pain de Campagne (Oval)", "Fermentação natural (levain), trigo 50% integral e centeio orgânico", 1800, "un", 2, True,
             f"{IMG}/cgo.jpg", 500, "Guarde em saco de pano. Dura até 4 dias em temperatura ambiente"),
            ("CAMPAGNE-REDONDO", "Pain de Campagne (Redondo)", "Fermentação natural (levain), trigo 50% integral e centeio orgânico", 1800, "un", 2, True,
             f"{IMG}/cgr.jpg", 500, "Guarde em saco de pano. Dura até 4 dias em temperatura ambiente"),
            ("CAMPAGNE-PASSAS", "Campagne Passas & Castanhas", "Levain, trigo 50% integral e centeio orgânico, passas, castanhas de caju e do Pará", 3300, "un", 3, True,
             f"{IMG}/cpx.jpg", 550, "Guarde em saco de pano. Dura até 5 dias em temperatura ambiente"),
            ("CIABATTA", "Ciabatta", "Pão aerado, clássico italiano com azeite extra virgem e fermentação 100% natural (levain)", 1400, "un", 0, True,
             f"{IMG}/ci.jpg", 200, "Congele no mesmo dia. Reaqueça a 200°C por 8min"),
            ("PAO-FORMA", "Pão de Forma Artesanal", "Super macio ao estilo japonês. Vem com 6 fatias grossas", 1800, "un", 2, True,
             f"{IMG}/fa.jpg", 400, "Mantenha em saco plástico fechado. Congela bem por até 30 dias"),
            ("CHALLAH", "Challah", "Trança fofinha e levemente adocicada, decorada com gergelim", 1800, "un", 2, True,
             f"{IMG}/ch.jpg", 350, "Mantenha em saco plástico fechado. Congela bem por até 30 dias"),
            ("PAO-HAMBURGER", "Pão de Hambúrguer", "Pão de tradição francesa e fermentação 100% natural (levain)", 600, "un", 0, True,
             f"{IMG}/ph.jpg", 100, "Melhor consumido no dia. Congele por até 30 dias"),
            # ── Focaccias ──
            ("FOCACCIA-ALECRIM", "Focaccia Alecrim & Sal Grosso", "Clássico italiano, alecrim fresco e sal grosso, regada com azeite extra virgem", 3100, "un", 0, True,
             f"{IMG}/foa.jpg", 450, "Congele em porções. Reaqueça a 200°C por 5min com um fio de azeite"),
            ("FOCACCIA-CEBOLA", "Focaccia Cebola Roxa & Azeitonas", "Cebola roxa e azeitonas pretas, regada com azeite extra virgem", 4000, "un", 0, True,
             f"{IMG}/foc.jpg", 500, "Congele em porções. Reaqueça a 200°C por 5min"),
            ("FOCACCIA-BACON", "Focaccia Bacon, Cebola & Tomilho", "Cebola, bacon, tomilho e queijo minas, regada com azeite extra virgem", 4000, "un", 0, True,
             f"{IMG}/cbt.jpg", 500, "Congele em porções. Reaqueça a 200°C por 5min"),
            ("MINI-FOCACCIA-ALECRIM", "Mini Focaccia Alecrim & Sal Grosso", "Versão individual, alecrim fresco e sal grosso, regada com azeite extra virgem", 1300, "un", 0, True,
             f"{IMG}/mif.jpg", 150, "Melhor consumida no dia. Reaqueça a 200°C por 3min"),
            ("MINI-FOCACCIA-CEBOLA", "Mini Focaccia Cebola Roxa & Azeitonas", "Versão individual, cebola roxa e azeitonas pretas", 1800, "un", 0, True,
             f"{IMG}/mifoc.jpg", 160, "Melhor consumida no dia. Reaqueça a 200°C por 3min"),
            ("MINI-FOCACCIA-BACON", "Mini Focaccia Bacon, Cebola & Tomilho", "Versão individual, cebola, bacon, tomilho e queijo minas", 1800, "un", 0, True,
             f"{IMG}/micbt.jpg", 160, "Melhor consumida no dia. Reaqueça a 200°C por 3min"),
            # ── Brioches & Pães Especiais ──
            ("BRIOCHE", "Brioche Nanterre", "Super leve e levemente adocicado", 2200, "un", 2, True,
             f"{IMG}/bn.jpg", 350, "Mantenha em saco plástico fechado. Congela bem por até 30 dias"),
            ("BRIOCHE-BURGER", "Brioche Burger Bun (pc. 2un.)", "Super leve, riquíssimo em ovos e manteiga", 1600, "un", 1, True,
             f"{IMG}/bbb.jpg", 200, "Congele no mesmo dia. Reaqueça a 180°C por 5min"),
            ("PAO-HOTDOG", "Pão para Hot Dog (pc. 4un.)", "Pão amanteigado, bom para cachorro quente", 2800, "un", 1, True,
             f"{IMG}/pho.jpg", 320, "Congele no mesmo dia por até 30 dias"),
            # ── Croissants & Folhados ──
            ("CROISSANT", "Croissant Tradicional", "Clássico em pura manteiga. Simples e delicioso. Ótimo com geleias!", 1300, "un", 1, True,
             f"{IMG}/ct.jpg", 80, "Reaqueça no forno a 180°C por 5min para recuperar a crocância"),
            ("PAIN-CHOCOLAT", "Pain au Chocolat", "Croissant recheado com chocolate!", 1500, "un", 1, True,
             f"{IMG}/pc.jpg", 90, "Reaqueça no forno a 180°C por 5min. Evite micro-ondas"),
            ("MINI-CROISSANT", "Mini Croissant", "Delicioso mini croissant com calda doce", 800, "un", 1, True,
             f"{IMG}/cm.jpg", 40, "Consuma no dia. Reaqueça no forno a 180°C por 3min"),
            ("CHAUSSON", "Chausson aux Pommes", "Clássico folhado em pura manteiga, recheio de maçã & canela da casa", 1800, "un", 1, True,
             f"{IMG}/cn.jpg", 120, "Consuma no dia. Reaqueça no forno a 180°C por 5min"),
            ("BICHON", "Bichon au Citron", "Folhado com creme de limão", 1800, "un", 1, True,
             f"{IMG}/bh.jpg", 110, "Consuma no dia. Reaqueça no forno a 180°C por 5min"),
            # ── Pães Doces & Recheados ──
            ("CORNET-CHOCOLATE", "Cornet Chocolate", "Pão amanteigado em formato de cone, recheio de creme de chocolate", 1100, "un", 1, True,
             f"{IMG}/coc.jpg", 120, "Melhor consumido no dia. Reaqueça a 180°C por 5min"),
            ("CORNET", "Cornet", "Pão amanteigado em formato de cone, recheio de creme", 1000, "un", 1, True,
             f"{IMG}/co.jpg", 120, "Melhor consumido no dia. Reaqueça a 180°C por 5min"),
            ("MELON-PAN", "Melon Pan", "Clássico japonês amanteigado com cobertura crocante e levemente doce", 1100, "un", 1, True,
             f"{IMG}/me.jpg", 100, "Melhor consumido no dia"),
            ("PAIN-RAISINS", "Pain aux Raisins", "Brioche com creme e uvas passas", 1100, "un", 1, True,
             f"{IMG}/pr.jpg", 110, "Consuma no dia. Reaqueça no forno a 180°C por 5min"),
            ("BRIOCHE-CHOCOLAT", "Brioche Chocolat", "Briochinho super macio com gotas de chocolate", 1000, "un", 1, True,
             f"{IMG}/bch.jpg", 90, "Melhor consumido no dia"),
            ("MADELEINE", "Madeleine", "Bolinho clássico francês, simples e delicioso", 600, "un", 2, True,
             f"{IMG}/md.jpg", 40, "Conserve em recipiente fechado por até 3 dias"),
            # ── Salgados & Recheados ──
            ("DELI", "Deli", "Pão amanteigado recheado com milho, bacon & queijo minas", 1900, "un", 0, True,
             f"{IMG}/dl.jpg", 180, "Melhor consumido quente, no dia"),
            ("HOTDOG", "Hot Dog", "Pão amanteigado recheado com salsicha viena artesanal", 1500, "un", 0, True,
             f"{IMG}/ho.jpg", 180, "Melhor consumido quente, no dia"),
            # ── Lanches (montados na hora) ──
            ("CROQUE-MONSIEUR", "Croque Monsieur", "Clássico sanduíche francês gratinado com presunto e queijo gruyere", 2400, "un", 0, True,
             unsplash("photo-1621188988504-f2a8ff685801"), 250, "Servir quente, imediatamente"),
            ("CROQUE-MADAME", "Croque Madame", "Croque monsieur com ovo pochado por cima", 2800, "un", 0, True,
             unsplash("photo-1621188988280-67c8d6e130a6"), 290, "Servir quente, imediatamente"),
            ("QUICHE-LORRAINE", "Quiche Lorraine", "Quiche clássica de bacon, queijo e cebola", 1800, "un", 0, True,
             unsplash("photo-1647275556041-ab0395841a38"), 200, "Melhor consumido quente, no dia"),
            ("QUICHE-LEGUMES", "Quiche de Legumes", "Quiche vegetariana com abobrinha, tomate e queijo", 1800, "un", 0, True,
             unsplash("photo-1647275555893-0536f9990b45"), 200, "Melhor consumido quente, no dia"),
            ("TARTINE-SAUMON", "Tartine Saumon", "Fatia de campagne com cream cheese, salmão defumado e alcaparras", 2600, "un", 0, True,
             unsplash("photo-1600856042179-a78ff49793fd"), 220, "Servir frio, consumir no dia"),
            ("TARTINE-TOMATE", "Tartine Tomate & Burrata", "Fatia de campagne com tomate, burrata e manjericão", 2200, "un", 0, True,
             unsplash("photo-1580638149300-65f0b9e8fbff"), 200, "Servir frio, consumir no dia"),
            # ── Cafés e Bebidas ──
            ("ESPRESSO", "Espresso", "Café espresso puro, grão especial torrado artesanal", 800, "un", None, True,
             unsplash("photo-1508088405209-fbd63b6a4f50"), 0, ""),
            ("ESPRESSO-DUPLO", "Espresso Duplo", "Dose dupla de espresso", 1000, "un", None, True,
             unsplash("photo-1507133750040-4a8f57021571"), 0, ""),
            ("CAPPUCCINO", "Cappuccino", "Espresso com leite vaporizado e espuma cremosa", 1200, "un", None, True,
             unsplash("photo-1506372023823-741c83b836fe"), 0, ""),
            ("LATTE", "Café Latte", "Espresso com bastante leite vaporizado", 1200, "un", None, True,
             unsplash("photo-1541167760496-1628856ab772"), 0, ""),
            ("CHOCOLATE-QUENTE", "Chocolate Quente", "Chocolate belga com leite vaporizado", 1400, "un", None, True,
             unsplash("photo-1542990253-0d0f5be5f0ed"), 0, ""),
            ("CHA-EARL-GREY", "Chá Earl Grey", "Chá preto com bergamota, servido em bule", 900, "un", None, True,
             unsplash("photo-1544787219-7f47ccb76574"), 0, ""),
            ("SUCO-LARANJA", "Suco de Laranja", "Suco natural de laranja espremido na hora", 1200, "un", None, True,
             unsplash("photo-1612783322374-2e8d108a6299"), 0, ""),
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

        # PDP metadata for remote purchase confidence. These are display-ready,
        # approximate values; ingredients/nutrition are materialized separately.
        PDP_METADATA = {
            "BAGUETE": {
                "allergens": ["glúten"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "2 pessoas",
                "approx_dimensions": "aprox. 55 x 6 x 5 cm",
            },
            "BAGUETE-CAMPAGNE": {
                "allergens": ["glúten"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "2 a 3 pessoas",
                "approx_dimensions": "aprox. 45 x 7 x 6 cm",
            },
            "BAGUETE-GERGELIM": {
                "allergens": ["glúten", "gergelim"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "2 pessoas",
                "approx_dimensions": "aprox. 55 x 6 x 5 cm",
            },
            "MINI-BAGUETE": {
                "allergens": ["glúten"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 26 x 5 x 4 cm",
            },
            "BATARD": {
                "allergens": ["glúten"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "2 a 3 pessoas",
                "approx_dimensions": "aprox. 28 x 10 x 8 cm",
            },
            "FENDU": {
                "allergens": ["glúten"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 12 x 8 x 5 cm",
            },
            "TABATIERE": {
                "allergens": ["glúten"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 12 x 8 x 5 cm",
            },
            "ITALIANO-RUSTICO": {
                "allergens": ["glúten"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "2 a 4 pessoas",
                "approx_dimensions": "aprox. 24 x 12 x 10 cm",
            },
            "CAMPAGNE-OVAL": {
                "allergens": ["glúten"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "3 a 5 pessoas",
                "approx_dimensions": "aprox. 28 x 16 x 10 cm",
            },
            "CAMPAGNE-REDONDO": {
                "allergens": ["glúten"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "3 a 5 pessoas",
                "approx_dimensions": "aprox. 18 cm de diâmetro",
            },
            "CAMPAGNE-PASSAS": {
                "allergens": ["glúten", "castanhas"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "4 a 6 pessoas",
                "approx_dimensions": "aprox. 28 x 16 x 10 cm",
            },
            "CIABATTA": {
                "allergens": ["glúten"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "1 a 2 pessoas",
                "approx_dimensions": "aprox. 20 x 10 x 4 cm",
            },
            "PAO-FORMA": {
                "allergens": ["glúten", "leite"],
                "dietary_info": ["vegetariano"],
                "serves": "6 fatias grossas",
                "approx_dimensions": "aprox. 18 x 10 x 10 cm",
            },
            "CHALLAH": {
                "allergens": ["glúten", "ovos", "gergelim"],
                "dietary_info": ["sem lactose", "vegetariano"],
                "serves": "3 a 4 pessoas",
                "approx_dimensions": "aprox. 28 x 12 x 8 cm",
            },
            "PAO-HAMBURGER": {
                "allergens": ["glúten"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 10 cm de diâmetro",
            },
            "FOCACCIA-ALECRIM": {
                "allergens": ["glúten"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "4 a 6 pessoas",
                "approx_dimensions": "aprox. 24 x 18 x 4 cm",
            },
            "FOCACCIA-CEBOLA": {
                "allergens": ["glúten"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "4 a 6 pessoas",
                "approx_dimensions": "aprox. 24 x 18 x 4 cm",
            },
            "FOCACCIA-BACON": {
                "allergens": ["glúten", "leite"],
                "dietary_info": [],
                "serves": "4 a 6 pessoas",
                "approx_dimensions": "aprox. 24 x 18 x 4 cm",
            },
            "MINI-FOCACCIA-ALECRIM": {
                "allergens": ["glúten"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 12 x 10 x 3 cm",
            },
            "MINI-FOCACCIA-CEBOLA": {
                "allergens": ["glúten"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 12 x 10 x 3 cm",
            },
            "MINI-FOCACCIA-BACON": {
                "allergens": ["glúten", "leite"],
                "dietary_info": [],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 12 x 10 x 3 cm",
            },
            "BRIOCHE": {
                "allergens": ["glúten", "leite", "ovos"],
                "dietary_info": ["vegetariano"],
                "serves": "3 a 4 pessoas",
                "approx_dimensions": "aprox. 22 x 10 x 9 cm",
            },
            "BRIOCHE-BURGER": {
                "allergens": ["glúten", "leite", "ovos"],
                "dietary_info": ["vegetariano"],
                "serves": "2 unidades",
                "approx_dimensions": "aprox. 10 cm de diâmetro cada",
            },
            "PAO-HOTDOG": {
                "allergens": ["glúten", "leite", "ovos"],
                "dietary_info": ["vegetariano"],
                "serves": "4 unidades",
                "approx_dimensions": "aprox. 16 x 5 x 4 cm cada",
            },
            "CROISSANT": {
                "allergens": ["glúten", "leite", "ovos"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 12 x 8 x 5 cm",
            },
            "PAIN-CHOCOLAT": {
                "allergens": ["glúten", "leite", "ovos", "soja"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 11 x 7 x 4 cm",
            },
            "MINI-CROISSANT": {
                "allergens": ["glúten", "leite", "ovos"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 8 x 5 x 4 cm",
            },
            "CHAUSSON": {
                "allergens": ["glúten", "leite"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 12 x 9 x 4 cm",
            },
            "BICHON": {
                "allergens": ["glúten", "leite"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 12 x 7 x 4 cm",
            },
            "CORNET-CHOCOLATE": {
                "allergens": ["glúten", "leite", "ovos", "soja"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 13 x 6 x 6 cm",
            },
            "CORNET": {
                "allergens": ["glúten", "leite", "ovos"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 13 x 6 x 6 cm",
            },
            "MELON-PAN": {
                "allergens": ["glúten", "leite", "ovos"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 10 cm de diâmetro",
            },
            "PAIN-RAISINS": {
                "allergens": ["glúten", "leite", "ovos"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 10 cm de diâmetro",
            },
            "BRIOCHE-CHOCOLAT": {
                "allergens": ["glúten", "leite", "ovos", "soja"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 10 x 6 x 5 cm",
            },
            "MADELEINE": {
                "allergens": ["glúten", "leite", "ovos"],
                "dietary_info": ["vegetariano"],
                "serves": "1 unidade",
                "approx_dimensions": "aprox. 8 x 5 x 3 cm",
            },
            "DELI": {
                "allergens": ["glúten", "leite", "ovos"],
                "dietary_info": [],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 13 x 7 x 5 cm",
            },
            "HOTDOG": {
                "allergens": ["glúten", "leite", "ovos"],
                "dietary_info": [],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 16 x 6 x 5 cm",
            },
            "CROQUE-MONSIEUR": {
                "allergens": ["glúten", "leite"],
                "dietary_info": [],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 16 x 12 x 5 cm",
            },
            "CROQUE-MADAME": {
                "allergens": ["glúten", "leite", "ovos"],
                "dietary_info": [],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 16 x 12 x 7 cm",
            },
            "QUICHE-LORRAINE": {
                "allergens": ["glúten", "leite", "ovos"],
                "dietary_info": [],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 12 cm de diâmetro",
            },
            "QUICHE-LEGUMES": {
                "allergens": ["glúten", "leite", "ovos"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 12 cm de diâmetro",
            },
            "TARTINE-SAUMON": {
                "allergens": ["glúten", "leite", "peixe"],
                "dietary_info": [],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 18 x 9 x 5 cm",
            },
            "TARTINE-TOMATE": {
                "allergens": ["glúten", "leite"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 18 x 9 x 5 cm",
            },
            "ESPRESSO": {
                "allergens": [],
                "dietary_info": ["100% vegetal", "sem glúten", "sem lactose"],
                "serves": "1 xícara de 40 ml",
            },
            "ESPRESSO-DUPLO": {
                "allergens": [],
                "dietary_info": ["100% vegetal", "sem glúten", "sem lactose"],
                "serves": "1 xícara de 80 ml",
            },
            "CAPPUCCINO": {
                "allergens": ["leite"],
                "dietary_info": ["vegetariano", "sem glúten"],
                "serves": "1 xícara de 180 ml",
            },
            "LATTE": {
                "allergens": ["leite"],
                "dietary_info": ["vegetariano", "sem glúten"],
                "serves": "1 xícara de 240 ml",
            },
            "CHOCOLATE-QUENTE": {
                "allergens": ["leite", "soja"],
                "dietary_info": ["vegetariano"],
                "serves": "1 xícara de 240 ml",
            },
            "CHA-EARL-GREY": {
                "allergens": [],
                "dietary_info": ["100% vegetal", "sem glúten", "sem lactose"],
                "serves": "1 bule individual",
            },
            "SUCO-LARANJA": {
                "allergens": [],
                "dietary_info": ["100% vegetal", "sem glúten", "sem lactose"],
                "serves": "1 copo de 200 ml",
            },
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
                    "availability_policy": AvailabilityPolicy.PLANNED_OK,
                    "image_url": image,
                    "unit_weight_g": weight_g,
                    "storage_tip": storage,
                },
            )
            if sku in keywords_map:
                p.keywords.add(*keywords_map[sku])
            if sku in PDP_METADATA:
                metadata = p.metadata if isinstance(p.metadata, dict) else {}
                p.metadata = {**metadata, **PDP_METADATA[sku]}
                p.save(update_fields=["metadata"])
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
                "availability_policy": AvailabilityPolicy.DEMAND_OK,
                "image_url": f"{IMG}/ct.jpg",
            },
        )
        combo.keywords.add("combo", "cafe-da-manha", "promocao")
        combo.metadata = {
            **(combo.metadata if isinstance(combo.metadata, dict) else {}),
            "allergens": ["glúten", "leite", "ovos"],
            "dietary_info": ["vegetariano"],
            "serves": "1 pessoa",
            "approx_dimensions": "1 croissant + 1 mini baguete",
        }
        combo.save(update_fields=["metadata"])
        products["COMBO-PETIT-DEJ"] = combo

        made_to_order_skus = [
            "CROQUE-MONSIEUR",
            "CROQUE-MADAME",
            "TARTINE-SAUMON",
            "TARTINE-TOMATE",
            "ESPRESSO",
            "ESPRESSO-DUPLO",
            "CAPPUCCINO",
            "LATTE",
            "CHOCOLATE-QUENTE",
            "CHA-EARL-GREY",
            "SUCO-LARANJA",
        ]
        for sku in made_to_order_skus:
            product = products.get(sku)
            if product:
                product.availability_policy = AvailabilityPolicy.DEMAND_OK
                product.save(update_fields=["availability_policy"])

        # Direct-override ingredients + nutrition (products without Recipe).
        # Exercises the "manual override" path of the PDP data schema:
        # ``auto_filled=False`` in nutrition_facts blocks any later derivation.
        def nutrition(
            serving_size_g,
            servings_per_container,
            energy_kcal,
            carbohydrates_g,
            sugars_g,
            proteins_g,
            total_fat_g,
            saturated_fat_g,
            fiber_g,
            sodium_mg,
        ):
            return {
                "serving_size_g": serving_size_g,
                "servings_per_container": servings_per_container,
                "energy_kcal": energy_kcal,
                "carbohydrates_g": carbohydrates_g,
                "sugars_g": sugars_g,
                "proteins_g": proteins_g,
                "total_fat_g": total_fat_g,
                "saturated_fat_g": saturated_fat_g,
                "trans_fat_g": 0.0,
                "fiber_g": fiber_g,
                "sodium_mg": sodium_mg,
                "auto_filled": False,
            }

        DIRECT_OVERRIDES = {
            "BAGUETE-GERGELIM": {
                "ingredients_text": (
                    "Farinha de trigo, água, fermento natural, gergelim, azeite extra virgem, sal. "
                    "CONTÉM: glúten e gergelim."
                ),
                "nutrition_facts": nutrition(100, 3, 265.0, 49.0, 1.5, 8.5, 3.8, 0.5, 3.1, 430.0),
            },
            "MINI-BAGUETE": {
                "ingredients_text": (
                    "Farinha de trigo, água, fermento natural, azeite extra virgem, sal. "
                    "CONTÉM: glúten."
                ),
                "nutrition_facts": nutrition(100, 1, 245.0, 50.0, 1.4, 8.0, 1.4, 0.2, 2.5, 420.0),
            },
            "BATARD": {
                "ingredients_text": (
                    "Farinha de trigo, água, fermento natural, sal. "
                    "CONTÉM: glúten."
                ),
                "nutrition_facts": nutrition(100, 4, 240.0, 50.0, 1.2, 8.0, 1.0, 0.2, 2.4, 430.0),
            },
            "FENDU": {
                "ingredients_text": (
                    "Farinha de trigo, água, fermento natural, sal. "
                    "CONTÉM: glúten."
                ),
                "nutrition_facts": nutrition(100, 1, 240.0, 50.0, 1.2, 8.0, 1.0, 0.2, 2.4, 430.0),
            },
            "TABATIERE": {
                "ingredients_text": (
                    "Farinha de trigo, água, fermento natural, sal. "
                    "CONTÉM: glúten."
                ),
                "nutrition_facts": nutrition(100, 1, 240.0, 50.0, 1.2, 8.0, 1.0, 0.2, 2.4, 430.0),
            },
            "CAMPAGNE-REDONDO": {
                "ingredients_text": (
                    "Farinha de trigo, farinha de trigo integral, água, fermento natural, farinha de centeio, sal. "
                    "CONTÉM: glúten."
                ),
                "nutrition_facts": nutrition(100, 5, 235.0, 46.0, 1.5, 8.3, 1.3, 0.2, 4.0, 390.0),
            },
            "CAMPAGNE-PASSAS": {
                "ingredients_text": (
                    "Farinha de trigo, farinha de trigo integral, água, fermento natural, uvas-passas, "
                    "castanha de caju, castanha-do-pará, farinha de centeio, sal. "
                    "CONTÉM: glúten e castanhas."
                ),
                "nutrition_facts": nutrition(100, 6, 275.0, 48.0, 10.0, 8.0, 5.5, 0.8, 4.2, 340.0),
            },
            "PAO-HAMBURGER": {
                "ingredients_text": (
                    "Farinha de trigo, água, fermento natural, azeite extra virgem, sal. "
                    "CONTÉM: glúten."
                ),
                "nutrition_facts": nutrition(100, 1, 245.0, 50.0, 1.4, 8.0, 1.4, 0.2, 2.5, 420.0),
            },
            "FOCACCIA-BACON": {
                "ingredients_text": (
                    "Farinha de trigo, água, fermento natural, azeite extra virgem, cebola, bacon, queijo minas, "
                    "tomilho, sal. CONTÉM: glúten e leite."
                ),
                "nutrition_facts": nutrition(100, 5, 300.0, 38.0, 2.0, 10.0, 12.0, 3.5, 2.0, 620.0),
            },
            "MINI-FOCACCIA-ALECRIM": {
                "ingredients_text": (
                    "Farinha de trigo, água, fermento natural, azeite extra virgem, alecrim fresco, sal grosso. "
                    "CONTÉM: glúten."
                ),
                "nutrition_facts": nutrition(100, 1, 285.0, 42.0, 1.5, 7.0, 9.5, 1.4, 2.0, 560.0),
            },
            "MINI-FOCACCIA-CEBOLA": {
                "ingredients_text": (
                    "Farinha de trigo, água, fermento natural, azeite extra virgem, cebola roxa, azeitonas pretas, sal. "
                    "CONTÉM: glúten."
                ),
                "nutrition_facts": nutrition(100, 1, 290.0, 41.0, 2.0, 7.0, 10.0, 1.5, 2.1, 600.0),
            },
            "MINI-FOCACCIA-BACON": {
                "ingredients_text": (
                    "Farinha de trigo, água, fermento natural, azeite extra virgem, cebola, bacon, queijo minas, "
                    "tomilho, sal. CONTÉM: glúten e leite."
                ),
                "nutrition_facts": nutrition(100, 1, 300.0, 38.0, 2.0, 10.0, 12.0, 3.5, 2.0, 620.0),
            },
            "BRIOCHE-BURGER": {
                "ingredients_text": (
                    "Farinha de trigo, ovos, manteiga, leite, açúcar, fermento biológico, sal. "
                    "CONTÉM: glúten, leite e ovos."
                ),
                "nutrition_facts": nutrition(100, 2, 330.0, 46.0, 8.0, 9.0, 12.0, 7.0, 1.5, 360.0),
            },
            "PAO-HOTDOG": {
                "ingredients_text": (
                    "Farinha de trigo, ovos, manteiga, leite, açúcar, fermento biológico, sal. "
                    "CONTÉM: glúten, leite e ovos."
                ),
                "nutrition_facts": nutrition(80, 4, 265.0, 37.0, 6.0, 7.0, 9.5, 5.5, 1.2, 290.0),
            },
            "MINI-CROISSANT": {
                "ingredients_text": (
                    "Farinha de trigo, manteiga, água, leite, açúcar, ovos, fermento biológico, sal, calda de açúcar. "
                    "CONTÉM: glúten, leite e ovos."
                ),
                "nutrition_facts": nutrition(40, 1, 160.0, 18.0, 5.0, 3.0, 8.5, 5.2, 0.7, 125.0),
            },
            "BICHON": {
                "ingredients_text": (
                    "Massa folhada com manteiga, creme de limão, açúcar. "
                    "CONTÉM: glúten e leite."
                ),
                "nutrition_facts": nutrition(100, 1, 345.0, 41.0, 15.0, 5.5, 17.0, 10.0, 1.4, 220.0),
            },
            "CORNET-CHOCOLATE": {
                "ingredients_text": (
                    "Farinha de trigo, leite, ovos, manteiga, açúcar, creme de chocolate, fermento biológico, sal. "
                    "CONTÉM: glúten, leite, ovos e soja."
                ),
                "nutrition_facts": nutrition(100, 1, 330.0, 45.0, 16.0, 7.0, 13.0, 7.5, 1.8, 260.0),
            },
            "CORNET": {
                "ingredients_text": (
                    "Farinha de trigo, leite, ovos, manteiga, açúcar, creme de confeiteiro, fermento biológico, sal. "
                    "CONTÉM: glúten, leite e ovos."
                ),
                "nutrition_facts": nutrition(100, 1, 315.0, 43.0, 14.0, 7.0, 12.0, 7.0, 1.4, 250.0),
            },
            "MELON-PAN": {
                "ingredients_text": (
                    "Farinha de trigo, leite, ovos, manteiga, açúcar, fermento biológico, sal. "
                    "CONTÉM: glúten, leite e ovos."
                ),
                "nutrition_facts": nutrition(100, 1, 335.0, 52.0, 15.0, 8.0, 10.0, 6.0, 1.5, 250.0),
            },
            "PAIN-RAISINS": {
                "ingredients_text": (
                    "Massa brioche, creme de confeiteiro, uvas-passas. "
                    "CONTÉM: glúten, leite e ovos."
                ),
                "nutrition_facts": nutrition(100, 1, 320.0, 48.0, 18.0, 7.0, 10.0, 5.8, 1.8, 260.0),
            },
            "BRIOCHE-CHOCOLAT": {
                "ingredients_text": (
                    "Farinha de trigo, ovos, manteiga, leite, açúcar, gotas de chocolate, fermento biológico, sal. "
                    "CONTÉM: glúten, leite, ovos e soja."
                ),
                "nutrition_facts": nutrition(90, 1, 310.0, 39.0, 14.0, 7.0, 13.0, 7.5, 1.8, 245.0),
            },
            "DELI": {
                "ingredients_text": (
                    "Pão amanteigado, milho, bacon, queijo minas. "
                    "CONTÉM: glúten, leite e ovos."
                ),
                "nutrition_facts": nutrition(180, 1, 520.0, 54.0, 8.0, 18.0, 27.0, 12.0, 3.0, 860.0),
            },
            "HOTDOG": {
                "ingredients_text": (
                    "Pão amanteigado, salsicha viena artesanal, molho da casa. "
                    "CONTÉM: glúten, leite e ovos."
                ),
                "nutrition_facts": nutrition(180, 1, 480.0, 44.0, 7.0, 17.0, 25.0, 10.0, 2.0, 980.0),
            },
            "CROQUE-MONSIEUR": {
                "ingredients_text": (
                    "Pão de forma artesanal, molho bechamel, presunto, queijo gruyere, manteiga. "
                    "CONTÉM: glúten e leite."
                ),
                "nutrition_facts": nutrition(250, 1, 620.0, 42.0, 8.0, 28.0, 38.0, 22.0, 2.5, 1180.0),
            },
            "CROQUE-MADAME": {
                "ingredients_text": (
                    "Pão de forma artesanal, molho bechamel, presunto, queijo gruyere, manteiga, ovo. "
                    "CONTÉM: glúten, leite e ovos."
                ),
                "nutrition_facts": nutrition(290, 1, 700.0, 43.0, 8.0, 34.0, 45.0, 24.0, 2.5, 1260.0),
            },
            "QUICHE-LORRAINE": {
                "ingredients_text": (
                    "Massa brisée, ovos, creme de leite, bacon, queijo, cebola. "
                    "CONTÉM: glúten, leite e ovos."
                ),
                "nutrition_facts": nutrition(200, 1, 560.0, 31.0, 4.0, 18.0, 42.0, 23.0, 2.0, 760.0),
            },
            "QUICHE-LEGUMES": {
                "ingredients_text": (
                    "Massa brisée, ovos, creme de leite, queijo, abobrinha, tomate, temperos. "
                    "CONTÉM: glúten, leite e ovos."
                ),
                "nutrition_facts": nutrition(200, 1, 470.0, 34.0, 5.0, 15.0, 32.0, 18.0, 3.0, 620.0),
            },
            "TARTINE-SAUMON": {
                "ingredients_text": (
                    "Pain de campagne, cream cheese, salmão defumado, alcaparras, ervas. "
                    "CONTÉM: glúten, leite e peixe."
                ),
                "nutrition_facts": nutrition(220, 1, 470.0, 46.0, 4.0, 22.0, 18.0, 8.0, 4.0, 940.0),
            },
            "TARTINE-TOMATE": {
                "ingredients_text": (
                    "Pain de campagne, tomate, burrata, manjericão, azeite extra virgem. "
                    "CONTÉM: glúten e leite."
                ),
                "nutrition_facts": nutrition(200, 1, 430.0, 42.0, 5.0, 16.0, 20.0, 10.0, 4.0, 620.0),
            },
            "COMBO-PETIT-DEJ": {
                "ingredients_text": (
                    "Composto por Croissant Tradicional e Mini Baguete. "
                    "CONTÉM: glúten, leite e ovos."
                ),
                "nutrition_facts": nutrition(200, 1, 610.0, 74.0, 8.0, 14.0, 27.0, 16.0, 3.2, 620.0),
            },
            "ESPRESSO": {
                "ingredients_text": "Café espresso. NÃO CONTÉM GLÚTEN.",
                "nutrition_facts": nutrition(40, 1, 2.0, 0.0, 0.0, 0.1, 0.0, 0.0, 0.0, 0.0),
            },
            "ESPRESSO-DUPLO": {
                "ingredients_text": "Café espresso em dose dupla. NÃO CONTÉM GLÚTEN.",
                "nutrition_facts": nutrition(80, 1, 4.0, 0.0, 0.0, 0.2, 0.0, 0.0, 0.0, 0.0),
            },
            "CAPPUCCINO": {
                "ingredients_text": (
                    "Café espresso e leite integral vaporizado. "
                    "CONTÉM: leite. NÃO CONTÉM GLÚTEN."
                ),
                "nutrition_facts": nutrition(180, 1, 105.0, 9.0, 9.0, 6.0, 5.5, 3.4, 0.0, 85.0),
            },
            "LATTE": {
                "ingredients_text": (
                    "Café espresso e leite integral vaporizado. "
                    "CONTÉM: leite. NÃO CONTÉM GLÚTEN."
                ),
                "nutrition_facts": nutrition(240, 1, 145.0, 12.0, 12.0, 8.0, 7.5, 4.6, 0.0, 115.0),
            },
            "CHA-EARL-GREY": {
                "ingredients_text": "Chá preto Earl Grey com bergamota. NÃO CONTÉM GLÚTEN.",
                "nutrition_facts": nutrition(200, 1, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            },
            "SUCO-LARANJA": {
                "ingredients_text": (
                    "Laranja natural. CONTÉM: naturalmente açúcares da fruta. "
                    "Sem adição de açúcar ou conservantes."
                ),
                "nutrition_facts": nutrition(200, 1, 90.0, 21.0, 17.0, 1.4, 0.4, 0.0, 0.5, 2.0),
            },
            "CHOCOLATE-QUENTE": {
                "ingredients_text": (
                    "Chocolate belga 54% cacau, leite integral, açúcar. "
                    "CONTÉM: leite, soja. PODE CONTER: glúten, amendoim (contaminação cruzada)."
                ),
                "nutrition_facts": nutrition(240, 1, 310.0, 36.0, 30.0, 8.5, 14.0, 9.0, 2.0, 80.0),
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
            defaults={"name": "Cafés & Bebidas", "is_active": True, "sort_order": 8},
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
        for ref, name, kind, saleable, default in [
            ("deposito", "Deposito", PositionKind.PHYSICAL, False, False),
            ("vitrine", "Vitrine / Exposicao", PositionKind.PHYSICAL, True, False),
            ("producao", "Área de Produção", PositionKind.PHYSICAL, False, False),
            ("massa", "Massa", PositionKind.PROCESS, False, True),
            ("molde", "Molde", PositionKind.PROCESS, False, False),
            ("forno", "Forno", PositionKind.PROCESS, False, False),
            ("ontem", "Vitrine D-1 (ontem)", PositionKind.PHYSICAL, True, False),
        ]:
            p, _ = Position.objects.update_or_create(
                ref=ref,
                defaults={
                    "name": name,
                    "kind": kind,
                    "is_saleable": saleable,
                    "is_default": default,
                },
            )
            positions[ref] = p

        self.stdout.write("  ✅ 7 posicoes")
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
            "CAMPAGNE-PASSAS": 6,
            "CIABATTA": 20,
            "PAO-FORMA": 12,
            "CHALLAH": 8,
            "PAO-HAMBURGER": 30,
            "FOCACCIA-ALECRIM": 8,
            "FOCACCIA-CEBOLA": 6,
            "FOCACCIA-BACON": 6,
            "MINI-FOCACCIA-ALECRIM": 15,
            "MINI-FOCACCIA-CEBOLA": 12,
            "MINI-FOCACCIA-BACON": 12,
            "BRIOCHE": 12,
            "BRIOCHE-BURGER": 15,
            "PAO-HOTDOG": 10,
            "CROISSANT": 40,
            "PAIN-CHOCOLAT": 30,
            "MINI-CROISSANT": 25,
            "CHAUSSON": 12,
            "BICHON": 10,
            "CORNET-CHOCOLATE": 15,
            "CORNET": 12,
            "MELON-PAN": 10,
            "PAIN-RAISINS": 12,
            "BRIOCHE-CHOCOLAT": 12,
            "MADELEINE": 20,
            "DELI": 15,
            "HOTDOG": 12,
            "QUICHE-LORRAINE": 8,
            "QUICHE-LEGUMES": 8,
            "CROQUE-MONSIEUR": 12,
            "CROQUE-MADAME": 10,
            "TARTINE-SAUMON": 10,
            "TARTINE-TOMATE": 10,
            "COMBO-PETIT-DEJ": 10,
            "ESPRESSO": 100,
            "ESPRESSO-DUPLO": 80,
            "CAPPUCCINO": 60,
            "LATTE": 60,
            "CHOCOLATE-QUENTE": 40,
            "CHA-EARL-GREY": 40,
            "SUCO-LARANJA": 30,
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
                "ref": "massa-levain-clara",
                "name": "Massa Levain Clara",
                "output_sku": "MASSA-LEVAIN-CLARA",
                "batch_size": Decimal("10"),
                "items": [
                    ("INS-FARINHA-T65", Decimal("5.000")),
                    ("INS-AGUA", Decimal("3.500")),
                    ("INS-FERMENTO-NAT", Decimal("1.500")),
                    ("INS-SAL", Decimal("0.100")),
                    ("INS-MALTE", Decimal("0.020")),
                ],
            },
            {
                "ref": "massa-campagne",
                "name": "Massa Campagne",
                "output_sku": "MASSA-CAMPAGNE",
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
                "ref": "massa-alta-hidratacao",
                "name": "Massa Alta Hidratação",
                "output_sku": "MASSA-ALTA-HIDRATACAO",
                "batch_size": Decimal("10"),
                "items": [
                    ("INS-FARINHA-T55", Decimal("5.000")),
                    ("INS-AGUA", Decimal("4.000")),
                    ("INS-FERMENTO-NAT", Decimal("1.500")),
                    ("INS-AZEITE", Decimal("0.250")),
                    ("INS-SAL", Decimal("0.100")),
                ],
            },
            {
                "ref": "massa-paes-macios",
                "name": "Massa Pães Macios",
                "output_sku": "MASSA-PAES-MACIOS",
                "batch_size": Decimal("10"),
                "items": [
                    ("INS-FARINHA-T55", Decimal("5.000")),
                    ("INS-LEITE", Decimal("2.000")),
                    ("INS-MANTEIGA-FR", Decimal("0.700")),
                    ("INS-ACUCAR", Decimal("0.350")),
                    ("INS-FERMENTO-BIO", Decimal("0.150")),
                    ("INS-SAL", Decimal("0.100")),
                ],
            },
            {
                "ref": "massa-folhada",
                "name": "Massa Folhada",
                "output_sku": "MASSA-FOLHADA",
                "batch_size": Decimal("10"),
                "items": [
                    ("INS-FARINHA-T45", Decimal("4.800")),
                    ("INS-MANTEIGA-FR", Decimal("2.400")),
                    ("INS-LEITE", Decimal("1.200")),
                    ("INS-ACUCAR", Decimal("0.450")),
                    ("INS-FERMENTO-BIO", Decimal("0.180")),
                    ("INS-SAL", Decimal("0.090")),
                    ("INS-OVOS", Decimal("0.300")),
                ],
            },
            {
                "ref": "massa-brioche",
                "name": "Massa Brioche",
                "output_sku": "MASSA-BRIOCHE",
                "batch_size": Decimal("10"),
                "items": [
                    ("INS-FARINHA-T45", Decimal("4.000")),
                    ("INS-MANTEIGA-FR", Decimal("2.000")),
                    ("INS-OVOS", Decimal("1.200")),
                    ("INS-ACUCAR", Decimal("0.600")),
                    ("INS-FERMENTO-BIO", Decimal("0.160")),
                    ("INS-SAL", Decimal("0.080")),
                ],
            },
            {
                "ref": "baguete",
                "name": "Baguete Francesa",
                "output_sku": "BAGUETE",
                "batch_size": Decimal("25"),
                "items": [
                    ("MASSA-LEVAIN-CLARA", Decimal("10.000")),
                ],
            },
            {
                "ref": "baguete-campagne",
                "name": "Baguette de Campagne",
                "output_sku": "BAGUETE-CAMPAGNE",
                "batch_size": Decimal("12"),
                "items": [
                    ("MASSA-CAMPAGNE", Decimal("5.800")),
                ],
            },
            {
                "ref": "campagne",
                "name": "Pain de Campagne",
                "output_sku": "CAMPAGNE-OVAL",
                "batch_size": Decimal("10"),
                "items": [
                    ("MASSA-CAMPAGNE", Decimal("8.200")),
                ],
            },
            {
                "ref": "italiano-rustico",
                "name": "Italiano Rústico",
                "output_sku": "ITALIANO-RUSTICO",
                "batch_size": Decimal("18"),
                "items": [
                    ("MASSA-LEVAIN-CLARA", Decimal("7.500")),
                    ("INS-AZEITE", Decimal("0.100")),
                ],
            },
            {
                "ref": "ciabatta",
                "name": "Ciabatta",
                "output_sku": "CIABATTA",
                "batch_size": Decimal("20"),
                "items": [
                    ("MASSA-ALTA-HIDRATACAO", Decimal("7.500")),
                ],
            },
            {
                "ref": "focaccia-alecrim",
                "name": "Focaccia Alecrim",
                "output_sku": "FOCACCIA-ALECRIM",
                "batch_size": Decimal("8"),
                "items": [
                    ("MASSA-ALTA-HIDRATACAO", Decimal("5.200")),
                    ("INS-ALECRIM", Decimal("0.030")),
                ],
            },
            {
                "ref": "focaccia-cebola",
                "name": "Focaccia Cebola Roxa",
                "output_sku": "FOCACCIA-CEBOLA",
                "batch_size": Decimal("6"),
                "items": [
                    ("INS-CEBOLA-ROXA", Decimal("0.400")),
                    ("INS-AZEITONA", Decimal("0.200")),
                    ("MASSA-ALTA-HIDRATACAO", Decimal("5.200")),
                ],
            },
            {
                "ref": "pao-forma",
                "name": "Pão de Forma Artesanal",
                "output_sku": "PAO-FORMA",
                "batch_size": Decimal("12"),
                "items": [
                    ("MASSA-PAES-MACIOS", Decimal("6.400")),
                ],
            },
            {
                "ref": "challah",
                "name": "Challah",
                "output_sku": "CHALLAH",
                "batch_size": Decimal("8"),
                "items": [
                    ("MASSA-PAES-MACIOS", Decimal("4.600")),
                    ("INS-OVOS", Decimal("0.600")),
                    ("INS-AZEITE", Decimal("0.200")),
                    ("INS-GERGELIM", Decimal("0.050")),
                ],
            },
            {
                "ref": "croissant",
                "name": "Croissant Manteiga",
                "output_sku": "CROISSANT",
                "batch_size": Decimal("48"),
                "items": [
                    ("MASSA-FOLHADA", Decimal("8.500")),
                ],
            },
            {
                "ref": "pain-chocolat",
                "name": "Pain au Chocolat",
                "output_sku": "PAIN-CHOCOLAT",
                "batch_size": Decimal("36"),
                "items": [
                    ("MASSA-FOLHADA", Decimal("6.500")),
                    ("INS-CHOCOLATE-70", Decimal("0.720")),
                ],
            },
            {
                "ref": "brioche",
                "name": "Brioche Nanterre",
                "output_sku": "BRIOCHE",
                "batch_size": Decimal("12"),
                "items": [
                    ("MASSA-BRIOCHE", Decimal("6.000")),
                ],
            },
            {
                "ref": "chausson",
                "name": "Chausson aux Pommes",
                "output_sku": "CHAUSSON",
                "batch_size": Decimal("12"),
                "items": [
                    ("MASSA-FOLHADA", Decimal("4.600")),
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
            product = Product.objects.filter(sku=rd["output_sku"]).first()
            shelf_life_days = product.shelf_life_days if product else None
            recipe, _ = Recipe.objects.update_or_create(
                ref=rd["ref"],
                defaults={
                    "name": rd["name"],
                    "output_sku": rd["output_sku"],
                    "batch_size": rd["batch_size"],
                    "steps": self._production_steps_for_recipe(rd["ref"]),
                    "is_active": True,
                    "meta": {
                        "capacity_per_day": int(rd["batch_size"] * Decimal("3")),
                        "max_started_minutes": self._max_started_minutes_for_recipe(rd["ref"]),
                        "requires_batch_tracking": shelf_life_days is not None,
                        "shelf_life_days": shelf_life_days,
                    },
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
            if product:
                fill_nutrition_from_recipe(product)

        # Production data is intentionally time-relative. Re-running the seed on
        # another day creates the same operational story around that new date:
        # history behind, a busy current day, and planned work ahead.
        from shopman.craftsman.models import WorkOrderEvent

        today = date.today()
        tz_info = timezone.get_current_timezone()

        production_plan = [
            # recipe_ref, base_qty, start, finish
            ("baguete", Decimal("28"), (4, 0), (6, 0)),
            ("baguete-campagne", Decimal("14"), (4, 10), (6, 30)),
            ("campagne", Decimal("10"), (3, 40), (8, 0)),
            ("italiano-rustico", Decimal("18"), (3, 50), (8, 30)),
            ("ciabatta", Decimal("20"), (5, 0), (7, 0)),
            ("pao-forma", Decimal("12"), (5, 10), (7, 30)),
            ("challah", Decimal("8"), (5, 20), (8, 0)),
            ("croissant", Decimal("48"), (5, 0), (7, 30)),
            ("pain-chocolat", Decimal("36"), (5, 30), (8, 0)),
            ("brioche", Decimal("12"), (5, 30), (8, 30)),
            ("focaccia-alecrim", Decimal("8"), (7, 0), (10, 0)),
            ("focaccia-cebola", Decimal("6"), (7, 30), (10, 30)),
            ("chausson", Decimal("12"), (8, 0), (11, 0)),
            ("madeleine", Decimal("24"), (9, 0), (13, 0)),
        ]
        recipes_by_ref = {r.ref: r for r in Recipe.objects.filter(ref__in=[row[0] for row in production_plan])}

        def at(day: date, hour_min: tuple[int, int]) -> datetime:
            return datetime.combine(day, time(hour_min[0], hour_min[1]), tzinfo=tz_info)

        def jittered(hour_min: tuple[int, int], minutes: int) -> tuple[int, int]:
            total = max(0, min(23 * 60 + 59, hour_min[0] * 60 + hour_min[1] + minutes))
            return total // 60, total % 60

        def recipe_snapshot(recipe: Recipe) -> dict:
            return {
                "batch_size": str(recipe.batch_size),
                "items": [
                    {"input_sku": item.input_sku, "quantity": str(item.quantity), "unit": item.unit}
                    for item in recipe.items.filter(is_optional=False).order_by("sort_order")
                ],
            }

        def reset_ledger(work_order: WorkOrder) -> None:
            work_order.events.all().delete()
            work_order.items.all().delete()

        def ensure_batch_traceability(work_order: WorkOrder, finished_qty: Decimal) -> None:
            if not (work_order.recipe.meta or {}).get("requires_batch_tracking"):
                return
            from shopman.stockman.models import Batch

            production_date = work_order.target_date or today
            shelf_life_days = (work_order.recipe.meta or {}).get("shelf_life_days")
            expiry_date = None
            if shelf_life_days not in (None, ""):
                expiry_date = production_date + timedelta(days=int(shelf_life_days))
            batch_ref = f"{work_order.output_sku}-{production_date:%Y%m%d}-{work_order.pk}"
            Batch.objects.update_or_create(
                ref=batch_ref,
                defaults={
                    "sku": work_order.output_sku,
                    "production_date": production_date,
                    "expiry_date": expiry_date,
                    "notes": f"Seed Nelson producao {work_order.ref}",
                },
            )
            work_order.meta = {
                **(work_order.meta or {}),
                "batch_ref": batch_ref,
                "batch_quantity": str(finished_qty),
                "expiry_date": expiry_date.isoformat() if expiry_date else "",
            }
            work_order.save(update_fields=["meta", "updated_at"])

        def add_event(work_order: WorkOrder, seq: int, kind: str, payload: dict, actor: str, created_at: datetime) -> None:
            event = WorkOrderEvent.objects.create(
                work_order=work_order,
                seq=seq,
                kind=kind,
                payload=payload,
                actor=actor,
            )
            WorkOrderEvent.objects.filter(pk=event.pk).update(created_at=created_at)

        def add_finished_items(work_order: WorkOrder, started_qty: Decimal, finished_qty: Decimal, recorded_at: datetime) -> None:
            coefficient = started_qty / work_order.recipe.batch_size
            for item in work_order.recipe.items.filter(is_optional=False).order_by("sort_order"):
                required = (item.quantity * coefficient).quantize(Decimal("0.001"))
                WorkOrderItem.objects.create(
                    work_order=work_order,
                    kind=WorkOrderItem.Kind.REQUIREMENT,
                    item_ref=item.input_sku,
                    quantity=required,
                    unit=item.unit,
                    recorded_at=recorded_at,
                    recorded_by="seed",
                )
                WorkOrderItem.objects.create(
                    work_order=work_order,
                    kind=WorkOrderItem.Kind.CONSUMPTION,
                    item_ref=item.input_sku,
                    quantity=required,
                    unit=item.unit,
                    recorded_at=recorded_at,
                    recorded_by="seed",
                )
            WorkOrderItem.objects.create(
                work_order=work_order,
                kind=WorkOrderItem.Kind.OUTPUT,
                item_ref=work_order.output_sku,
                quantity=finished_qty,
                unit="un",
                recorded_at=recorded_at,
                recorded_by="seed",
            )
            waste_qty = max(started_qty - finished_qty, Decimal("0"))
            if waste_qty > 0:
                WorkOrderItem.objects.create(
                    work_order=work_order,
                    kind=WorkOrderItem.Kind.WASTE,
                    item_ref=work_order.output_sku,
                    quantity=waste_qty,
                    unit="un",
                    recorded_at=recorded_at,
                    recorded_by="seed",
                    meta={"reason": "perda natural / não vendido"},
                )

        def upsert_work_order(
            *,
            scope: str,
            recipe: Recipe,
            target_date: date,
            planned_qty: Decimal,
            status: str,
            started_qty: Decimal | None = None,
            finished_qty: Decimal | None = None,
            start_at: datetime | None = None,
            finish_at: datetime | None = None,
            operator_ref: str = "",
            position_ref: str = "producao",
        ) -> WorkOrder:
            source_ref = f"seed:production:{scope}:{target_date.isoformat()}:{recipe.ref}"
            work_order = WorkOrder.objects.filter(source_ref=source_ref).first()
            if work_order is None:
                work_order = WorkOrder(source_ref=source_ref)
            work_order.recipe = recipe
            work_order.output_sku = recipe.output_sku
            work_order.quantity = planned_qty
            work_order.finished = finished_qty
            work_order.status = status
            work_order.target_date = target_date
            work_order.started_at = start_at
            work_order.finished_at = finish_at
            work_order.position_ref = position_ref
            work_order.operator_ref = operator_ref
            work_order.meta = {"seed": True, "scope": scope, "_recipe_snapshot": recipe_snapshot(recipe)}
            work_order.save()

            reset_ledger(work_order)
            add_event(
                work_order,
                0,
                WorkOrderEvent.Kind.PLANNED,
                {
                    "quantity": str(planned_qty),
                    "recipe": recipe.ref,
                    "output_sku": recipe.output_sku,
                    "target_date": target_date.isoformat(),
                    "source_ref": source_ref,
                    "position_ref": position_ref,
                    "operator_ref": operator_ref,
                },
                "seed",
                at(target_date, (3, 0)),
            )
            if status in (WorkOrder.Status.STARTED, WorkOrder.Status.FINISHED):
                effective_started = started_qty or planned_qty
                add_event(
                    work_order,
                    1,
                    WorkOrderEvent.Kind.STARTED,
                    {
                        "quantity": str(effective_started),
                        "operator_ref": operator_ref,
                        "position_ref": position_ref,
                        "note": "seed operacional",
                    },
                    "seed",
                    start_at or at(target_date, (5, 0)),
                )
            if status == WorkOrder.Status.FINISHED and finished_qty is not None:
                effective_started = started_qty or planned_qty
                add_event(
                    work_order,
                    2,
                    WorkOrderEvent.Kind.FINISHED,
                    {
                        "finished_qty": str(finished_qty),
                        "planned_qty": str(planned_qty),
                        "started_qty": str(effective_started),
                        "loss_qty": str(max(effective_started - finished_qty, Decimal("0"))),
                        "output_sku": recipe.output_sku,
                        "target_date": target_date.isoformat(),
                        "source_ref": source_ref,
                        "position_ref": position_ref,
                        "operator_ref": operator_ref,
                    },
                    "seed",
                    finish_at or at(target_date, (8, 0)),
                )
                add_finished_items(work_order, effective_started, finished_qty, finish_at or at(target_date, (8, 0)))
                ensure_batch_traceability(work_order, finished_qty)
            return work_order

        # Remove old seed rows outside the moving operational window. The active window
        # is overwritten below through stable source_ref values.
        stale_before = today - timedelta(days=45)
        WorkOrder.objects.filter(source_ref__startswith="seed:production:", target_date__lt=stale_before).delete()

        wo_count = 0
        history_count = 0
        future_count = 0

        # Current day: mixed statuses so the matrix is useful immediately.
        for index, (ref, qty, start_hm, finish_hm) in enumerate(production_plan):
            recipe = recipes_by_ref[ref]
            if index in (0, 1, 7, 9):
                status = WorkOrder.Status.FINISHED
            elif index in (2, 3, 4, 10, 11):
                status = WorkOrder.Status.STARTED
            else:
                status = WorkOrder.Status.PLANNED
            started = (qty + Decimal(str(index % 3))).quantize(Decimal("0.001"))
            finished = None
            finish_at = None
            if status == WorkOrder.Status.FINISHED:
                if ref == "croissant":
                    finished = max((started * Decimal("0.70")).quantize(Decimal("1")), Decimal("1"))
                else:
                    finished = max(started - Decimal(str((index % 4) + 1)), Decimal("1"))
                finish_at = at(today, finish_hm)
            start_at = at(today, start_hm) if status != WorkOrder.Status.PLANNED else None
            if status == WorkOrder.Status.STARTED and index == 2:
                start_at = timezone.now() - timedelta(minutes=self._max_started_minutes_for_recipe(ref) + 15)
            upsert_work_order(
                scope="today",
                recipe=recipe,
                target_date=today,
                planned_qty=qty,
                status=status,
                started_qty=started if status != WorkOrder.Status.PLANNED else None,
                finished_qty=finished,
                start_at=start_at,
                finish_at=finish_at,
                operator_ref=["chef:ana", "chef:joao", "chef:maria"][index % 3],
            )
            wo_count += 1

        # Future horizon: planned production for one week ahead.
        for offset in range(1, 8):
            target = today + timedelta(days=offset)
            if target.weekday() == 0:
                continue
            day_multiplier = Decimal("1.25") if target.weekday() in (4, 5) else Decimal("1")
            for index, (ref, qty, _start_hm, _finish_hm) in enumerate(production_plan):
                if offset > 2 and index % 3 == 2:
                    continue
                recipe = recipes_by_ref[ref]
                planned = (qty * day_multiplier).quantize(Decimal("1"))
                upsert_work_order(
                    scope=f"future-{offset}",
                    recipe=recipe,
                    target_date=target,
                    planned_qty=planned,
                    status=WorkOrder.Status.PLANNED,
                    operator_ref="chef:planejamento",
                )
                future_count += 1

        # Historical production: 35 relative days behind today for BI,
        # pickup slots and waste patterns.
        for days_ago in range(1, 36):
            target = today - timedelta(days=days_ago)
            if target.weekday() == 0:
                continue
            weekday_multiplier = Decimal("1.20") if target.weekday() in (4, 5) else Decimal("1")
            for index, (ref, qty, start_hm, finish_hm) in enumerate(production_plan):
                recipe = recipes_by_ref[ref]
                jitter = random.randint(-12, 12)
                start = at(target, jittered(start_hm, jitter))
                finish = at(target, jittered(finish_hm, jitter + random.randint(-6, 10)))
                planned = (qty * weekday_multiplier).quantize(Decimal("1"))
                started = planned
                loss = Decimal(str((index + days_ago) % 4))
                finished = max(started - loss, Decimal("1"))
                upsert_work_order(
                    scope=f"history-{days_ago}",
                    recipe=recipe,
                    target_date=target,
                    planned_qty=planned,
                    status=WorkOrder.Status.FINISHED,
                    started_qty=started,
                    finished_qty=finished,
                    start_at=start,
                    finish_at=finish,
                    operator_ref=["chef:ana", "chef:joao", "chef:maria"][index % 3],
                )
                history_count += 1

        self.stdout.write(
            f"  ✅ {len(recipes_data)} receitas, {wo_count} ordens de hoje,"
            f" {future_count} futuras e {history_count} historico movel"
        )

    def _production_steps_for_recipe(self, ref: str) -> list[str]:
        if "croissant" in ref or "chocolat" in ref or "chausson" in ref:
            return ["Massa", "Laminação", "Forno"]
        if "focaccia" in ref:
            return ["Mistura", "Fermentação", "Cobertura", "Forno"]
        if "brioche" in ref:
            return ["Mistura", "Descanso", "Forno"]
        if ref.startswith("massa-"):
            return ["Pesagem", "Mistura", "Fermentação"]
        return ["Mistura", "Fermentação", "Modelagem", "Forno"]

    def _max_started_minutes_for_recipe(self, ref: str) -> int:
        if "croissant" in ref or "chocolat" in ref or "chausson" in ref:
            return 150
        if "campagne" in ref or "italiano" in ref:
            return 240
        if ref.startswith("massa-"):
            return 180
        return 120

    def _assert_catalog_remote_purchase_data(self):
        missing = []
        required_metadata = ("allergens", "dietary_info", "serves")
        products = Product.objects.filter(is_published=True).prefetch_related("keywords").order_by("sku")

        for product in products:
            gaps = []
            metadata = product.metadata if isinstance(product.metadata, dict) else {}
            for key in required_metadata:
                if key not in metadata:
                    gaps.append(f"metadata.{key}")
            if product.unit_weight_g and not metadata.get("approx_dimensions"):
                gaps.append("metadata.approx_dimensions")
            if not product.keywords.exists():
                gaps.append("keywords")
            if not product.ingredients_text:
                gaps.append("ingredients_text")
            if not product.nutrition_facts:
                gaps.append("nutrition_facts")
            if gaps:
                missing.append(f"{product.sku}: {', '.join(gaps)}")

        if missing:
            raise CommandError(
                "Seed catalog remoto incompleto. Corrija os produtos publicados: "
                + "; ".join(missing)
            )

        self.stdout.write(f"  ✅ Dados remotos PDP: {products.count()} produtos completos")

    def _assert_storefront_products_orderable(self):
        from shopman.shop.services import catalog_context

        blocked = []
        products = Product.objects.filter(is_published=True, is_sellable=True).order_by("sku")
        for product in products:
            raw_availability = catalog_context.availability_for_sku(product.sku, channel_ref="web")
            availability = catalog_context.storefront_availability(
                raw_availability,
                is_sellable=product.is_sellable,
            )
            if not availability or not availability.get("can_order"):
                blocked.append(product.sku)

        if blocked:
            raise CommandError(
                "Seed storefront incompleto. Produtos publicados/vendáveis sem compra web: "
                + ", ".join(blocked)
            )

        self.stdout.write(f"  ✅ Compra web: {products.count()} produtos vendáveis orderable")

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
            ("CLI-004", "Café", "Parisiense", "business", atacado, "+5543994444444"),
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
            "confirmation": {"mode": "auto_confirm", "timeout_minutes": 5, "stale_new_alert_minutes": 10},
            "payment": {"method": ["pix", "card"], "timing": "post_commit", "timeout_minutes": 10},
            "stock": _remote_stock,
        }
        _marketplace_config = {
            "confirmation": {"mode": "manual", "stale_new_alert_minutes": 30},
            "payment": {"method": "external", "timing": "external"},
            "stock": {**_remote_stock, "check_on_commit": True},
        }
        _whatsapp_config = {
            "confirmation": {"mode": "auto_confirm", "timeout_minutes": 5, "stale_new_alert_minutes": 10},
            "payment": {"method": ["pix", "card"], "timing": "post_commit", "timeout_minutes": 10},
            "notifications": {"backend": "manychat"},
            "stock": _remote_stock,
        }
        channels_data = [
            # (ref, name, config_overrides)
            ("pdv", "PDV", _pos_config),
            ("delivery", "Delivery Proprio", _remote_config),
            ("ifood", "iFood", {
                **_marketplace_config,
                "pricing": {"policy": "external"},
                "editing": {"policy": "locked"},
            }),
            ("whatsapp", "WhatsApp", _whatsapp_config),
            ("web", "E-commerce", _remote_config),
        ]

        for ref, name, config_data in channels_data:
            ch, _ = Channel.objects.update_or_create(
                ref=ref,
                defaults={
                    "name": name,
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

                ref = self._new_order_ref(channel.ref, order_time.date())

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
                    data={"availability_decision": {"approved": True, "source": "seed", "decisions": []}},
                )
                self._stamp_order(order, order_time)

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
        from shopman.shop.handlers.production_order_sync import link_order_to_work_orders

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

            ref = self._new_order_ref(channel.ref, order_time.date())
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
                data={"availability_decision": {"approved": True, "source": "seed", "decisions": []}},
            )
            self._stamp_order(order, order_time)

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

                from shopman.shop.services.kds import dispatch
                tickets = dispatch(order)

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

            if live_status in ("confirmed", "preparing", "ready"):
                link_order_to_work_orders(order=order, event_type="status_changed", actor="seed")

            order_count += 1

        # Deterministic production-dependent order so Pedidos and Produção
        # always demonstrate the visual sync from WP-BS-9.
        produced_product = products.get("CROISSANT") or products.get("BAGUETE")
        if produced_product:
            customer = customer_list[0]
            channel = channels["pdv"]
            order_time = now - timedelta(minutes=6)
            ref = self._new_order_ref(channel.ref, order_time.date())
            sync_order = Order.objects.create(
                ref=ref,
                channel_ref=channel.ref,
                status=Order.Status.CONFIRMED,
                total_q=produced_product.base_price_q * 3,
                handle_type="phone",
                handle_ref=customer.contact_points.filter(type="whatsapp").values_list("value_normalized", flat=True).first() or "",
                created_at=order_time,
                data={
                    "customer": {"name": customer.name},
                    "payment": {"method": "cash"},
                    "fulfillment_type": "pickup",
                    "availability_decision": {"approved": True, "source": "seed", "decisions": []},
                },
            )
            self._stamp_order(sync_order, order_time)
            OrderItem.objects.create(
                order=sync_order,
                line_id=f"L-{uuid.uuid4().hex[:8]}",
                sku=produced_product.sku,
                name=produced_product.name,
                qty=Decimal("3"),
                unit_price_q=produced_product.base_price_q,
                line_total_q=produced_product.base_price_q * 3,
            )
            OrderEvent.objects.create(
                order=sync_order,
                type="status_change",
                seq=0,
                payload={"new_status": "new"},
                created_at=order_time,
            )
            OrderEvent.objects.create(
                order=sync_order,
                type="status_change",
                seq=1,
                payload={"new_status": "confirmed"},
                created_at=order_time + timedelta(minutes=1),
            )
            link_order_to_work_orders(order=sync_order, event_type="status_changed", actor="seed")
            order_count += 1

        # ── iFood operational orders ──────────────────────────────────────────
        if "ifood" in channels:
            ifood_ch = channels["ifood"]
            prod_a = product_list[0]
            prod_b = product_list[1] if len(product_list) > 1 else product_list[0]

            # Order 1: new iFood order (just arrived, awaiting confirmation)
            ref_new = self._new_order_ref(ifood_ch.ref, (now - timedelta(minutes=2)).date())
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
            self._stamp_order(order_new, now - timedelta(minutes=2))
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
            ref_confirmed = self._new_order_ref(ifood_ch.ref, (now - timedelta(minutes=9)).date())
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
            self._stamp_order(order_confirmed, now - timedelta(minutes=9))
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
            link_order_to_work_orders(order=order_confirmed, event_type="status_changed", actor="seed")

            order_count += 2
            self.stdout.write("  ✅ 2 pedidos iFood operacionais adicionados")

        production_history_count = self._seed_production_demand_history(products, channels, now)
        order_count += production_history_count

        self.stdout.write(
            f"  ✅ {order_count} pedidos (35 dias + live + iFood + historico producao)"
        )

    def _seed_security_reliability_edges(self, products, customers, channels):
        """Deterministic edge scenarios for adversarial QA and Omotenashi drills."""
        self.stdout.write("  🧪 Cenários de segurança/confiabilidade...")

        now = timezone.now()
        web = channels.get("web")
        ifood = channels.get("ifood")
        product = products.get("CROISSANT") or next(iter(products.values()), None)
        if web is None or product is None:
            self.stdout.write("  ⏭️  Sem canal web/produto para cenários de borda")
            return

        low_attention = customers.get("CLI-001")
        if low_attention:
            low_attention.metadata = {
                **(low_attention.metadata if isinstance(low_attention.metadata, dict) else {}),
                "seed_persona": "low_attention",
                "qa_notes": [
                    "tende a clicar duas vezes em confirmar",
                    "abandona pagamento PIX e volta pelo tracking",
                    "precisa de mensagens curtas e recuperacao clara",
                ],
            }
            low_attention.save(update_fields=["metadata"])

        created = 0

        pending = self._create_edge_order(
            seed_key="security:payment-pending-near-expiry",
            channel_ref=web.ref,
            status=Order.Status.CONFIRMED,
            product=product,
            qty=Decimal("2"),
            customer=low_attention,
            created_at=now - timedelta(minutes=4),
            data={
                "customer": {"name": getattr(low_attention, "name", "Cliente distraido")},
                "payment": {
                    "method": "pix",
                    "amount_q": product.base_price_q * 2,
                    "expires_at": (now + timedelta(minutes=6)).replace(microsecond=0).isoformat(),
                },
                "fulfillment_type": "pickup",
                "edge_case": "low_attention_payment_pending",
                "availability_decision": {"approved": True, "source": "seed:edge", "decisions": []},
            },
        )
        if pending:
            self._attach_edge_payment_intent(
                pending,
                method=PaymentIntent.Method.PIX,
                status=PaymentIntent.Status.PENDING,
                gateway="efi",
                gateway_id="seed-edge-pix-pending",
                expires_at=now + timedelta(minutes=6),
            )
            created += 1

        expired = self._create_edge_order(
            seed_key="security:payment-expired-low-attention",
            channel_ref=web.ref,
            status=Order.Status.CONFIRMED,
            product=product,
            qty=Decimal("1"),
            customer=low_attention,
            created_at=now - timedelta(minutes=18),
            data={
                "customer": {"name": getattr(low_attention, "name", "Cliente distraido")},
                "payment": {
                    "method": "pix",
                    "amount_q": product.base_price_q,
                    "expires_at": (now - timedelta(minutes=3)).replace(microsecond=0).isoformat(),
                },
                "fulfillment_type": "pickup",
                "edge_case": "low_attention_payment_expired",
                "availability_decision": {"approved": True, "source": "seed:edge", "decisions": []},
            },
        )
        if expired:
            self._attach_edge_payment_intent(
                expired,
                method=PaymentIntent.Method.PIX,
                status=PaymentIntent.Status.PENDING,
                gateway="efi",
                gateway_id="seed-edge-pix-expired",
                expires_at=now - timedelta(minutes=3),
            )
            created += 1

        late_paid = self._create_edge_order(
            seed_key="security:payment-after-cancel",
            channel_ref=web.ref,
            status=Order.Status.CANCELLED,
            product=product,
            qty=Decimal("3"),
            customer=low_attention,
            created_at=now - timedelta(minutes=26),
            data={
                "customer": {"name": getattr(low_attention, "name", "Cliente distraido")},
                "payment": {
                    "method": "pix",
                    "amount_q": product.base_price_q * 3,
                    "expires_at": (now - timedelta(minutes=10)).replace(microsecond=0).isoformat(),
                },
                "fulfillment_type": "pickup",
                "cancellation_reason": "customer_requested",
                "edge_case": "late_payment_after_cancel",
                "availability_decision": {"approved": True, "source": "seed:edge", "decisions": []},
            },
        )
        if late_paid:
            self._attach_edge_payment_intent(
                late_paid,
                method=PaymentIntent.Method.PIX,
                status=PaymentIntent.Status.CAPTURED,
                gateway="efi",
                gateway_id="seed-edge-pix-after-cancel",
                captured_at=now - timedelta(minutes=5),
            )
            OperatorAlert.objects.get_or_create(
                type="payment_after_cancel",
                order_ref=late_paid.ref,
                defaults={
                    "severity": "critical",
                    "message": (
                        f"Pagamento capturado depois do cancelamento do pedido {late_paid.ref}. "
                        "Validar reembolso e comunicação com o cliente."
                    ),
                },
            )
            self._mark_edge_webhook_replay(
                scope="webhook:efi-pix",
                source="e2e",
                source_id="seed-edge-e2e-after-cancel",
                response_body={
                    "status": "processed",
                    "txid": f"seed-edge-pix-after-cancel-{late_paid.ref}",
                    "e2e_id": "seed-edge-e2e-after-cancel",
                },
                now=now,
            )
            created += 1

        if ifood is not None:
            stale = self._create_edge_order(
                seed_key="security:ifood-stale-confirmation",
                channel_ref=ifood.ref,
                status=Order.Status.NEW,
                product=product,
                qty=Decimal("1"),
                customer=None,
                created_at=now - timedelta(minutes=46),
                external_ref="IFOOD-EDGE-STALE-001",
                data={
                    "customer": {"name": "Pedido iFood parado"},
                    "payment": {"method": "external", "timing": "external"},
                    "fulfillment_type": "delivery",
                    "edge_case": "marketplace_stale_confirmation",
                    "availability_decision": {"approved": True, "source": "seed:edge", "decisions": []},
                },
            )
            if stale:
                OperatorAlert.objects.get_or_create(
                    type="stale_new_order",
                    order_ref=stale.ref,
                    defaults={
                        "severity": "error",
                        "message": f"Pedido marketplace {stale.ref} parado aguardando confirmação.",
                    },
                )
                self._mark_edge_webhook_replay(
                    scope="webhook:ifood",
                    source="order",
                    source_id="IFOOD-EDGE-STALE-001",
                    response_body={"status": "already_processed", "order_ref": stale.ref},
                    now=now,
                )
                created += 1

        self.stdout.write(f"  ✅ {created} cenários determinísticos de borda")

    def _mark_edge_webhook_replay(
        self,
        *,
        scope: str,
        source: str,
        source_id: str,
        response_body: dict,
        now,
    ) -> None:
        from shopman.shop.services.webhook_idempotency import stable_webhook_key

        key = f"{source}:{stable_webhook_key(source_id)}"
        IdempotencyKey.objects.update_or_create(
            scope=scope,
            key=key,
            defaults={
                "status": "done",
                "response_code": 200,
                "response_body": response_body,
                "expires_at": now + timedelta(days=30),
            },
        )

    def _create_edge_order(
        self,
        *,
        seed_key: str,
        channel_ref: str,
        status: str,
        product,
        qty: Decimal,
        customer,
        created_at: datetime,
        data: dict,
        external_ref: str | None = None,
    ) -> Order | None:
        existing = Order.objects.filter(snapshot__seed_key=seed_key).first()
        if existing:
            return None

        total_q = int(qty * product.base_price_q)
        ref = self._new_order_ref(channel_ref, created_at.date())
        handle_ref = ""
        if customer is not None:
            handle_ref = (
                customer.contact_points.filter(type="whatsapp")
                .values_list("value_normalized", flat=True)
                .first()
                or customer.phone
                or ""
            )
            data.setdefault("customer_ref", customer.ref)

        order = Order.objects.create(
            ref=ref,
            channel_ref=channel_ref,
            session_key=f"seed-edge-{ref}",
            status=status,
            total_q=total_q,
            handle_type="phone" if handle_ref else "marketplace_order",
            handle_ref=handle_ref,
            external_ref=external_ref,
            snapshot={
                "seed": "nelson",
                "seed_namespace": "security_reliability_edges",
                "seed_key": seed_key,
            },
            data=data,
        )
        self._stamp_order(order, created_at)
        OrderItem.objects.create(
            order=order,
            line_id=f"L-{uuid.uuid4().hex[:8]}",
            sku=product.sku,
            name=product.name,
            qty=qty,
            unit_price_q=product.base_price_q,
            line_total_q=total_q,
            meta={"seed": "nelson", "source": "security_reliability_edges"},
        )
        OrderEvent.objects.create(
            order=order,
            type="status_change",
            seq=0,
            payload={"new_status": status, "source": "seed:edge"},
            created_at=created_at,
        )
        return order

    def _attach_edge_payment_intent(
        self,
        order: Order,
        *,
        method: str,
        status: str,
        gateway: str,
        gateway_id: str,
        expires_at=None,
        captured_at=None,
    ) -> None:
        intent = PaymentIntent.objects.create(
            ref=f"PI-EDGE-{uuid.uuid4().hex[:10].upper()}",
            order_ref=order.ref,
            method=method,
            status=status,
            amount_q=order.total_q,
            gateway=gateway,
            gateway_id=f"{gateway_id}-{order.ref}",
            expires_at=expires_at,
            captured_at=captured_at,
        )
        payment = dict((order.data or {}).get("payment") or {})
        payment["intent_ref"] = intent.ref
        if status == PaymentIntent.Status.CAPTURED:
            PaymentTransaction.objects.create(
                intent=intent,
                type=PaymentTransaction.Type.CAPTURE,
                amount_q=order.total_q,
                gateway_id=intent.gateway_id,
            )
        order.data = {**(order.data or {}), "payment": payment}
        order.save(update_fields=["data", "updated_at"])

    def _seed_production_demand_history(self, products, channels, now) -> int:
        """Stable same-weekday demand rows for Craftsman production suggestions."""
        pdv = channels["pdv"]
        history = {
            "BAGUETE": [Decimal("34"), Decimal("38"), Decimal("31"), Decimal("36")],
            "CROISSANT": [Decimal("44"), Decimal("48"), Decimal("41"), Decimal("46")],
            "PAIN-CHOCOLAT": [Decimal("24"), Decimal("28"), Decimal("22"), Decimal("26")],
            "CIABATTA": [Decimal("18"), Decimal("21"), Decimal("17"), Decimal("20")],
        }
        created_or_updated = 0
        for sku, quantities in history.items():
            product = products.get(sku)
            if product is None:
                continue
            for index, qty in enumerate(quantities, start=1):
                order_time = (now - timedelta(days=7 * index)).replace(
                    hour=10,
                    minute=15,
                    second=0,
                    microsecond=0,
                )
                seed_key = f"production-demand-history:{sku}:{index}"
                ref = self._new_order_ref(pdv.ref, order_time.date())
                total_q = int(qty * product.base_price_q)
                order = Order.objects.filter(snapshot__seed_key=seed_key).first()
                if order is None:
                    order = Order.objects.create(
                        ref=ref,
                        channel_ref=pdv.ref,
                        session_key=f"seed-{ref}",
                        status=Order.Status.COMPLETED,
                        snapshot={
                            "seed": "nelson",
                            "source": "production_demand_history",
                            "seed_key": seed_key,
                        },
                        data={"availability_decision": {"approved": True, "source": "seed", "decisions": []}},
                        total_q=total_q,
                        completed_at=order_time,
                    )
                    self._stamp_order(order, order_time)
                    OrderEvent.objects.create(
                        order=order,
                        type="status_change",
                        seq=0,
                        payload={"new_status": "completed", "source": "seed"},
                        created_at=order_time,
                    )
                else:
                    Order.objects.filter(pk=order.pk).update(
                        status=Order.Status.COMPLETED,
                        completed_at=order_time,
                    )
                Order.objects.filter(pk=order.pk).update(created_at=order_time, updated_at=order_time)
                OrderItem.objects.update_or_create(
                    order=order,
                    line_id="production-history",
                    defaults={
                        "sku": sku,
                        "name": product.name,
                        "qty": qty,
                        "unit_price_q": product.base_price_q,
                        "line_total_q": total_q,
                        "meta": {"seed": "nelson", "source": "production_demand_history"},
                    },
                )
                created_or_updated += 1
        return created_or_updated

    def _stamp_order(self, order: Order, created_at: datetime):
        Order.objects.filter(pk=order.pk).update(created_at=created_at, updated_at=created_at)
        order.created_at = created_at
        order.updated_at = created_at

    def _new_order_ref(self, channel_ref: str, business_date: date) -> str:
        for _attempt in range(20):
            ref = generate_order_ref(channel_ref=channel_ref, business_date=business_date)
            if not Order.objects.filter(ref=ref).exists():
                return ref
        raise CommandError(f"Nao foi possivel gerar ORDER_REF unico para canal {channel_ref!r}.")

    def _seed_pos_tabs(self):
        self.stdout.write("  🧾 POS tabs...")

        tabs = [
            ("00001007", "1007"),
            ("00001008", "1008"),
            ("00001009", "1009"),
            ("00001010", "1010"),
            ("00001011", "1011"),
            ("00001012", "1012"),
        ]
        for code, label in tabs:
            POSTab.objects.update_or_create(
                code=code,
                defaults={"label": label, "is_active": True},
            )

        self.stdout.write(f"  ✅ {len(tabs)} POS tabs cadastradas")

    # ────────────────────────────────────────────────────────────────
    # Sessoes abertas (Orderman)
    # ────────────────────────────────────────────────────────────────

    def _seed_sessions(self, channels):
        self.stdout.write("  📝 Sessoes abertas...")

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
            defaults = {
                "session_key": generate_session_key(),
                "state": "open",
                "pricing_policy": cfg.pricing.policy,
                "edit_policy": cfg.editing.policy,
            }
            if channel_ref == "pdv":
                tab_code = "00001007"
                defaults["handle_type"] = "pos_tab"
                defaults["handle_ref"] = tab_code
                defaults["data"] = {
                    "origin_channel": "pos",
                    "fulfillment_type": "pickup",
                    "tab_code": tab_code,
                    "tab_display": tab_code.lstrip("0"),
                    "pos_operator": "seed",
                    "last_touched_at": timezone.now().isoformat(),
                }
                session, _ = Session.objects.update_or_create(
                    channel_ref=ch.ref,
                    state="open",
                    handle_type="pos_tab",
                    handle_ref=tab_code,
                    defaults=defaults,
                )
            else:
                session = Session.objects.create(
                    channel_ref=ch.ref,
                    **defaults,
                )
            session.update_items(items)

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

    def _seed_operator_alerts(self):
        self.stdout.write("  🚨 Alertas operacionais...")

        from shopman.shop.handlers.production_alerts import (
            check_late_started_orders,
            create_stock_short_alert,
            maybe_create_low_yield_alert,
        )

        today = date.today()
        created_late = check_late_started_orders(selected_date=today)
        created_yield = 0
        for work_order in WorkOrder.objects.filter(
            source_ref__startswith="seed:production:today:",
            status=WorkOrder.Status.FINISHED,
        ):
            if maybe_create_low_yield_alert(work_order):
                created_yield += 1

        shortage_target = (
            WorkOrder.objects.filter(
                source_ref__startswith="seed:production:today:",
                output_sku="CROISSANT",
            )
            .order_by("created_at")
            .first()
        )
        if shortage_target:
            create_stock_short_alert(
                work_order_ref=shortage_target.ref,
                output_sku=shortage_target.output_sku,
                error="sementes de validação: manteiga francesa abaixo do ponto de reposição",
            )

        active_count = OperatorAlert.objects.filter(acknowledged=False).count()
        self.stdout.write(
            f"  ✅ Alertas operacionais ativos: {active_count}"
            f" ({created_late} atraso, {created_yield} rendimento)"
        )

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

        # Promotion 1: Semana do Pão — 15% off pães artesanais
        promo_paes, _ = Promotion.objects.update_or_create(
            name="Semana do Pão",
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
        linked = 0

        for i, order in enumerate(orders):
            existing_intent = PaymentIntent.objects.filter(order_ref=order.ref).order_by("-created_at").first()
            if existing_intent:
                if self._attach_order_payment_link(order, existing_intent):
                    linked += 1
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
            if self._attach_order_payment_link(order, intent):
                linked += 1
            count += 1

        self.stdout.write(f"  ✅ {count} payment intents + transactions ({linked} order links)")

    def _attach_order_payment_link(self, order: Order, intent: PaymentIntent) -> bool:
        payment = dict((order.data or {}).get("payment") or {})
        next_payment = {
            **payment,
            "method": intent.method,
            "intent_ref": intent.ref,
            "gateway": intent.gateway,
        }
        if payment == next_payment:
            return False
        order.data = {**(order.data or {}), "payment": next_payment}
        order.save(update_fields=["data", "updated_at"])
        return True

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

        # KDS Encomendas — Picking: separação de pedidos de balcão e agendados
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

        # KDS Expedição — pedidos prontos para balcão/despacho
        KDSInstance.objects.update_or_create(
            ref="expedicao",
            defaults={
                "name": "Expedição",
                "type": "expedition",
                "target_time_minutes": 2,
                "sound_enabled": True,
                "is_active": True,
            },
        )

        KDSInstance.objects.filter(ref__in=["padaria"]).delete()

        self.stdout.write("  ✅ 4 estações KDS (Cafés, Lanches, Encomendas, Expedição)")

    # ────────────────────────────────────────────────────────────────
    # Notification Templates
    # ────────────────────────────────────────────────────────────────

    def _seed_notification_templates(self):
        self.stdout.write("  📨 Templates de notificação...")

        from shopman.shop.models import NotificationTemplate

        FALLBACK_TEMPLATES = {
            "order_received": {"subject": "Pedido {order_ref} recebido", "body": "Ola{customer_name_greeting}! Recebemos seu pedido *{order_ref}*. O estabelecimento vai conferir a disponibilidade. Acompanhe por aqui: {tracking_url}"},
            "order_received_outside_hours": {"subject": "Pedido {order_ref} recebido", "body": "Ola{customer_name_greeting}! Recebemos seu pedido *{order_ref}* fora do nosso horario de atendimento. Vamos processar assim que abrirmos. Total: *{total}*."},
            "order_confirmed": {"subject": "Pedido {order_ref} confirmado", "body": "Ola{customer_name_greeting}! Seu pedido *{order_ref}* foi confirmado. Total: *{total}*.\n\nObrigado pela preferencia!"},
            "order_preparing": {"subject": "Pedido {order_ref} em preparo", "body": "Ola{customer_name_greeting}! Seu pedido *{order_ref}* esta sendo preparado.\n\nAvisaremos quando estiver pronto!"},
            "order_ready_pickup": {"subject": "Pedido {order_ref} pronto para retirada", "body": "Ola{customer_name_greeting}! Seu pedido *{order_ref}* esta pronto para retirada! \U0001f389\n\nVenha buscar. Obrigado!"},
            "order_ready_delivery": {"subject": "Pedido {order_ref} pronto para entrega", "body": "Ola{customer_name_greeting}! Seu pedido *{order_ref}* esta pronto e aguardando entregador. Assim que sair para entrega avisamos. \U0001f4e6"},
            "order_dispatched": {"subject": "Pedido {order_ref} saiu para entrega", "body": "Ola{customer_name_greeting}! Seu pedido *{order_ref}* saiu para entrega!\n\nEm breve estara com voce!"},
            "order_delivered": {"subject": "Pedido {order_ref} entregue", "body": "Ola{customer_name_greeting}! Seu pedido *{order_ref}* foi entregue.\n\nEsperamos que tenha gostado! Obrigado pela preferencia."},
            "order_cancelled": {"subject": "Pedido {order_ref} cancelado", "body": "Ola{customer_name_greeting}! Seu pedido *{order_ref}* foi cancelado.\n\nEm caso de duvidas, entre em contato."},
            "order_rejected": {"subject": "Pedido {order_ref} nao confirmado", "body": "Ola{customer_name_greeting}! O estabelecimento nao conseguiu confirmar o pedido *{order_ref}*.\n\nMotivo: {reason}\n\nEm caso de duvidas, estamos aqui."},
            "payment_requested": {"subject": "Pedido {order_ref}: pagamento liberado", "body": "Ola{customer_name_greeting}! Confirmamos a disponibilidade do pedido *{order_ref}*.\n\nPara continuar, conclua o pagamento dentro do prazo: {payment_url}"},
            "payment_confirmed": {"subject": "Pagamento do pedido {order_ref} confirmado", "body": "Ola{customer_name_greeting}! O pagamento do pedido *{order_ref}* foi recebido.\n\nValor: *{total}*\n\nSeu pedido seguira para preparo. Obrigado!"},
            "payment_expired": {"subject": "Pagamento do pedido {order_ref} expirado", "body": "Ola{customer_name_greeting}! O prazo de pagamento do pedido *{order_ref}* expirou.\n\nO pedido foi cancelado automaticamente."},
            "payment_failed": {"subject": "Falha ao preparar pagamento do pedido {order_ref}", "body": "Ola{customer_name_greeting}! Nao conseguimos preparar o pagamento do pedido *{order_ref}*.\n\nAcesse {payment_url} para tentar novamente."},
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

        closing_items = [
            {"sku": "BAGUETE", "qty_reported": 6, "qty_applied": 6, "qty_discrepancy": 0, "qty_remaining": 6, "qty_d1": 4, "qty_loss": 2},
            {"sku": "BATARD", "qty_reported": 3, "qty_applied": 3, "qty_discrepancy": 0, "qty_remaining": 3, "qty_d1": 2, "qty_loss": 1},
            {"sku": "FENDU", "qty_reported": 7, "qty_applied": 7, "qty_discrepancy": 0, "qty_remaining": 7, "qty_d1": 5, "qty_loss": 2},
            {"sku": "TABATIERE", "qty_reported": 5, "qty_applied": 5, "qty_discrepancy": 0, "qty_remaining": 5, "qty_d1": 4, "qty_loss": 1},
            {"sku": "CIABATTA", "qty_reported": 4, "qty_applied": 4, "qty_discrepancy": 0, "qty_remaining": 4, "qty_d1": 3, "qty_loss": 1},
            {"sku": "PAO-HAMBURGER", "qty_reported": 8, "qty_applied": 8, "qty_discrepancy": 0, "qty_remaining": 8, "qty_d1": 6, "qty_loss": 2},
        ]
        production_summary = {}
        for work_order in WorkOrder.objects.filter(target_date=yesterday).select_related("recipe"):
            row = production_summary.setdefault(
                work_order.recipe.ref,
                {
                    "recipe_ref": work_order.recipe.ref,
                    "output_sku": work_order.output_sku,
                    "planned": 0,
                    "finished": 0,
                    "loss": 0,
                },
            )
            row["planned"] += int(work_order.quantity or 0)
            if work_order.finished is not None:
                row["finished"] += int(work_order.finished or 0)
                row["loss"] += max(0, int((work_order.started_qty or work_order.quantity) - work_order.finished))

        _, created = DayClosing.objects.update_or_create(
            date=yesterday,
            defaults={
                "closed_by": admin,
                "notes": "Fechamento automatico (seed)",
                "data": {
                    "items": closing_items,
                    "production_summary": production_summary,
                    "reconciliation_errors": [],
                },
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
