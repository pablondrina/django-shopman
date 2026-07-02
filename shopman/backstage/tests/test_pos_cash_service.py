"""POS cash-register service tests."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from shopman.backstage.models import CashMovement, CashShift, POSTerminal
from shopman.backstage.services import pos
from shopman.backstage.services.exceptions import POSError


@pytest.fixture
def operator(db):
    return User.objects.create_user(username="cash-service", password="x", is_staff=True)


def test_parse_money_to_q_accepts_common_operator_inputs():
    assert pos.parse_money_to_q("12,34") == 1234
    assert pos.parse_money_to_q("12.34") == 1234
    assert pos.parse_money_to_q("-10") == -1000  # ajuste de falta
    assert pos.parse_money_to_q("") == 0


def test_parse_money_to_q_rejects_garbage_loudly():
    # Fechamento CEGO: typo virar 0 silencioso = diferença gigante sem aviso.
    with pytest.raises(POSError):
        pos.parse_money_to_q("bad")
    with pytest.raises(POSError):
        pos.parse_money_to_q("12,,30")


@pytest.mark.django_db
def test_open_cash_shift_creates_or_returns_current_shift(operator):
    shift = pos.open_cash_shift(operator=operator, opening_amount_raw="50,00")
    same = pos.open_cash_shift(operator=operator, opening_amount_raw="99,00")

    assert shift.pk == same.pk
    assert shift.opening_amount_q == 5000
    assert CashShift.objects.count() == 1
    assert shift.terminal == POSTerminal.default()


@pytest.mark.django_db
def test_open_cash_shift_blocks_terminal_double_open(operator):
    other = User.objects.create_user(username="other-cash", password="x", is_staff=True)
    terminal = POSTerminal.default()
    pos.open_cash_shift(operator=operator, terminal_ref=terminal.ref)

    with pytest.raises(POSError):
        pos.open_cash_shift(operator=other, terminal_ref=terminal.ref)


@pytest.mark.django_db
def test_register_cash_movement_requires_open_session(operator):
    with pytest.raises(POSError):
        pos.register_cash_movement(operator=operator, amount_raw="10")


@pytest.mark.django_db
def test_register_cash_movement_validates_amount_and_normalizes_type(operator):
    session = CashShift.objects.create(operator=operator, opening_amount_q=0)

    with pytest.raises(POSError):
        pos.register_cash_movement(operator=operator, amount_raw="0")

    movement = pos.register_cash_movement(
        operator=operator,
        movement_type="unknown",
        amount_raw="25,50",
        reason="troco",
    )

    assert movement.shift_id == session.pk
    assert movement.movement_type == "sangria"
    assert movement.amount_q == 2550
    assert movement.created_by == operator.username
    assert CashMovement.objects.count() == 1


@pytest.mark.django_db
def test_close_cash_shift_requires_open_shift(operator):
    with pytest.raises(POSError):
        pos.close_cash_shift(operator=operator, closing_amount_raw="0")


@pytest.mark.django_db
def test_close_cash_shift_closes_and_records_notes(operator):
    CashShift.objects.create(operator=operator, opening_amount_q=1000)

    shift = pos.close_cash_shift(
        operator=operator,
        closing_amount_raw="10,00",
        notes="fim do turno",
    )

    assert shift.status == CashShift.Status.CLOSED
    assert shift.blind_closing_amount_q == 1000
    assert shift.notes == "fim do turno"


@pytest.mark.django_db
def test_cash_shift_result_is_blind_to_operator(operator):
    """The operator close response never exposes the expected amount or variance."""
    from shopman.backstage.api.operations import _cash_shift_result

    terminal = POSTerminal.default()
    shift = CashShift.objects.create(operator=operator, terminal=terminal, opening_amount_q=1000)
    shift.close(blind_closing_amount_q=800)

    # The shift still stores the variance for manager review...
    assert shift.expected_amount_q == 1000
    assert shift.difference_q == -200

    # ...but the operator-facing payload hides both.
    result = _cash_shift_result(shift)
    assert result["blind_closing_amount_q"] == 800
    assert "expected_amount_q" not in result
    assert "difference_q" not in result


@pytest.mark.django_db
def test_close_cash_shift_counts_terminal_cash_not_delivery_cash(operator):
    from shopman.orderman.models import Order

    terminal = POSTerminal.default()
    shift = CashShift.objects.create(operator=operator, terminal=terminal, opening_amount_q=1000)
    Order.objects.create(
        ref="POS-CASH-TERMINAL",
        channel_ref=terminal.channel_ref,
        session_key="pos-cash-terminal",
        total_q=2000,
        data={
            "pos": {"cash_shift_id": shift.pk},
            "payment": {
                "method": "cash",
                "collection": "terminal",
                "cash_received_q": 2000,
            },
        },
    )
    Order.objects.create(
        ref="POS-CASH-DELIVERY",
        channel_ref=terminal.channel_ref,
        session_key="pos-cash-delivery",
        total_q=3000,
        data={
            "pos": {"cash_shift_id": shift.pk},
            "payment": {
                "method": "cash",
                "collection": "on_delivery",
            },
        },
    )

    shift.close(blind_closing_amount_q=3000)

    assert shift.expected_amount_q == 3000
    assert shift.difference_q == 0


@pytest.mark.django_db
def test_two_open_shifts_do_not_double_count_untagged_sale(operator):
    """Venda cash sem tag de turno é ADOTADA pelo 1º fechamento que a conta.

    Regressão do audit: com dois terminais abertos no mesmo canal, o
    catch-all por created_at somava a mesma venda no expected dos DOIS turnos.
    """
    from shopman.orderman.models import Order

    other_op = User.objects.create_user(username="cash-op-2", password="x", is_staff=True)
    terminal_a = POSTerminal.default()
    terminal_b = POSTerminal.objects.create(ref="pos-2", label="POS 2", channel_ref=terminal_a.channel_ref)
    shift_a = CashShift.objects.create(operator=operator, terminal=terminal_a, opening_amount_q=0)
    shift_b = CashShift.objects.create(operator=other_op, terminal=terminal_b, opening_amount_q=0)

    Order.objects.create(
        ref="POS-CASH-ORPHAN",
        channel_ref=terminal_a.channel_ref,
        session_key="pos-cash-orphan",
        total_q=2000,
        data={"payment": {"method": "cash", "collection": "terminal", "cash_received_q": 2000}},
    )

    shift_a.close(blind_closing_amount_q=2000)
    assert shift_a.expected_amount_q == 2000

    shift_b.close(blind_closing_amount_q=0)
    # O turno B NÃO conta a venda adotada pelo A.
    assert shift_b.expected_amount_q == 0


@pytest.mark.django_db
def test_negative_adjustment_reduces_expected(operator):
    shift = CashShift.objects.create(operator=operator, terminal=POSTerminal.default(), opening_amount_q=1000)
    pos.register_cash_movement(
        operator=operator, movement_type="ajuste", amount_raw="-5,00", reason="falta na conferência"
    )

    shift.close(blind_closing_amount_q=500)
    assert shift.expected_amount_q == 500
    assert shift.difference_q == 0


def test_mixed_tender_change_comes_from_cash_not_electronic():
    """Troco de venda mista sai do dinheiro — a maquininha capturou inteiro."""
    from shopman.shop.services.pos import _reconcile_tenders_to_total

    tenders = [
        {"method": "cash", "amount_q": 5000, "collection": "terminal"},
        {"method": "pix", "amount_q": 2000, "collection": "terminal"},
    ]
    _reconcile_tenders_to_total(tenders, 6000)

    assert tenders[0]["amount_q"] == 4000  # cash absorve o troco de 10
    assert tenders[1]["amount_q"] == 2000  # pix intocado


@pytest.mark.django_db
def test_cod_cash_counted_by_collecting_shift_not_creating_shift(operator):
    """COD coletado por um turno diferente do que criou a venda é contado pelo
    turno que COLETOU (regressão do code-review: o guard pos_shift_id cegava o
    ramo COD e o dinheiro sumia dos dois fechamentos)."""
    from shopman.orderman.models import Order

    other_op = User.objects.create_user(username="cod-op-2", password="x", is_staff=True)
    terminal_a = POSTerminal.default()
    terminal_b = POSTerminal.objects.create(ref="pos-cod-2", label="POS 2", channel_ref=terminal_a.channel_ref)
    shift_a = CashShift.objects.create(operator=operator, terminal=terminal_a, opening_amount_q=0)
    shift_b = CashShift.objects.create(operator=other_op, terminal=terminal_b, opening_amount_q=0)

    # Venda criada no turno A, COD coletado (settle) pelo turno B.
    Order.objects.create(
        ref="POS-COD-DIFF-SHIFT",
        channel_ref=terminal_a.channel_ref,
        session_key="pos-cod-diff",
        total_q=3000,
        data={
            "pos": {"cash_shift_id": shift_a.pk},
            "payment": {
                "method": "cash",
                "collection": "on_delivery",
                "cash_received_q": 3000,
                "cod_cash_shift_id": shift_b.pk,
            },
        },
    )

    shift_b.close(blind_closing_amount_q=3000)
    assert shift_b.expected_amount_q == 3000  # B conta o que coletou

    shift_a.close(blind_closing_amount_q=0)
    assert shift_a.expected_amount_q == 0  # A não conta (não coletou)


@pytest.mark.django_db
def test_close_is_atomic_rolls_back_adoption_on_failure(operator, monkeypatch):
    """Se o save final do turno falhar, as adoções de vendas órfãs revertem
    (nenhum pedido fica carimbado a um turno que não fechou)."""
    from shopman.orderman.models import Order

    terminal = POSTerminal.default()
    shift = CashShift.objects.create(operator=operator, terminal=terminal, opening_amount_q=0)
    order = Order.objects.create(
        ref="POS-ATOMIC-1",
        channel_ref=terminal.channel_ref,
        session_key="pos-atomic-1",
        total_q=1000,
        data={"payment": {"method": "cash", "collection": "terminal", "cash_received_q": 1000}},
    )

    # Falha no save final do turno (após o laço de adoção).
    original_save = CashShift.save

    def boom(self, *args, **kwargs):
        if "expected_amount_q" in (kwargs.get("update_fields") or []):
            raise RuntimeError("disco cheio")
        return original_save(self, *args, **kwargs)

    monkeypatch.setattr(CashShift, "save", boom)
    with pytest.raises(RuntimeError):
        shift.close(blind_closing_amount_q=1000)

    # A adoção do pedido reverteu junto — não ficou carimbado.
    order.refresh_from_db()
    assert (order.data.get("pos") or {}).get("cash_shift_id") != shift.pk
