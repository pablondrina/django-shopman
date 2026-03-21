"""
Testes do webhook EFI PIX.

Cobre:
- Validação de autenticação (token)
- Processamento de pagamento PIX (happy path)
- Idempotência (não processa duplicatas)
- Order não encontrada
- Payload inválido (sem pix, sem txid)
- GET health check
- E2E: webhook → on_payment_confirmed → auto-transition + stock.commit + notification
"""

from __future__ import annotations

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from shopman.ordering.models import Channel, Directive, Order


def _make_whatsapp_channel(**overrides) -> Channel:
    """Cria canal WhatsApp com config completa para testes."""
    config = {
        "order_flow": {
            "initial_status": "new",
            "transitions": {
                "new": ["confirmed", "cancelled"],
                "confirmed": ["processing", "cancelled"],
                "processing": ["ready", "cancelled"],
                "ready": ["dispatched", "completed"],
                "dispatched": ["delivered"],
                "delivered": ["completed"],
                "completed": [],
                "cancelled": [],
            },
            "terminal_statuses": ["completed", "cancelled"],
            "auto_transitions": {
                "on_payment_confirm": "confirmed",
            },
        },
        "confirmation_flow": {
            "confirmation_timeout_minutes": 5,
            "pix_payment_timeout_minutes": 10,
            "require_manual_confirmation": True,
        },
        "stock": {
            "checkout_hold_expiration_minutes": 20,
            "safety_margin_default": 2,
        },
        "payment": {
            "backend": "efi",
            "method": "pix",
            "require_prepayment": True,
        },
    }
    config.update(overrides.pop("config", {}))
    defaults = dict(ref="whatsapp", name="WhatsApp (Nice)", config=config)
    defaults.update(overrides)
    return Channel.objects.create(**defaults)


def _make_order(channel: Channel, ref: str = "ORD-WH-001", total_q: int = 1850, **kwargs) -> Order:
    """Cria order de teste."""
    return Order.objects.create(
        ref=ref,
        channel=channel,
        total_q=total_q,
        status=kwargs.pop("status", Order.Status.CONFIRMED),
        data=kwargs.pop("data", {}),
        **kwargs,
    )


WEBHOOK_URL = "/api/webhooks/efi/pix/"


class EfiPixWebhookAuthTests(TestCase):
    """Testes de autenticação do webhook."""

    def setUp(self) -> None:
        self.client = APIClient()

    @override_settings(SHOPMAN_EFI_WEBHOOK={"WEBHOOK_TOKEN": "secret-token-123"})
    def test_rejects_missing_token(self):
        """Sem token → 401."""
        response = self.client.post(
            WEBHOOK_URL,
            data={"pix": [{"txid": "abc123", "endToEndId": "E123", "valor": "10.00"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    @override_settings(SHOPMAN_EFI_WEBHOOK={"WEBHOOK_TOKEN": "secret-token-123"})
    def test_rejects_wrong_token(self):
        """Token errado → 401."""
        response = self.client.post(
            WEBHOOK_URL,
            data={"pix": [{"txid": "abc123", "endToEndId": "E123", "valor": "10.00"}]},
            format="json",
            HTTP_X_EFI_WEBHOOK_TOKEN="wrong-token",
        )
        self.assertEqual(response.status_code, 401)

    @override_settings(SHOPMAN_EFI_WEBHOOK={"WEBHOOK_TOKEN": "secret-token-123"})
    def test_accepts_correct_token_header(self):
        """Token correto no header → aceita (mesmo sem order)."""
        response = self.client.post(
            WEBHOOK_URL,
            data={"pix": [{"txid": "nonexistent", "endToEndId": "E123", "valor": "10.00"}]},
            format="json",
            HTTP_X_EFI_WEBHOOK_TOKEN="secret-token-123",
        )
        self.assertEqual(response.status_code, 200)

    @override_settings(SHOPMAN_EFI_WEBHOOK={"WEBHOOK_TOKEN": "secret-token-123"})
    def test_accepts_correct_token_query_param(self):
        """Token correto via query param → aceita."""
        response = self.client.post(
            f"{WEBHOOK_URL}?token=secret-token-123",
            data={"pix": [{"txid": "nonexistent", "endToEndId": "E123", "valor": "10.00"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

    def test_no_token_configured_allows_all(self):
        """Sem SHOPMAN_EFI_WEBHOOK configurado → auth desabilitada (dev mode)."""
        response = self.client.post(
            WEBHOOK_URL,
            data={"pix": [{"txid": "nonexistent", "endToEndId": "E123", "valor": "10.00"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

    @override_settings(SHOPMAN_EFI_WEBHOOK={"SKIP_SIGNATURE": True, "WEBHOOK_TOKEN": "secret"})
    def test_skip_signature_bypasses_auth(self):
        """SKIP_SIGNATURE=True → aceita sem token."""
        response = self.client.post(
            WEBHOOK_URL,
            data={"pix": [{"txid": "nonexistent", "endToEndId": "E123", "valor": "10.00"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)


class EfiPixWebhookHealthCheckTests(TestCase):
    """Testes do GET health check."""

    def setUp(self) -> None:
        self.client = APIClient()

    def test_get_returns_200(self):
        """GET → 200 (EFI usa para validar endpoint ao registrar webhook)."""
        response = self.client.get(WEBHOOK_URL)
        self.assertEqual(response.status_code, 200)


class EfiPixWebhookPayloadTests(TestCase):
    """Testes de validação de payload."""

    def setUp(self) -> None:
        self.client = APIClient()

    def test_empty_pix_list_returns_400(self):
        """Payload sem pix → 400."""
        response = self.client.post(
            WEBHOOK_URL,
            data={"pix": []},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_pix_key_returns_400(self):
        """Payload sem chave pix → 400."""
        response = self.client.post(
            WEBHOOK_URL,
            data={"other": "data"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_pix_item_without_txid_is_skipped(self):
        """Item sem txid → skipped, mas responde 200."""
        response = self.client.post(
            WEBHOOK_URL,
            data={"pix": [{"endToEndId": "E123", "valor": "10.00"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)


class EfiPixWebhookProcessingTests(TestCase):
    """Testes de processamento de pagamento."""

    def setUp(self) -> None:
        self.client = APIClient()
        self.channel = _make_whatsapp_channel()

    def test_happy_path_confirms_payment(self):
        """Webhook com txid válido → order.data.payment.status = captured."""
        order = _make_order(self.channel, data={
            "payment": {"intent_id": "txid_abc123", "status": "pending", "amount_q": 1850},
        })

        response = self.client.post(
            WEBHOOK_URL,
            data={
                "pix": [{
                    "txid": "txid_abc123",
                    "endToEndId": "E12345678202603201000",
                    "valor": "18.50",
                    "horario": "2026-03-20T10:00:00.000Z",
                }],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        order.refresh_from_db()
        self.assertEqual(order.data["payment"]["status"], "captured")
        self.assertEqual(order.data["payment"]["e2e_id"], "E12345678202603201000")
        self.assertEqual(order.data["payment"]["paid_amount_q"], 1850)

    def test_happy_path_triggers_auto_transition(self):
        """Webhook → on_payment_confirmed → auto-transition confirmed (já é confirmed)."""
        order = _make_order(self.channel, data={
            "payment": {"intent_id": "txid_transition", "status": "pending", "amount_q": 3300},
        })

        self.client.post(
            WEBHOOK_URL,
            data={"pix": [{"txid": "txid_transition", "endToEndId": "E999", "valor": "33.00"}]},
            format="json",
        )

        order.refresh_from_db()
        # Order was already CONFIRMED, so auto_transition to "confirmed" is a no-op
        # but payment should be captured
        self.assertEqual(order.data["payment"]["status"], "captured")

    def test_happy_path_creates_notification_directive(self):
        """Webhook → notification.send com template payment_confirmed."""
        order = _make_order(self.channel, data={
            "payment": {"intent_id": "txid_notif", "status": "pending"},
        })

        self.client.post(
            WEBHOOK_URL,
            data={"pix": [{"txid": "txid_notif", "endToEndId": "E888", "valor": "10.00"}]},
            format="json",
        )

        notif = Directive.objects.filter(
            topic="notification.send",
            payload__template="payment_confirmed",
        ).first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.payload["order_ref"], order.ref)

    def test_happy_path_creates_stock_commit_when_holds_exist(self):
        """Webhook com holds → stock.commit directive criada."""
        order = _make_order(self.channel, data={
            "payment": {"intent_id": "txid_holds", "status": "pending"},
            "holds": [
                {"hold_id": "h1", "sku": "CROISSANT", "qty": 3.0},
                {"hold_id": "h2", "sku": "BAGUETE", "qty": 1.0},
            ],
        })

        self.client.post(
            WEBHOOK_URL,
            data={"pix": [{"txid": "txid_holds", "endToEndId": "E777", "valor": "50.00"}]},
            format="json",
        )

        commit = Directive.objects.filter(topic="stock.commit").first()
        self.assertIsNotNone(commit)
        self.assertEqual(commit.payload["order_ref"], order.ref)
        self.assertEqual(len(commit.payload["holds"]), 2)

    def test_idempotent_does_not_reprocess(self):
        """Segundo webhook para mesma order → skip (já captured)."""
        order = _make_order(self.channel, data={
            "payment": {"intent_id": "txid_idem", "status": "captured", "e2e_id": "E111"},
        })

        self.client.post(
            WEBHOOK_URL,
            data={"pix": [{"txid": "txid_idem", "endToEndId": "E111", "valor": "10.00"}]},
            format="json",
        )

        # Não deve criar directives duplicadas
        self.assertEqual(Directive.objects.filter(topic="notification.send").count(), 0)
        self.assertEqual(Directive.objects.filter(topic="stock.commit").count(), 0)

    def test_order_not_found_returns_200(self):
        """txid sem order correspondente → 200 (log warning, não falha)."""
        response = self.client.post(
            WEBHOOK_URL,
            data={"pix": [{"txid": "txid_orphan", "endToEndId": "E000", "valor": "5.00"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

    def test_multiple_pix_in_single_payload(self):
        """Payload com múltiplos pix items → processa todos."""
        order1 = _make_order(self.channel, ref="ORD-MULTI-1", data={
            "payment": {"intent_id": "txid_multi_1", "status": "pending"},
        })
        order2 = _make_order(self.channel, ref="ORD-MULTI-2", data={
            "payment": {"intent_id": "txid_multi_2", "status": "pending"},
        })

        response = self.client.post(
            WEBHOOK_URL,
            data={
                "pix": [
                    {"txid": "txid_multi_1", "endToEndId": "E001", "valor": "10.00"},
                    {"txid": "txid_multi_2", "endToEndId": "E002", "valor": "20.00"},
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        order1.refresh_from_db()
        order2.refresh_from_db()
        self.assertEqual(order1.data["payment"]["status"], "captured")
        self.assertEqual(order2.data["payment"]["status"], "captured")


class EfiPixWebhookE2ETests(TestCase):
    """
    Testes E2E: simula fluxo completo webhook EFI → transição + directives.

    Cenário: Order NEW → CONFIRMED (operador) → PIX gerado → webhook EFI →
             payment captured → stock.commit + notification
    """

    def setUp(self) -> None:
        self.client = APIClient()
        self.channel = _make_whatsapp_channel()

    def test_e2e_new_order_to_payment_confirmed(self):
        """
        Fluxo completo:
        1. Order criada (NEW)
        2. Operador confirma → CONFIRMED
        3. PIX gerado (simulado via data)
        4. Webhook EFI recebido → payment captured
        5. Directives criadas: stock.commit + notification
        """
        # 1. Order criada
        order = _make_order(
            self.channel,
            ref="ORD-E2E-001",
            status=Order.Status.NEW,
            total_q=3300,
            data={
                "holds": [{"hold_id": "h1", "sku": "BRIOCHE", "qty": 2.0}],
            },
        )

        # 2. Operador confirma
        order.transition_status(Order.Status.CONFIRMED, actor="operator")
        self.assertEqual(order.status, Order.Status.CONFIRMED)

        # 3. PIX gerado (simula PixGenerateHandler preenchendo payment data)
        order.data["payment"] = {
            "intent_id": "txid_e2e_001",
            "status": "pending",
            "amount_q": 3300,
            "method": "pix",
            "qr_code": "data:image/svg+xml;base64,mock",
            "copy_paste": "00020126580014br.gov.bcb.pix...",
        }
        order.save(update_fields=["data", "updated_at"])

        # 4. Webhook EFI recebido
        response = self.client.post(
            WEBHOOK_URL,
            data={
                "pix": [{
                    "txid": "txid_e2e_001",
                    "endToEndId": "E12345678202603201000abc",
                    "valor": "33.00",
                    "horario": "2026-03-20T14:30:00.000Z",
                    "chave": "12345678000199",
                }],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        # 5. Verificações
        order.refresh_from_db()

        # Payment captured
        self.assertEqual(order.data["payment"]["status"], "captured")
        self.assertEqual(order.data["payment"]["e2e_id"], "E12345678202603201000abc")
        self.assertEqual(order.data["payment"]["paid_amount_q"], 3300)

        # Stock commit criado
        stock_commit = Directive.objects.filter(topic="stock.commit").first()
        self.assertIsNotNone(stock_commit, "Expected stock.commit directive")
        self.assertEqual(stock_commit.payload["order_ref"], "ORD-E2E-001")
        self.assertEqual(len(stock_commit.payload["holds"]), 1)

        # Notification criada
        notif = Directive.objects.filter(
            topic="notification.send",
            payload__template="payment_confirmed",
        ).first()
        self.assertIsNotNone(notif, "Expected payment_confirmed notification")
        self.assertEqual(notif.payload["order_ref"], "ORD-E2E-001")

    def test_e2e_duplicate_webhook_is_safe(self):
        """Dois webhooks com mesmo txid → segundo é no-op."""
        order = _make_order(
            self.channel,
            ref="ORD-E2E-DUP",
            data={
                "payment": {"intent_id": "txid_dup", "status": "pending"},
                "holds": [{"hold_id": "h1", "sku": "PAIN", "qty": 1.0}],
            },
        )

        payload = {
            "pix": [{"txid": "txid_dup", "endToEndId": "E999", "valor": "10.00"}],
        }

        # Primeiro webhook
        self.client.post(WEBHOOK_URL, data=payload, format="json")

        # Verifica directives criadas
        notif_count = Directive.objects.filter(topic="notification.send").count()
        commit_count = Directive.objects.filter(topic="stock.commit").count()

        # Segundo webhook (duplicata)
        self.client.post(WEBHOOK_URL, data=payload, format="json")

        # Mesma contagem (não duplicou)
        self.assertEqual(Directive.objects.filter(topic="notification.send").count(), notif_count)
        self.assertEqual(Directive.objects.filter(topic="stock.commit").count(), commit_count)

    def test_e2e_auto_transition_from_new(self):
        """
        Order em NEW com auto_transition on_payment_confirm=confirmed.
        Webhook → auto-transition NEW → CONFIRMED.
        """
        order = _make_order(
            self.channel,
            ref="ORD-E2E-AUTO",
            status=Order.Status.NEW,
            data={
                "payment": {"intent_id": "txid_auto", "status": "pending"},
            },
        )

        self.client.post(
            WEBHOOK_URL,
            data={"pix": [{"txid": "txid_auto", "endToEndId": "E555", "valor": "15.00"}]},
            format="json",
        )

        order.refresh_from_db()
        self.assertEqual(order.data["payment"]["status"], "captured")
        self.assertEqual(order.status, Order.Status.CONFIRMED)
