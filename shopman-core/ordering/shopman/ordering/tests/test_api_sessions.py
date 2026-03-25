from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from shopman.ordering import registry
from shopman.ordering.contrib.stock.resolvers import StockIssueResolver
from shopman.ordering.models import Channel, Directive, IdempotencyKey, Session


class SessionApiTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user("testuser", password="testpass")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        registry.clear()

    def tearDown(self) -> None:
        registry.clear()
        super().tearDown()

    def _mk_channel(
        self,
        *,
        ref: str = "pos",
        pricing_policy: str = "internal",
        edit_policy: str = "open",
        config: dict | None = None,
    ) -> Channel:
        return Channel.objects.create(
            ref=ref,
            name=ref.upper(),
            pricing_policy=pricing_policy,
            edit_policy=edit_policy,
            config=config or {},
            is_active=True,
        )

    def test_create_session_basic(self) -> None:
        self._mk_channel(ref="pos")
        resp = self.client.post("/api/sessions", {"channel_ref": "pos"}, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["channel_ref"], "pos")
        self.assertEqual(resp.data["state"], "open")
        self.assertTrue(resp.data["session_key"])

    def test_create_session_get_or_open_by_owner(self) -> None:
        self._mk_channel(ref="pos")
        payload = {"channel_ref": "pos", "handle_type": "mesa", "handle_ref": "T12"}

        r1 = self.client.post("/api/sessions", payload, format="json")
        self.assertEqual(r1.status_code, 201, r1.data)

        r2 = self.client.post("/api/sessions", payload, format="json")
        self.assertEqual(r2.status_code, 200, r2.data)
        self.assertEqual(r2.data["id"], r1.data["id"])

    def test_retrieve_requires_channel_ref_if_ambiguous(self) -> None:
        c1 = self._mk_channel(ref="pos")
        c2 = self._mk_channel(ref="shop")

        Session.objects.create(
            session_key="SESS-AMBIG",
            channel=c1,
            state="open",
            pricing_policy=c1.pricing_policy,
            edit_policy=c1.edit_policy,
            rev=0,
            items=[],
            data={"checks": {}, "issues": []},
        )
        Session.objects.create(
            session_key="SESS-AMBIG",
            channel=c2,
            state="open",
            pricing_policy=c2.pricing_policy,
            edit_policy=c2.edit_policy,
            rev=0,
            items=[],
            data={"checks": {}, "issues": []},
        )

        r = self.client.get("/api/sessions/SESS-AMBIG")
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn("channel_ref", r.data)

        r2 = self.client.get("/api/sessions/SESS-AMBIG?channel_ref=pos")
        self.assertEqual(r2.status_code, 200, r2.data)
        self.assertEqual(r2.data["channel_ref"], "pos")

    def test_modify_increments_rev_clears_checks_issues_and_enqueues_directive(self) -> None:
        # Register a mock stock check so ModifyService finds it via registry
        class _MockStockCheck:
            code = "stock"
            topic = "stock.hold"
            def validate(self, *, channel, session, ctx):
                pass
        registry.register_check(_MockStockCheck())

        self._mk_channel(
            ref="pos",
            config={
                "rules": {"checks": ["stock"]},
            },
        )
        s = self.client.post("/api/sessions", {"channel_ref": "pos"}, format="json").data

        payload = {"channel_ref": "pos", "ops": [{"op": "add_line", "sku": "LATTE", "qty": 2}]}
        r = self.client.post(f"/api/sessions/{s['session_key']}/modify", payload, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["rev"], 1)
        self.assertEqual(r.data["data"]["checks"], {})
        self.assertEqual(r.data["data"]["issues"], [])

        d = Directive.objects.filter(topic="stock.hold").order_by("-id").first()
        self.assertIsNotNone(d)
        self.assertEqual(d.payload["session_key"], s["session_key"])
        self.assertEqual(d.payload["channel_ref"], "pos")
        self.assertEqual(d.payload["rev"], 1)
        self.assertIn("items", d.payload)

    def test_modify_locked_session_rejected(self) -> None:
        self._mk_channel(ref="pos", edit_policy="locked")
        s = self.client.post("/api/sessions", {"channel_ref": "pos"}, format="json").data
        r = self.client.post(
            f"/api/sessions/{s['session_key']}/modify",
            {"channel_ref": "pos", "ops": [{"op": "add_line", "sku": "LATTE", "qty": 1}]},
            format="json",
        )
        self.assertEqual(r.status_code, 400, r.data)
        self.assertEqual(r.data["code"], "locked")

    def test_modify_validates_qty_positive(self) -> None:
        self._mk_channel(ref="pos")
        s = self.client.post("/api/sessions", {"channel_ref": "pos"}, format="json").data

        r = self.client.post(
            f"/api/sessions/{s['session_key']}/modify",
            {"channel_ref": "pos", "ops": [{"op": "add_line", "sku": "LATTE", "qty": 0}]},
            format="json",
        )
        self.assertEqual(r.status_code, 400, r.data)
        self.assertEqual(r.data["code"], "invalid_qty")

    def test_modify_external_pricing_requires_unit_price_q(self) -> None:
        self._mk_channel(ref="ifood", pricing_policy="external")
        s = self.client.post("/api/sessions", {"channel_ref": "ifood"}, format="json").data

        r = self.client.post(
            f"/api/sessions/{s['session_key']}/modify",
            {"channel_ref": "ifood", "ops": [{"op": "add_line", "sku": "LATTE", "qty": 1}]},
            format="json",
        )
        self.assertEqual(r.status_code, 400, r.data)
        self.assertEqual(r.data["code"], "missing_unit_price_q")

    def test_commit_requires_fresh_required_checks(self) -> None:
        c = self._mk_channel(ref="pos", config={"required_checks_on_commit": ["stock"]})
        sess = Session.objects.create(
            session_key="SESS-C1",
            channel=c,
            state="open",
            pricing_policy=c.pricing_policy,
            edit_policy=c.edit_policy,
            rev=0,
            items=[{"line_id": "L-1", "sku": "LATTE", "qty": 1, "unit_price_q": 1000, "meta": {}}],
            data={"checks": {}, "issues": []},
        )

        r1 = self.client.post(f"/api/sessions/{sess.session_key}/commit", {"channel_ref": "pos"}, format="json")
        self.assertEqual(r1.status_code, 400, r1.data)
        self.assertEqual(r1.data["code"], "missing_check")

        # stale check
        sess.data["checks"]["stock"] = {"rev": -1}
        sess.save(update_fields=["data"])
        r2 = self.client.post(f"/api/sessions/{sess.session_key}/commit", {"channel_ref": "pos"}, format="json")
        self.assertEqual(r2.status_code, 400, r2.data)
        self.assertEqual(r2.data["code"], "stale_check")

    def test_commit_blocks_on_blocking_issues(self) -> None:
        c = self._mk_channel(ref="pos")
        sess = Session.objects.create(
            session_key="SESS-C2",
            channel=c,
            state="open",
            pricing_policy=c.pricing_policy,
            edit_policy=c.edit_policy,
            rev=0,
            items=[{"line_id": "L-1", "sku": "LATTE", "qty": 1, "unit_price_q": 1000, "meta": {}}],
            data={
                "checks": {},
                "issues": [
                    {
                        "id": "ISS-1",
                        "source": "stock",
                        "code": "stock.insufficient",
                        "blocking": True,
                        "message": "Sem estoque",
                        "context": {},
                    }
                ],
            },
        )

        r = self.client.post(f"/api/sessions/{sess.session_key}/commit", {"channel_ref": "pos"}, format="json")
        self.assertEqual(r.status_code, 400, r.data)
        self.assertEqual(r.data["code"], "blocking_issues")

    def test_commit_is_idempotent(self) -> None:
        c = self._mk_channel(ref="pos")
        sess = Session.objects.create(
            session_key="SESS-IDEM",
            channel=c,
            state="open",
            pricing_policy=c.pricing_policy,
            edit_policy=c.edit_policy,
            rev=0,
            items=[{"line_id": "L-1", "sku": "LATTE", "qty": 1, "unit_price_q": 1000, "meta": {}}],
            data={"checks": {}, "issues": []},
        )

        idem = "IDEM-TEST-1"
        r1 = self.client.post(
            f"/api/sessions/{sess.session_key}/commit",
            {"channel_ref": "pos", "idempotency_key": idem},
            format="json",
        )
        self.assertEqual(r1.status_code, 201, r1.data)
        self.assertEqual(r1.data["status"], "committed")

        # Repetição com mesma chave
        r2 = self.client.post(
            f"/api/sessions/{sess.session_key}/commit",
            {"channel_ref": "pos", "idempotency_key": idem},
            format="json",
        )
        # Replay idempotente: retorna o mesmo corpo (e, por consequência, o mesmo status HTTP).
        self.assertEqual(r2.status_code, 201, r2.data)
        self.assertEqual(r2.data["status"], "committed")
        self.assertEqual(r2.data["order_ref"], r1.data["order_ref"])

        # Confirma que guardou o response no idem
        self.assertTrue(IdempotencyKey.objects.filter(scope="commit:pos", key=idem).exists())

    def test_resolve_delegates_by_source_and_applies_ops(self) -> None:
        c = self._mk_channel(ref="pos")
        sess = Session.objects.create(
            session_key="SESS-R1",
            channel=c,
            state="open",
            pricing_policy=c.pricing_policy,
            edit_policy=c.edit_policy,
            rev=0,
            items=[{"line_id": "L-1", "sku": "LATTE", "qty": 3, "unit_price_q": 1000, "meta": {}}],
            data={"checks": {}, "issues": []},
        )

        # Registra resolver (v0.5.8)
        registry.register_issue_resolver(StockIssueResolver())

        # Injeta issue no formato v0.5.8 (actions em context)
        issue_id = "ISS-R1"
        action_id = "ACT-R1"
        sess.data["issues"] = [
            {
                "id": issue_id,
                "source": "stock",
                "code": "stock.insufficient",
                "blocking": True,
                "message": "Só temos 1",
                "context": {
                    "actions": [
                        {
                            "id": action_id,
                            "label": "Ajustar para 1",
                            "rev": sess.rev,
                            "ops": [{"op": "set_qty", "line_id": "L-1", "qty": 1}],
                        }
                    ]
                },
            }
        ]
        sess.save(update_fields=["data"])

        r = self.client.post(
            f"/api/sessions/{sess.session_key}/resolve",
            {"channel_ref": "pos", "issue_id": issue_id, "action_id": action_id},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["rev"], 1)
        self.assertEqual(Decimal(str(r.data["items"][0]["qty"])), Decimal("1"))
        # ModifyService limpa issues/checks após aplicar ops
        self.assertEqual(r.data["data"]["issues"], [])
        self.assertEqual(r.data["data"]["checks"], {})
