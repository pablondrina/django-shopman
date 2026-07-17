from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from shopman.orderman.models import Order

from shopman.backstage.models import CashShift, POSTerminal
from shopman.backstage.services import pos as pos_service

REPORT_URL = "/api/v1/backstage/pos/cash/report/"


def _make_shop():
    from shopman.shop.models import Shop

    return Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})[0]


def _grant_operate_pos(user):
    ct = ContentType.objects.get_for_model(CashShift)
    perm = Permission.objects.get(content_type=ct, codename="operate_pos")
    user.user_permissions.add(perm)


class POSCashReportTests(TestCase):
    """Relatório X/Z da antesala do PDV (ADMIN-ROLE-PLAN WP-ADM-4).

    Leitura X = parcial do turno ABERTO do operador; Z = turnos FECHADOS do
    dia; histórico = totais agregados. BLIND COUNT: o PDV nunca revela o valor
    ESPERADO da gaveta nem a variância — nem no X, nem no Z. A conferência é
    da retaguarda; aqui garantimos por contrato que essas chaves NÃO existem
    na resposta.
    """

    def setUp(self) -> None:
        _make_shop()
        User = get_user_model()
        self.operator = User.objects.create_user(username="caixa", password="x", is_staff=True)
        _grant_operate_pos(self.operator)
        self.client.force_login(self.operator)
        self.terminal = POSTerminal.default()

    # ── helpers ────────────────────────────────────────────────────────

    def _open_shift(self, *, opening="50,00") -> CashShift:
        return pos_service.open_cash_shift(
            operator=self.operator,
            opening_amount_raw=opening,
            terminal_ref=self.terminal.ref,
        )

    def _sale(self, ref: str, *, shift: CashShift, total_q: int, tenders: list[dict]) -> Order:
        return Order.objects.create(
            ref=ref,
            channel_ref=self.terminal.channel_ref,
            session_key=f"sess-{ref}",
            total_q=total_q,
            data={
                "pos": {"cash_shift_id": shift.pk},
                "payment": {"method": "mixed" if len(tenders) > 1 else tenders[0]["method"], "tenders": tenders},
            },
        )

    # ── gate ───────────────────────────────────────────────────────────

    def test_report_requires_operate_pos_permission(self) -> None:
        User = get_user_model()
        other = User.objects.create_user(username="sem-perm", password="x", is_staff=True)
        self.client.force_login(other)

        resp = self.client.get(REPORT_URL)

        self.assertEqual(resp.status_code, 403)

    # ── leitura X (turno aberto) ───────────────────────────────────────

    def test_x_reading_shows_opening_movements_and_sales_by_method(self) -> None:
        shift = self._open_shift(opening="50,00")
        pos_service.register_cash_movement(
            operator=self.operator, movement_type="sangria", amount_raw="20,00", reason="troco banco",
        )
        pos_service.register_cash_movement(
            operator=self.operator, movement_type="suprimento", amount_raw="10,00", reason="reforço",
        )
        self._sale(
            "POS-X-CASH", shift=shift, total_q=3000,
            tenders=[{"method": "cash", "amount_q": 3000, "collection": "terminal", "cash_shift_id": shift.pk}],
        )
        self._sale(
            "POS-X-PIX", shift=shift, total_q=2500,
            tenders=[{"method": "pix", "amount_q": 2500, "collection": "terminal"}],
        )

        resp = self.client.get(REPORT_URL)

        self.assertEqual(resp.status_code, 200)
        report = resp.json()["report"]
        self.assertTrue(report["has_open_shift"])
        x = report["x_reading"]
        self.assertEqual(x["shift_id"], shift.pk)
        self.assertEqual(x["status"], "open")
        self.assertEqual(x["operator"], "caixa")
        self.assertEqual(x["opening_amount_q"], 5000)
        self.assertEqual(x["sales_count"], 2)
        self.assertEqual(x["sales_total_q"], 5500)
        by_method = {row["method"]: row for row in x["sales_by_method"]}
        self.assertEqual(by_method["cash"]["amount_q"], 3000)
        self.assertEqual(by_method["pix"]["amount_q"], 2500)
        kinds = [(m["kind"], m["amount_q"]) for m in x["movements"]]
        self.assertEqual(kinds, [("sangria", 2000), ("suprimento", 1000)])
        self.assertEqual(x["movements_in_q"], 1000)
        self.assertEqual(x["movements_out_q"], 2000)
        # Turno aberto: contagem ainda não existe.
        self.assertIsNone(x["counted_amount_q"])

    def test_x_reading_never_exposes_expected_drawer_amount(self) -> None:
        """BLIND COUNT: nenhuma chave de esperado/variância na resposta."""
        shift = self._open_shift(opening="100,00")
        self._sale(
            "POS-X-BLIND", shift=shift, total_q=4000,
            tenders=[{"method": "cash", "amount_q": 4000, "collection": "terminal", "cash_shift_id": shift.pk}],
        )

        resp = self.client.get(REPORT_URL)

        self.assertEqual(resp.status_code, 200)
        raw = json.dumps(resp.json())
        self.assertNotIn("expected", raw)
        self.assertNotIn("difference", raw)

    def test_x_reading_absent_without_open_shift(self) -> None:
        resp = self.client.get(REPORT_URL)

        self.assertEqual(resp.status_code, 200)
        report = resp.json()["report"]
        self.assertFalse(report["has_open_shift"])
        self.assertIsNone(report["x_reading"])
        self.assertEqual(report["z_readings"], [])
        self.assertEqual(report["day_totals"]["shifts_count"], 0)

    def test_x_reading_ignores_sales_tagged_to_another_shift(self) -> None:
        other_operator = get_user_model().objects.create_user(
            username="outro-caixa", password="x", is_staff=True,
        )
        other_terminal = POSTerminal.objects.create(
            ref="pdv-2", label="PDV 2", channel_ref=self.terminal.channel_ref,
        )
        other_shift = pos_service.open_cash_shift(
            operator=other_operator, terminal_ref=other_terminal.ref,
        )
        shift = self._open_shift()
        self._sale(
            "POS-OTHER-SHIFT", shift=other_shift, total_q=9900,
            tenders=[{"method": "cash", "amount_q": 9900, "collection": "terminal", "cash_shift_id": other_shift.pk}],
        )

        resp = self.client.get(REPORT_URL)

        x = resp.json()["report"]["x_reading"]
        self.assertEqual(x["shift_id"], shift.pk)
        self.assertEqual(x["sales_count"], 0)
        self.assertEqual(x["sales_by_method"], [])

    # ── leituras Z (turnos fechados) + histórico ───────────────────────

    def test_z_readings_list_closed_shifts_with_counted_and_totals(self) -> None:
        shift = self._open_shift(opening="50,00")
        pos_service.register_cash_movement(
            operator=self.operator, movement_type="sangria", amount_raw="15,00", reason="banco",
        )
        self._sale(
            "POS-Z-CASH", shift=shift, total_q=3000,
            tenders=[{"method": "cash", "amount_q": 3000, "collection": "terminal", "cash_shift_id": shift.pk}],
        )
        self._sale(
            "POS-Z-CARD", shift=shift, total_q=4500,
            tenders=[{"method": "card", "amount_q": 4500, "collection": "terminal"}],
        )
        pos_service.close_cash_shift(operator=self.operator, closing_amount_raw="63,00", notes="ok")

        resp = self.client.get(REPORT_URL)

        self.assertEqual(resp.status_code, 200)
        report = resp.json()["report"]
        self.assertFalse(report["has_open_shift"])
        self.assertTrue(report["has_closed_shifts"])
        self.assertEqual(len(report["z_readings"]), 1)
        z = report["z_readings"][0]
        self.assertEqual(z["status"], "closed")
        self.assertEqual(z["operator"], "caixa")
        self.assertEqual(z["opening_amount_q"], 5000)
        self.assertEqual(z["counted_amount_q"], 6300)
        self.assertEqual(z["sales_count"], 2)
        self.assertEqual(z["sales_total_q"], 7500)
        self.assertEqual(z["movements_out_q"], 1500)
        self.assertEqual(z["notes"], "ok")
        by_method = {row["method"]: row for row in z["sales_by_method"]}
        self.assertEqual(by_method["cash"]["amount_q"], 3000)
        self.assertEqual(by_method["card"]["amount_q"], 4500)

        totals = report["day_totals"]
        self.assertEqual(totals["shifts_count"], 1)
        self.assertEqual(totals["sales_count"], 2)
        self.assertEqual(totals["sales_total_q"], 7500)
        self.assertEqual(totals["counted_total_q"], 6300)

    def test_z_reading_never_exposes_expected_nor_variance(self) -> None:
        """O turno fechado TEM expected/difference no model; o PDV não os serve."""
        shift = self._open_shift(opening="10,00")
        self._sale(
            "POS-Z-BLIND", shift=shift, total_q=2000,
            tenders=[{"method": "cash", "amount_q": 2000, "collection": "terminal", "cash_shift_id": shift.pk}],
        )
        pos_service.close_cash_shift(operator=self.operator, closing_amount_raw="25,00")
        shift.refresh_from_db()
        self.assertIsNotNone(shift.expected_amount_q)  # o model calcula…

        resp = self.client.get(REPORT_URL)

        raw = json.dumps(resp.json())  # …mas a resposta não carrega.
        self.assertNotIn("expected", raw)
        self.assertNotIn("difference", raw)
