"""Teste exploratório de REGRAS DE NEGÓCIO e CASOS DE BORDA do storefront.

Objetivo (validação pré-alpha): provar que as nuances de precificação, estoque,
produção, checkout e lifecycle estão cobertas — e transformar cada dúvida do
plano de QA em uma asserção executável.

Estrutura (espelha o roteiro de QA):

    PRICING & PROMOTIONS  ....  D-1, happy hour, funcionário, quantidade,
                                melhor-desconto, cupom esgotado, total <= 0
    ESTOQUE & PRODUÇÃO    ....  hold exato, planejado (encomenda), sem produção,
                                expiração, cancelamento, perecível vs não-perecível
    CHECKOUT & DELIVERY   ....  pickup slots, data passada, pedido mínimo, troco
    LIFECYCLE             ....  cancelamento na janela, estado terminal, template

Estes testes exercitam o pipeline REAL:
``sessions.create_session`` → ``sessions.modify_session`` (cadeia completa de
modifiers) → ``CommitService.commit`` (gate de estoque transacional). Só os
adapters externos (pagamento/notificação) são os mocks do ``settings_test``.

Onde um teste documenta um comportamento que MERECE revisão de produto (não um
crash, mas uma nuance surpreendente), o docstring/coment marca ``ACHADO:``.
"""

from __future__ import annotations

from datetime import time, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone

pytestmark = pytest.mark.django_db


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de setup
# ─────────────────────────────────────────────────────────────────────────────


def _shop(defaults=None):
    from shopman.shop.models import Shop

    shop, _ = Shop.objects.get_or_create(
        name="Test Shop", defaults={"brand_name": "Test", "short_name": "Test"}
    )
    if defaults is not None:
        shop.defaults = defaults
        shop.save(update_fields=["defaults"])
    return shop


def _channel(ref="web", config=None):
    from shopman.shop.models import Channel

    return Channel.objects.get_or_create(
        ref=ref, defaults={"name": ref, "is_active": True, "config": config or {}}
    )[0]


def _position(ref="loja"):
    from shopman.stockman.models import Position, PositionKind

    return Position.objects.get_or_create(
        ref=ref,
        defaults={"name": ref, "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )[0]


def _product(sku, price_q=1000, *, stock=None, **kwargs):
    """Cria um Product vendável. ``stock`` (int) recebe físico de HOJE."""
    from shopman.offerman.models import Product

    fields = {
        "sku": sku,
        "name": f"Produto {sku}",
        "base_price_q": price_q,
        "is_published": True,
        "is_sellable": True,
    }
    fields.update(kwargs)
    product = Product.objects.create(**fields)
    if stock is not None:
        _receive(sku, stock)
    return product


def _receive(sku, qty, *, target_date=None, position=None):
    from shopman.stockman import stock as stock_mod
    from shopman.stockman.models import Move

    pos = position or _position()
    kwargs = {"reason": "edge-case test setup"}
    if target_date is not None:
        kwargs["target_date"] = target_date
        kwargs["kind"] = Move.Kind.MAKE
    stock_mod.receive(Decimal(str(qty)), sku, pos, **kwargs)


def _promotion(name, *, ptype, value, skus=None, min_order_q=0, coupon_code=None, **kwargs):
    """Cria uma Promotion. Se ``coupon_code`` for dado, cria o Coupon atrelado
    (e a promo deixa de ser 'automática' — só aplica via cupom)."""
    from shopman.storefront.models import Coupon, Promotion

    max_uses = kwargs.pop("max_uses", 0)
    now = timezone.now()
    promo = Promotion.objects.create(
        name=name,
        type=ptype,
        value=value,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
        skus=skus or [],
        min_order_q=min_order_q,
        **kwargs,
    )
    coupon = None
    if coupon_code is not None:
        coupon = Coupon.objects.create(code=coupon_code, promotion=promo, max_uses=max_uses)
    return promo, coupon


def _rule(ref, rule_path, params, *, enabled=True, channel=None):
    """Cria um RuleConfig (gate dos modifiers rule-driven). Sem ``channel`` =
    global (todos os canais)."""
    from shopman.shop.models import RuleConfig

    rc = RuleConfig.objects.create(
        ref=ref, rule_path=rule_path, label=ref, enabled=enabled, params=params
    )
    if channel is not None:
        rc.channels.add(channel)
    _bust_rules_cache()
    return rc


def _bust_rules_cache():
    from django.core.cache import cache

    from shopman.shop.rules.engine import CACHE_KEY

    cache.delete(CACHE_KEY)


def _reprice(session, ops):
    """Aplica ops no pipeline REAL (cadeia completa de modifiers) e devolve a
    sessão recarregada do banco."""
    from shopman.orderman.models import Session

    from shopman.shop.services import sessions

    sessions.modify_session(
        session_key=session.session_key, channel_ref=session.channel_ref, ops=ops
    )
    return Session.objects.get(pk=session.pk)


def _line(sku, name=None, qty=1, unit_price_q=None):
    op = {"op": "add_line", "sku": sku, "name": name or sku, "qty": qty}
    if unit_price_q is not None:
        op["unit_price_q"] = unit_price_q
    return op


def _merch_total_q(session):
    """Total cobrado de mercadoria (o que o pedido soma), ignorando linhas de taxa."""
    return sum(
        int(i.get("line_total_q", 0))
        for i in (session.items or [])
        if i.get("sku") != "__DELIVERY_FEE__"
        and (i.get("meta") or {}).get("type") != "delivery_fee"
    )


def _unit_price(session, sku):
    for i in session.items or []:
        if i.get("sku") == sku:
            return int(i.get("unit_price_q", 0))
    raise AssertionError(f"linha {sku} não encontrada")


# Dotted paths dos rules (gate dos modifiers)
D1_RULE = "shopman.shop.rules.pricing.D1Rule"
HAPPY_RULE = "shopman.shop.rules.pricing.HappyHourRule"
EMPLOYEE_RULE = "shopman.shop.rules.pricing.EmployeeRule"

PERCENT = "percent"
FIXED = "fixed"


# ═════════════════════════════════════════════════════════════════════════════
# PRICING & PROMOTIONS
# ═════════════════════════════════════════════════════════════════════════════


class TestD1Discount:
    """1. D-1 (sobras do dia anterior)."""

    def _session_with_d1(self, sku, price_q=1000, *, d1_percent=50):
        from shopman.shop.services import sessions

        _shop()
        _channel("web")
        _product(sku, price_q)
        _rule("d1_discount", D1_RULE, {"discount_percent": d1_percent})
        s = sessions.create_session("web")
        return _reprice(
            s,
            [
                _line(sku, qty=1),
                {"op": "set_data", "path": "availability", "value": {sku: {"is_d1": True}}},
            ],
        )

    def test_d1_percent_applied(self):
        s = self._session_with_d1("PAO-D1", 1000, d1_percent=50)
        assert _unit_price(s, "PAO-D1") == 500
        assert s.pricing.get("d1_discount", {}).get("total_discount_q") == 500

    def test_modifiers_applied_marker_is_lost_after_persist(self):
        """CAUSA RAIZ do bug de empilhamento: Session.update_items() normaliza a
        linha e DESCARTA `modifiers_applied` (só sobrevivem line_id/sku/name/qty/
        unit_price_q/line_total_q/meta). Como os guards anti-stacking da
        DiscountModifier/TimeWindowDiscountModifier leem esse marcador, eles ficam
        cegos entre um modifier e o próximo dentro da MESMA passagem de repricing.
        """
        s = self._session_with_d1("PAO-D1", 1000, d1_percent=50)
        line = next(i for i in s.items if i.get("sku") == "PAO-D1")
        # O desconto foi aplicado (pricing registra), mas o marcador na linha sumiu.
        assert "d1_discount" in s.pricing
        assert "modifiers_applied" not in line

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "BUG P1 — auto-promoção EMPILHA sobre D-1. O guard da DiscountModifier "
            "(`is_d1_line = any(m['type']=='d1_discount' ...)`) depende de "
            "`modifiers_applied`, que Session.update_items() (_normalize_items) "
            "descarta entre um modifier e o próximo. Resultado observado: 350 "
            "(500 do D-1, depois −30% da promo sobre o preço JÁ descontado), "
            "violando 'D-1 tem prioridade absoluta' (modifiers.py)."
        ),
    )
    def test_d1_does_not_stack_with_auto_promotion(self):
        """D-1 tem prioridade absoluta: promoção automática NÃO deve acumular."""
        from shopman.shop.services import sessions

        _shop()
        _channel("web")
        _product("PAO-D1", 1000)
        _rule("d1_discount", D1_RULE, {"discount_percent": 50})
        # Promoção automática de 30% no mesmo SKU.
        _promotion("Promo Pão", ptype=PERCENT, value=30, skus=["PAO-D1"])
        s = sessions.create_session("web")
        s = _reprice(
            s,
            [
                _line("PAO-D1", qty=1),
                {"op": "set_data", "path": "availability", "value": {"PAO-D1": {"is_d1": True}}},
            ],
        )
        # Invariante desejada: só o D-1 (50%). (Hoje o pipeline entrega 350.)
        assert _unit_price(s, "PAO-D1") == 500

    def test_d1_stacking_bug_actual_numbers(self):
        """Fixa os números REAIS do bug acima (guarda de regressão até o fix).

        Enquanto o guard não for corrigido, a promo empilha: 1000 → 500 (D-1) →
        350 (−30% sobre 500). Este teste passa HOJE e vai FALHAR quando o bug for
        corrigido — sinal para trocar o xfail acima por asserção normal.
        """
        from shopman.shop.services import sessions

        _shop()
        _channel("web")
        _product("PAO-D1", 1000)
        _rule("d1_discount", D1_RULE, {"discount_percent": 50})
        _promotion("Promo Pão", ptype=PERCENT, value=30, skus=["PAO-D1"])
        s = sessions.create_session("web")
        s = _reprice(
            s,
            [
                _line("PAO-D1", qty=1),
                {"op": "set_data", "path": "availability", "value": {"PAO-D1": {"is_d1": True}}},
            ],
        )
        assert _unit_price(s, "PAO-D1") == 350  # comportamento atual (bug)
        # Ambos os descontos ficam registrados no pricing — dupla contagem.
        assert "d1_discount" in s.pricing and "discount" in s.pricing

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "BUG P1 (mesma causa raiz) — cupom EMPILHA sobre D-1. modifiers_applied "
            "some no update_items, então o guard de D-1 na DiscountModifier não vê a "
            "linha como D-1 e aplica o cupom. Observado: 300 (500 do D-1, −40% do "
            "cupom sobre 500)."
        ),
    )
    def test_d1_does_not_stack_with_manual_coupon(self):
        """Cupom (percentual) NÃO deve aplicar em linha D-1 (sem aprovação)."""
        from shopman.shop.services import sessions

        _shop()
        _channel("web")
        _product("PAO-D1", 1000)
        _rule("d1_discount", D1_RULE, {"discount_percent": 50})
        _promotion("Cupom 40", ptype=PERCENT, value=40, skus=["PAO-D1"], coupon_code="QUARENTA")
        s = sessions.create_session("web")
        s = _reprice(
            s,
            [
                _line("PAO-D1", qty=1),
                {"op": "set_data", "path": "availability", "value": {"PAO-D1": {"is_d1": True}}},
                {"op": "set_data", "path": "coupon_code", "value": "QUARENTA"},
            ],
        )
        # Invariante desejada: cupom ignorado na linha D-1 → fica só o D-1 (50%).
        assert _unit_price(s, "PAO-D1") == 500


class TestHappyHour:
    """2. Happy hour — janela de tempo. Bordas exatas testadas no modifier
    (localtime determinístico)."""

    def _apply_at(self, hour, minute, *, start, end, percent=25, price_q=1000):
        from shopman.shop.modifiers import TimeWindowDiscountModifier

        session = SimpleNamespace(
            items=[{"sku": "P", "unit_price_q": price_q, "qty": 1}],
            data={},
            pricing={},
        )
        session.update_items = lambda items: None
        session.save = lambda **kw: None
        fake = SimpleNamespace(time=lambda: time(hour, minute))
        with (
            patch(
                "shopman.shop.rules.engine.get_channel_rule_params",
                return_value={"discount_percent": percent, "start": start, "end": end},
            ),
            patch("django.utils.timezone.localtime", return_value=fake),
        ):
            TimeWindowDiscountModifier().apply(channel=SimpleNamespace(ref="web"), session=session, ctx={})
        return session.items[0]["unit_price_q"]

    def test_inside_window(self):
        assert self._apply_at(17, 45, start="17:30", end="18:00") == 750

    def test_outside_window(self):
        assert self._apply_at(16, 0, start="17:30", end="18:00") == 1000

    def test_boundary_start_is_inclusive(self):
        # start <= now < end  → no minuto de início já vale.
        assert self._apply_at(17, 30, start="17:30", end="18:00") == 750

    def test_boundary_end_is_exclusive(self):
        # No minuto exato do fim NÃO vale mais.
        assert self._apply_at(18, 0, start="17:30", end="18:00") == 1000

    def test_happy_hour_skips_employee_line_in_isolation(self):
        """No modifier isolado, happy hour PULA linha com desconto de funcionário
        (guard `modifiers_applied`)."""
        from shopman.shop.modifiers import TimeWindowDiscountModifier

        session = SimpleNamespace(
            items=[{
                "sku": "P", "unit_price_q": 1000, "qty": 1,
                "modifiers_applied": [{"type": "employee_discount"}],
            }],
            data={},
            pricing={},
        )
        session.update_items = lambda items: None
        session.save = lambda **kw: None
        fake = SimpleNamespace(time=lambda: time(12, 0))
        with (
            patch(
                "shopman.shop.rules.engine.get_channel_rule_params",
                return_value={"discount_percent": 20, "start": "00:00", "end": "23:59"},
            ),
            patch("django.utils.timezone.localtime", return_value=fake),
        ):
            TimeWindowDiscountModifier().apply(channel=SimpleNamespace(ref="web"), session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 1000  # não empilha


class TestEmployeeDiscount:
    """3. Desconto de funcionário (customer_group == staff)."""

    def _staff_session(self, group="staff", price_q=1000, percent=20):
        from shopman.shop.services import sessions

        _shop()
        _channel("web")
        _product("PAO", price_q)
        _rule("employee_discount", EMPLOYEE_RULE, {"discount_percent": percent})
        s = sessions.create_session("web")
        return _reprice(
            s,
            [
                _line("PAO", qty=1),
                {"op": "set_data", "path": "customer", "value": {"group": group}},
            ],
        )

    def test_staff_gets_discount(self):
        s = self._staff_session(group="staff", percent=20)
        assert _unit_price(s, "PAO") == 800

    def test_non_staff_no_discount(self):
        """Cliente comum não recebe o desconto de funcionário (é gated por grupo,
        não por cupom 'FUNCIONARIO' — não existe cupom de funcionário no modelo)."""
        s = self._staff_session(group="regular", percent=20)
        assert _unit_price(s, "PAO") == 1000

    def test_staff_plus_d1_stacks(self):
        """ACHADO (revisar intenção de produto): staff + D-1 ACUMULAM.

        O D-1 (order 15) desconta 50% e marca a linha; o desconto de funcionário
        (order 60) aplica sobre TODAS as linhas não-congeladas, sem pular linha
        D-1 — logo 1000 → 500 (D-1) → 400 (−20% funcionário). O docstring do
        módulo diz "apenas UM desconto por item (o melhor)", mas o funcionário é
        pós-precificação e empilha. Pode ser perk intencional (funcionário sempre
        leva sua fatia) ou double-dip. Registrado para decisão de produto.
        """
        from shopman.shop.services import sessions

        _shop()
        _channel("web")
        _product("PAO-D1", 1000)
        _rule("d1_discount", D1_RULE, {"discount_percent": 50})
        _rule("employee_discount", EMPLOYEE_RULE, {"discount_percent": 20})
        s = sessions.create_session("web")
        s = _reprice(
            s,
            [
                _line("PAO-D1", qty=1),
                {"op": "set_data", "path": "availability", "value": {"PAO-D1": {"is_d1": True}}},
                {"op": "set_data", "path": "customer", "value": {"group": "staff"}},
            ],
        )
        assert _unit_price(s, "PAO-D1") == 400  # 50% D-1 e depois 20% funcionário


class TestQuantityPromotion:
    """4. Promoção por quantidade ("compre 3 pague 2")."""

    def test_no_bogo_percent_is_per_unit(self):
        """ACHADO (feature ausente por design): NÃO há promoção 'compre X pague Y'.

        O modelo Promotion só tem percentual e valor fixo — ``min_order_q`` é
        limiar de VALOR, não gatilho de quantidade. Um percentual aplica por
        unidade, independente da qty. 3× R$30 com 33% NÃO vira "pague 2" (R$60);
        vira R$60,30 (3 × R$20,10). Registrado: se BOGO for requisito de
        negócio, é feature nova (não bug).
        """
        from shopman.shop.services import sessions

        _shop()
        _channel("web")
        _product("BOLO", 3000)
        _promotion("Terço off", ptype=PERCENT, value=33, skus=["BOLO"])
        s = sessions.create_session("web")
        s = _reprice(s, [_line("BOLO", qty=3)])
        # 33% de 3000 = 990 → unit 2010 → linha 6030 (≠ 6000 de um "pague 2").
        assert _unit_price(s, "BOLO") == 2010
        assert _merch_total_q(s) == 6030


class TestBestDiscountWins:
    """5. Cupom percentual + promoção automática no mesmo item → melhor ganha
    (nunca stacka)."""

    def _run(self, auto_percent, coupon_percent):
        from shopman.shop.services import sessions

        _shop()
        _channel("web")
        _product("PAO", 1000)
        _promotion("Auto", ptype=PERCENT, value=auto_percent, skus=["PAO"])
        _promotion("Cupom", ptype=PERCENT, value=coupon_percent, skus=["PAO"], coupon_code="CUP")
        s = sessions.create_session("web")
        return _reprice(
            s,
            [_line("PAO", qty=1), {"op": "set_data", "path": "coupon_code", "value": "CUP"}],
        )

    def test_coupon_wins_when_bigger(self):
        s = self._run(auto_percent=20, coupon_percent=40)
        assert _unit_price(s, "PAO") == 600  # só o cupom (40%), não 60%

    def test_auto_wins_when_bigger(self):
        s = self._run(auto_percent=50, coupon_percent=40)
        assert _unit_price(s, "PAO") == 500  # só a auto (50%)


class TestExhaustedCoupon:
    """6. Cupom com max_uses atingido não desconta (silenciosamente 0, sem crash)."""

    def test_exhausted_coupon_does_not_discount(self):
        from shopman.shop.services import sessions

        _shop()
        _channel("web")
        _product("PAO", 1000)
        _, coupon = _promotion("Cupom", ptype=PERCENT, value=40, skus=["PAO"], coupon_code="CUP", max_uses=1)
        coupon.uses_count = 1
        coupon.save(update_fields=["uses_count"])

        s = sessions.create_session("web")
        s = _reprice(
            s,
            [_line("PAO", qty=1), {"op": "set_data", "path": "coupon_code", "value": "CUP"}],
        )
        # Não desconta e não persiste 'coupon' no pricing.
        assert _unit_price(s, "PAO") == 1000
        assert "coupon" not in (s.pricing or {})

    def test_invalid_coupon_code_is_ignored(self):
        from shopman.shop.services import sessions

        _shop()
        _channel("web")
        _product("PAO", 1000)
        s = sessions.create_session("web")
        s = _reprice(
            s,
            [_line("PAO", qty=1), {"op": "set_data", "path": "coupon_code", "value": "NAOEXISTE"}],
        )
        assert _unit_price(s, "PAO") == 1000


class TestNonNegativeTotal:
    """7. Total <= 0 via combinação de descontos — o sistema clampa em 0."""

    def test_100_percent_coupon_floors_at_zero(self):
        from shopman.shop.services import sessions

        _shop()
        _channel("web")
        _product("PAO", 1000)
        _promotion("Grátis", ptype=PERCENT, value=100, skus=["PAO"], coupon_code="FREE")
        s = sessions.create_session("web")
        s = _reprice(
            s,
            [_line("PAO", qty=1), {"op": "set_data", "path": "coupon_code", "value": "FREE"}],
        )
        assert _unit_price(s, "PAO") == 0
        assert _merch_total_q(s) == 0

    def test_percent_over_100_is_clamped(self):
        """Percentual digitado errado no admin (ex.: 150) nunca gera preço negativo."""
        from shopman.shop.services import sessions

        _shop()
        _channel("web")
        _product("PAO", 1000)
        _promotion("Bug 150%", ptype=PERCENT, value=150, skus=["PAO"])
        s = sessions.create_session("web")
        s = _reprice(s, [_line("PAO", qty=1)])
        assert _unit_price(s, "PAO") == 0
        assert _merch_total_q(s) >= 0

    def test_loyalty_redeem_over_subtotal_is_clamped(self):
        """Resgate de pontos maior que o subtotal é limitado ao subtotal."""
        from shopman.shop.services import sessions

        _shop()
        _channel("web")
        _product("PAO", 1000)
        s = sessions.create_session("web")
        s = _reprice(
            s,
            [
                _line("PAO", qty=1),
                {"op": "set_data", "path": "loyalty", "value": {"redeem_points_q": 5000}},
            ],
        )
        assert _merch_total_q(s) == 0
        # Débito de pontos == desconto realmente aplicado (nunca 5000).
        applied = (s.data.get("loyalty") or {}).get("applied_discount_q")
        assert applied == 1000


# ═════════════════════════════════════════════════════════════════════════════
# ESTOQUE & PRODUÇÃO
# ═════════════════════════════════════════════════════════════════════════════


def _open_cart(channel_ref, session_key, sku, qty, *, data=None):
    """Cria uma Session de commit direta (evita a cadeia de repricing)."""
    from shopman.orderman.models import Session

    return Session.objects.create(
        session_key=session_key,
        channel_ref=channel_ref,
        state="open",
        rev=1,
        items=[{"line_id": f"L-{session_key}", "sku": sku, "name": sku, "qty": qty, "unit_price_q": 1000}],
        data=data or {},
    )


def _commit(session_key, channel_ref, idem):
    from shopman.orderman.services.commit import CommitService

    return CommitService.commit(
        session_key=session_key, channel_ref=channel_ref, idempotency_key=idem
    )


class TestStockExactAndShortfall:
    """8. Estoque exato = qty: primeiro pedido fecha, segundo falha."""

    def test_exact_then_next_fails(self):
        from shopman.orderman.exceptions import ValidationError
        from shopman.orderman.models import Order

        _shop()
        ch = _channel("gate-web")
        _product("EX-SKU", 1000, stock=3)

        _open_cart(ch.ref, "SS-A", "EX-SKU", 3)
        _commit("SS-A", ch.ref, "K-A")  # consome os 3

        _open_cart(ch.ref, "SS-B", "EX-SKU", 1)
        with pytest.raises(ValidationError) as exc:
            _commit("SS-B", ch.ref, "K-B")
        assert exc.value.code == "insufficient_stock"
        assert Order.objects.filter(channel_ref=ch.ref).count() == 1


class TestPreorderPlanned:
    """9. Sem estoque hoje mas com produção planejada datada → encomenda fecha."""

    def test_preorder_against_planned_stock(self):
        from shopman.offerman.models import AvailabilityPolicy
        from shopman.orderman.models import Order

        _shop()
        ch = _channel("web")
        _product(
            "MINI-BAGUETE",
            1000,
            availability_policy=AvailabilityPolicy.PLANNED_OK,
            shelf_life_days=0,
        )
        target = timezone.localdate() + timedelta(days=2)
        _receive("MINI-BAGUETE", 50, target_date=target, position=_position("prod"))

        _open_cart(ch.ref, "PRE-OK", "MINI-BAGUETE", 5, data={"delivery_date": target.isoformat()})
        result = _commit("PRE-OK", ch.ref, "PRE-K")

        order = Order.objects.get(ref=result.order_ref)
        holds = (order.data or {}).get("hold_ids", [])
        assert len(holds) == 1 and holds[0].get("hold_id")


class TestNoStockNoProduction:
    """10. Sem estoque E sem produção planejada → rejeita de imediato.

    Canal com ``stock.preorder=False`` (PDV/marketplace) reprova; o default
    (encomenda 1ª classe) registraria demanda. Aqui provamos a recusa dura para
    o dia de HOJE (sem plano, sem físico)."""

    def test_same_day_no_stock_rejected(self):
        from shopman.orderman.exceptions import ValidationError
        from shopman.orderman.models import Order

        _shop()
        ch = _channel("gate-web")
        # Rastreado (tem Quant) mas com apenas 1 físico: pedido de 2 no MESMO dia
        # não tem como reservar → recusa dura (sem plano, sem demanda futura).
        _product("SEM-SKU", 1000, stock=1)

        _open_cart(ch.ref, "NO-SS", "SEM-SKU", 2)
        with pytest.raises(ValidationError) as exc:
            _commit("NO-SS", ch.ref, "NO-K")
        assert exc.value.code == "insufficient_stock"
        assert Order.objects.filter(channel_ref=ch.ref).count() == 0


class TestHoldExpiry:
    """11. Hold expira → estoque volta a ficar disponível."""

    def test_expired_hold_frees_stock(self):
        from shopman.stockman.models import Hold

        from shopman.shop.services import availability

        _shop()
        _channel("web")
        _product("HOLD-SKU", 1000, stock=3)

        r = availability.reserve("HOLD-SKU", Decimal("3"), session_key="SESS-HOLD", channel_ref=None)
        assert r["ok"]
        # Toda a disponibilidade está reservada.
        assert availability.check("HOLD-SKU", Decimal("1"), channel_ref=None)["ok"] is False

        # Expira o hold no passado (o que o backstop/TTL faria).
        Hold.objects.filter(metadata__reference="SESS-HOLD").update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        # Estoque volta a ser vendável (hold morto não conta).
        assert availability.check("HOLD-SKU", Decimal("3"), channel_ref=None)["ok"] is True


class TestCancellationReleasesHold:
    """12 / 19. Cancelamento libera holds → estoque retorna ao disponível."""

    def test_cancel_releases_holds_and_restores_stock(self, django_capture_on_commit_callbacks):
        from shopman.orderman.models import Order

        from shopman.shop.services import availability, cancellation

        _shop()
        ch = _channel("gate-web")
        _product("CAN-SKU", 1000, stock=3)

        _open_cart(ch.ref, "CAN-SS", "CAN-SKU", 3)
        result = _commit("CAN-SS", ch.ref, "CAN-K")
        order = Order.objects.get(ref=result.order_ref)
        assert availability.check("CAN-SKU", Decimal("1"), channel_ref=None)["ok"] is False

        with django_capture_on_commit_callbacks(execute=True):
            assert cancellation.cancel(order, reason="cliente desistiu", actor="operator") is True

        order.refresh_from_db()
        assert order.status == Order.Status.CANCELLED
        assert availability.check("CAN-SKU", Decimal("3"), channel_ref=None)["ok"] is True


class TestPerishableVsShelfStable:
    """13 / 14. Perecível (shelf_life=0) vs não-perecível (shelf_life>0) para
    data futura, com estoque físico de HOJE e canal SEM preorder (recusa dura,
    isola a regra de validade)."""

    def _channel_no_preorder(self):
        return _channel("noorder", config={"stock": {"preorder": False}})

    def test_perishable_cannot_use_today_stock_for_future(self):
        from shopman.offerman.models import AvailabilityPolicy
        from shopman.orderman.exceptions import ValidationError
        from shopman.orderman.models import Order

        _shop()
        ch = self._channel_no_preorder()
        _product(
            "PEREC",
            1000,
            stock=10,  # físico de HOJE
            availability_policy=AvailabilityPolicy.PLANNED_OK,
            shelf_life_days=0,  # vence hoje → inválido p/ amanhã
        )
        tomorrow = timezone.localdate() + timedelta(days=1)
        _open_cart(ch.ref, "PER-SS", "PEREC", 1, data={"delivery_date": tomorrow.isoformat()})

        with pytest.raises(ValidationError) as exc:
            _commit("PER-SS", ch.ref, "PER-K")
        assert exc.value.code == "insufficient_stock"
        assert Order.objects.filter(channel_ref=ch.ref).count() == 0

    def test_shelf_stable_can_use_today_stock_for_future(self):
        from shopman.offerman.models import AvailabilityPolicy
        from shopman.orderman.models import Order

        _shop()
        ch = self._channel_no_preorder()
        _product(
            "DURAVEL",
            1000,
            stock=10,  # físico de HOJE
            availability_policy=AvailabilityPolicy.PLANNED_OK,
            shelf_life_days=5,  # aguenta a data futura
        )
        tomorrow = timezone.localdate() + timedelta(days=1)
        _open_cart(ch.ref, "DUR-SS", "DURAVEL", 1, data={"delivery_date": tomorrow.isoformat()})

        result = _commit("DUR-SS", ch.ref, "DUR-K")
        order = Order.objects.get(ref=result.order_ref)
        holds = [h for h in (order.data or {}).get("hold_ids", []) if h.get("hold_id")]
        assert len(holds) == 1


# ═════════════════════════════════════════════════════════════════════════════
# CHECKOUT & DELIVERY
# ═════════════════════════════════════════════════════════════════════════════


_FAKE_SLOTS = [
    {"ref": "slot-09", "label": "A partir das 09h", "starts_at": "09:00"},
    {"ref": "slot-12", "label": "A partir das 12h", "starts_at": "12:00"},
    {"ref": "slot-15", "label": "A partir das 15h", "starts_at": "15:00"},
]


class TestPickupSlots:
    """15. Slots de retirada respeitam o expediente; slot no passado é rejeitado."""

    def _validate(self, slot, *, delivery_date="", now=None, closes_at):
        from shopman.storefront.services import pickup_slots

        with patch.object(pickup_slots, "get_slots", return_value=_FAKE_SLOTS):
            return pickup_slots.validate_pickup_slot_selection(
                slot, delivery_date=delivery_date, now=now, closes_at=closes_at
            )

    def test_past_slot_today_rejected(self):
        # 15h: slot-09 já foi superado.
        err = self._validate("slot-09", now=time(15, 0), closes_at=time(19, 0))
        assert err and "passou" in err.lower()

    def test_future_slot_today_ok(self):
        err = self._validate("slot-15", now=time(10, 0), closes_at=time(19, 0))
        assert err is None

    def test_after_close_no_pickup_today(self):
        """Depois do fechamento não há retirada hoje, mesmo no último slot."""
        err = self._validate("slot-15", now=time(19, 30), closes_at=time(19, 0))
        assert err and "fechou" in err.lower()

    def test_slot_starting_after_close_is_unreachable(self):
        # Fecha 11h: slot-12/15 começam depois do fechamento → inalcançáveis hoje.
        err = self._validate("slot-15", now=time(10, 0), closes_at=time(11, 0))
        assert err is not None


class TestDeliveryDate:
    """16. Data de entrega no passado é rejeitada."""

    def test_past_delivery_date_rejected(self):
        from shopman.storefront.intents.checkout import _validate_preorder

        yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
        errors = _validate_preorder(yesterday)
        assert "delivery_date" in errors
        assert "passada" in errors["delivery_date"].lower()

    def test_today_delivery_date_ok(self):
        from shopman.storefront.intents.checkout import _validate_preorder

        _shop()
        today = timezone.localdate().isoformat()
        errors = _validate_preorder(today)
        assert errors.get("delivery_date") is None


class TestDeliveryMinimum:
    """17. Pedido mínimo de entrega: carrinho abaixo do mínimo é rejeitado no
    commit (regra DeliveryZoneRule). Retirada nunca tem mínimo."""

    def _fake_session(self, *, fulfillment, items, fee_present=True):
        data = {"fulfillment_type": fulfillment}
        if fulfillment == "delivery" and fee_present:
            data["delivery_fee_q"] = 0
            data["delivery_address_structured"] = {"postal_code": "86010000", "city": "Londrina"}
        return SimpleNamespace(data=data, items=items, pricing={})

    def test_below_minimum_delivery_rejected(self):
        from shopman.orderman.exceptions import ValidationError as OrderValidationError

        from shopman.shop.rules.validation import DeliveryZoneRule

        _shop(defaults={"rules": {"delivery_minimum_q": 3000}})
        session = self._fake_session(
            fulfillment="delivery",
            items=[{"sku": "PAO", "line_total_q": 1000, "qty": 1}],
        )
        with pytest.raises(OrderValidationError) as exc:
            DeliveryZoneRule().validate(channel=SimpleNamespace(ref="web"), session=session, ctx={})
        assert exc.value.code == "below_delivery_minimum"

    def test_above_minimum_delivery_ok(self):
        from shopman.shop.rules.validation import DeliveryZoneRule

        _shop(defaults={"rules": {"delivery_minimum_q": 3000}})
        session = self._fake_session(
            fulfillment="delivery",
            items=[{"sku": "PAO", "line_total_q": 5000, "qty": 1}],
        )
        # Não levanta.
        DeliveryZoneRule().validate(channel=SimpleNamespace(ref="web"), session=session, ctx={})

    def test_pickup_never_has_minimum(self):
        from shopman.shop.rules.validation import DeliveryZoneRule

        _shop(defaults={"rules": {"delivery_minimum_q": 3000}})
        session = self._fake_session(
            fulfillment="pickup",
            items=[{"sku": "PAO", "line_total_q": 500, "qty": 1}],
            fee_present=False,
        )
        DeliveryZoneRule().validate(channel=SimpleNamespace(ref="web"), session=session, ctx={})


class TestChangeFor:
    """18. Troco (troco para R$ X) no pagamento em dinheiro."""

    def test_parse_change_for_variants(self):
        from shopman.storefront.intents.checkout import parse_change_for

        assert parse_change_for("50") == 5000
        assert parse_change_for("50,50") == 5050
        assert parse_change_for("R$ 100,00") == 10000
        assert parse_change_for("-10") == 0  # negativo → 0
        assert parse_change_for("abc") == 0

    def test_change_for_less_than_total_not_validated_server_side(self):
        """ACHADO (nuance de UX): o servidor NÃO valida troco < total.

        ``parse_change_for`` só converte Reais→centavos e clampa negativos em 0.
        Um "troco para R$ 5" num pedido de R$ 40 é aceito e guardado — a
        conciliação fica com o operador/motoboy. Registrado: se a loja quiser
        barrar troco insuficiente, é validação nova no checkout.
        """
        from shopman.storefront.intents.checkout import parse_change_for

        change_for_q = parse_change_for("5")  # R$ 5,00
        assert change_for_q == 500  # aceito sem comparar com o total do pedido


# ═════════════════════════════════════════════════════════════════════════════
# LIFECYCLE
# ═════════════════════════════════════════════════════════════════════════════


class TestCancellationTerminalGuard:
    """20. Pedido em estado terminal não pode ser cancelado de novo (guard)."""

    def test_cannot_cancel_already_cancelled(self, django_capture_on_commit_callbacks):
        from shopman.orderman.models import Order

        from shopman.shop.services import cancellation

        _shop()
        ch = _channel("gate-web")
        _product("TERM-SKU", 1000, stock=2)
        _open_cart(ch.ref, "TERM-SS", "TERM-SKU", 1)
        result = _commit("TERM-SS", ch.ref, "TERM-K")
        order = Order.objects.get(ref=result.order_ref)

        with django_capture_on_commit_callbacks(execute=True):
            assert cancellation.cancel(order, reason="1x", actor="op") is True
        order.refresh_from_db()
        # Segunda tentativa: estado terminal → recusa (retorna False, não crash).
        assert cancellation.cancel(order, reason="2x", actor="op") is False


class TestNotificationTemplate:
    """21. Template de notificação por evento.

    ACHADO (premissa do QA vs modelo): NotificationTemplate é chaveado por
    ``event`` (unique), NÃO por canal. O roteamento por canal é a escolha do
    BACKEND de notificação (ChannelConfig.notification), não do template. Aqui
    provamos que a resolução é por evento e que não há dimensão de canal.
    """

    def test_template_is_keyed_by_event_not_channel(self):
        from django.db import IntegrityError

        from shopman.shop.models import NotificationTemplate

        _shop()
        NotificationTemplate.objects.create(
            event="order_confirmed", subject="Pedido confirmado", body="Olá {name}"
        )
        # 'event' é unique — não há como ter um template 'order_confirmed' por canal.
        with pytest.raises(IntegrityError):
            NotificationTemplate.objects.create(
                event="order_confirmed", subject="Outro", body="x"
            )
