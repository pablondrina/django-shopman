"""Storefront order tracking page rendering guardrails."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import Client
from django.utils import timezone

pytestmark = pytest.mark.django_db


class TestOrderTrackingPage:
    def test_payment_pending_countdown_uses_server_time_anchor(
        self,
        client: Client,
        order_with_payment,
        channel,
    ) -> None:
        channel.config = {"confirmation": {"mode": "auto_confirm", "timeout_minutes": 5}}
        channel.save(update_fields=["config"])
        order_with_payment.data["payment"]["expires_at"] = (
            timezone.now() + timezone.timedelta(minutes=15)
        ).isoformat()
        order_with_payment.save(update_fields=["data", "updated_at"])

        response = client.get(f"/pedido/{order_with_payment.ref}/")

        assert response.status_code == 200
        body = response.content.decode()
        assert "Recebemos seu pedido." in body
        assert "Aguardamos a confirmação do pagamento." in body
        assert "Pagar agora" in body
        assert f"/pedido/{order_with_payment.ref}/pagamento/" in body
        assert "Pagamento confirmado." not in body
        assert "O estabelecimento tem" not in body
        assert "order-live-area" in body
        assert "serverNow" in body
        assert "Atualizado agora" in body
        assert "Estamos conferindo uma atualização." in body

    def test_active_tracking_hides_terminal_reorder_ctas(
        self,
        client: Client,
        order,
    ) -> None:
        response = client.get(f"/pedido/{order.ref}/")

        assert response.status_code == 200
        body = response.content.decode()
        assert "Pedir novamente" not in body
        assert "Ver cardápio" not in body
        assert "Recebemos seu pedido." in body

    def test_terminal_tracking_shows_reorder_ctas(
        self,
        client: Client,
        order,
    ) -> None:
        from shopman.orderman.models import Order

        Order.objects.filter(pk=order.pk).update(status="completed", updated_at=timezone.now())
        order.refresh_from_db()

        response = client.get(f"/pedido/{order.ref}/")

        assert response.status_code == 200
        body = response.content.decode()
        assert "Pedir novamente" in body
        assert "Ver cardápio" in body

    def test_confirmed_unpaid_pix_tracking_redirects_to_payment_gate(
        self,
        client: Client,
        order_with_payment,
    ) -> None:
        from shopman.orderman.models import Order

        order_with_payment.data["payment"]["expires_at"] = (
            timezone.now() + timezone.timedelta(minutes=10)
        ).isoformat()
        order_with_payment.save(update_fields=["data", "updated_at"])
        Order.objects.filter(pk=order_with_payment.pk).update(
            status="confirmed",
            updated_at=timezone.now(),
        )
        order_with_payment.refresh_from_db()

        response = client.get(f"/pedido/{order_with_payment.ref}/")

        assert response.status_code == 302
        assert response["Location"] == f"/pedido/{order_with_payment.ref}/pagamento/"

    def test_confirmed_pix_with_payment_error_still_redirects_to_payment_gate(
        self,
        client: Client,
        order_with_payment,
    ) -> None:
        from shopman.orderman.models import Order

        order_with_payment.data["payment"]["error"] = "No module named 'qrcode'"
        order_with_payment.save(update_fields=["data", "updated_at"])
        Order.objects.filter(pk=order_with_payment.pk).update(
            status="confirmed",
            updated_at=timezone.now(),
        )
        order_with_payment.refresh_from_db()

        response = client.get(f"/pedido/{order_with_payment.ref}/")

        assert response.status_code == 302
        assert response["Location"] == f"/pedido/{order_with_payment.ref}/pagamento/"

    def test_confirmed_unpaid_pix_status_partial_redirects_to_payment_gate(
        self,
        client: Client,
        order_with_payment,
    ) -> None:
        from shopman.orderman.models import Order

        order_with_payment.data["payment"]["expires_at"] = (
            timezone.now() + timezone.timedelta(minutes=10)
        ).isoformat()
        order_with_payment.save(update_fields=["data", "updated_at"])
        Order.objects.filter(pk=order_with_payment.pk).update(
            status="confirmed",
            updated_at=timezone.now(),
        )
        order_with_payment.refresh_from_db()

        response = client.get(
            f"/pedido/{order_with_payment.ref}/status/",
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        assert response["HX-Redirect"] == f"/pedido/{order_with_payment.ref}/pagamento/"

    def test_confirmed_pix_with_payment_error_status_partial_redirects_to_gate(
        self,
        client: Client,
        order_with_payment,
    ) -> None:
        from shopman.orderman.models import Order

        order_with_payment.data["payment"]["error"] = "No module named 'qrcode'"
        order_with_payment.save(update_fields=["data", "updated_at"])
        Order.objects.filter(pk=order_with_payment.pk).update(
            status="confirmed",
            updated_at=timezone.now(),
        )
        order_with_payment.refresh_from_db()

        response = client.get(
            f"/pedido/{order_with_payment.ref}/status/",
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        assert response["HX-Redirect"] == f"/pedido/{order_with_payment.ref}/pagamento/"

    def test_confirmed_unpaid_pix_live_partial_has_payment_action_when_rendered_directly(
        self,
        order_with_payment,
    ) -> None:
        from django.template.loader import render_to_string
        from shopman.orderman.models import Order

        from shopman.storefront.projections import build_order_tracking

        order_with_payment.data["payment"]["expires_at"] = (
            timezone.now() + timezone.timedelta(minutes=10)
        ).isoformat()
        order_with_payment.save(update_fields=["data", "updated_at"])
        Order.objects.filter(pk=order_with_payment.pk).update(
            status="confirmed",
            updated_at=timezone.now(),
        )
        order_with_payment.refresh_from_db()

        body = render_to_string(
            "storefront/partials/order_live.html",
            {"tracking": build_order_tracking(order_with_payment)},
        )

        assert "Disponibilidade confirmada." in body
        assert "Para continuar, conclua o pagamento." in body
        assert "Tempo para pagamento:" in body
        assert "Pagar agora" in body
        assert f"/pedido/{order_with_payment.ref}/pagamento/" in body
        assert "Agora falta o pagamento" not in body

    def test_status_poll_returns_live_area_with_eta_copy(
        self,
        client: Client,
        order,
    ) -> None:
        order.transition_status("confirmed", actor="test")
        order.transition_status("preparing", actor="test")
        order.refresh_from_db()

        response = client.get(f"/pedido/{order.ref}/status/")

        assert response.status_code == 200
        body = response.content.decode()
        assert "Estamos preparando seu pedido." in body
        assert "Previsão para ficar pronto às" in body
        assert "Previsão:" not in body

    def test_ready_delivery_live_area_explains_waiting_courier(self, order) -> None:
        from django.template.loader import render_to_string

        from shopman.storefront.projections import build_order_tracking

        order.data = {"fulfillment_type": "delivery"}
        order.save(update_fields=["data"])
        for status in ("confirmed", "preparing", "ready"):
            order.transition_status(status, actor="test")
        order.refresh_from_db()

        body = render_to_string(
            "storefront/partials/order_live.html",
            {"tracking": build_order_tracking(order)},
        )

        assert "Seu pedido está pronto e aguardando entregador." in body
        assert "Aguardando entregador." in body
        assert "Já solicitamos a coleta do seu pedido. Assim que sair para entrega avisamos." in body
        assert "Seu pedido saiu para entrega." not in body

    def test_delivery_tracking_does_not_show_pickup_directions_without_tracking(
        self,
        client: Client,
        order,
    ) -> None:
        from shopman.orderman.models import Fulfillment

        order.data = {"fulfillment_type": "delivery"}
        order.save(update_fields=["data", "updated_at"])
        Fulfillment.objects.create(order=order)

        response = client.get(f"/pedido/{order.ref}/")

        assert response.status_code == 200
        body = response.content.decode()
        assert "Como chegar" not in body
        assert "Pronto para retirada" not in body

    def test_auto_confirm_countdown_can_refresh_live_area_without_blank_copy(
        self,
        client: Client,
        order,
        channel,
    ) -> None:
        from shopman.orderman.models import Directive

        channel.config = {"confirmation": {"mode": "auto_confirm", "timeout_minutes": 5}}
        channel.save(update_fields=["config"])
        expires_at = timezone.now() + timezone.timedelta(minutes=5)
        Directive.objects.create(
            topic="confirmation.timeout",
            payload={
                "order_ref": order.ref,
                "action": "confirm",
                "expires_at": expires_at.isoformat(),
            },
            available_at=expires_at,
        )

        response = client.get(f"/pedido/{order.ref}/")

        assert response.status_code == 200
        body = response.content.decode()
        assert "Recebemos seu pedido." in body
        assert "O estabelecimento está conferindo a disponibilidade." not in body
        assert "O estabelecimento tem" in body
        assert "para conferir a disponibilidade." in body
        assert "countdown-expired" in body
        assert "!expired && timeLeft" in body

    def test_closed_store_tracking_does_not_render_availability_countdown(
        self,
        client: Client,
        order,
        channel,
        shop_instance,
    ) -> None:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from shopman.orderman.models import Directive

        tz = ZoneInfo("America/Sao_Paulo")
        shop_instance.timezone = "America/Sao_Paulo"
        shop_instance.opening_hours = {
            "monday": {"open": "09:00", "close": "18:00"},
            "tuesday": {"open": "09:00", "close": "18:00"},
            "wednesday": {"open": "09:00", "close": "18:00"},
            "thursday": {"open": "09:00", "close": "18:00"},
            "friday": {"open": "09:00", "close": "18:00"},
            "saturday": {"open": "09:00", "close": "18:00"},
        }
        shop_instance.save(update_fields=["timezone", "opening_hours"])
        channel.config = {"confirmation": {"mode": "auto_confirm", "timeout_minutes": 5}}
        channel.save(update_fields=["config"])
        Directive.objects.create(
            topic="confirmation.timeout",
            payload={
                "order_ref": order.ref,
                "action": "confirm",
                "expires_at": datetime(2026, 5, 4, 9, 5, tzinfo=tz).isoformat(),
            },
            available_at=datetime(2026, 5, 4, 9, 5, tzinfo=tz),
        )

        with patch(
            "shopman.shop.services.business_calendar.timezone.now",
            return_value=datetime(2026, 5, 3, 12, 0, tzinfo=tz),
        ):
            response = client.get(f"/pedido/{order.ref}/")

        assert response.status_code == 200
        body = response.content.decode()
        assert "Recebemos seu pedido." in body
        assert "Estamos fechados agora. Vamos conferir a disponibilidade quando abrirmos." in body
        assert "Próxima abertura:" in body
        assert "amanhã às 9h" in body
        assert "O estabelecimento tem" not in body
        assert "para conferir a disponibilidade." not in body

    def test_payment_timeout_tracking_shows_expired_copy(
        self,
        client: Client,
        order_with_payment,
    ) -> None:
        from shopman.orderman.models import Order

        Order.objects.filter(pk=order_with_payment.pk).update(
            status="cancelled",
            data={
                **order_with_payment.data,
                "cancellation_reason": "payment_timeout",
                "payment_timeout_at": timezone.now().isoformat(),
            },
            updated_at=timezone.now(),
        )
        order_with_payment.refresh_from_db()

        response = client.get(f"/pedido/{order_with_payment.ref}/")

        assert response.status_code == 200
        body = response.content.decode()
        assert "O prazo para pagamento expirou." in body
        assert "O pedido foi automaticamente cancelado." in body
        assert body.count("Pagamento expirado") == 1
        assert "Aguardamos a confirmação do pagamento." not in body
        assert "O estabelecimento tem" not in body

    def test_status_partial_updates_header_badge_out_of_band(self, client: Client, order_with_payment) -> None:
        from shopman.orderman.models import Order

        Order.objects.filter(pk=order_with_payment.pk).update(
            status="cancelled",
            data={
                **order_with_payment.data,
                "cancellation_reason": "payment_timeout",
                "payment_timeout_at": timezone.now().isoformat(),
            },
            updated_at=timezone.now(),
        )
        order_with_payment.refresh_from_db()

        response = client.get(f"/pedido/{order_with_payment.ref}/status/")

        assert response.status_code == 200
        body = response.content.decode()
        assert 'id="order-status-badge"' in body
        assert 'hx-swap-oob="outerHTML"' in body
        assert body.count("Pagamento expirado") == 1

    def test_expired_confirmed_pix_tracking_reconciles_to_cancelled(
        self,
        client: Client,
        order_with_payment,
    ) -> None:
        from shopman.orderman.models import Order

        order_with_payment.data["payment"]["expires_at"] = (
            timezone.now().replace(microsecond=0) - timezone.timedelta(minutes=1)
        ).isoformat()
        order_with_payment.save(update_fields=["data", "updated_at"])
        Order.objects.filter(pk=order_with_payment.pk).update(
            status="confirmed",
            updated_at=timezone.now(),
        )
        order_with_payment.refresh_from_db()

        response = client.get(f"/pedido/{order_with_payment.ref}/")

        assert response.status_code == 200
        order_with_payment.refresh_from_db()
        assert order_with_payment.status == "cancelled"
        body = response.content.decode()
        assert "O prazo para pagamento expirou." in body
        assert "O pedido foi automaticamente cancelado." in body
        assert "Pagar agora" not in body
        assert "Aguardando pagamento" not in body

    def test_confirmed_paid_tracking_keeps_payment_confirmation_visible(
        self,
        client: Client,
        order_with_payment,
    ) -> None:
        from shopman.orderman.models import Order
        from shopman.payman import PaymentService

        intent = PaymentService.create_intent(
            order_ref=order_with_payment.ref,
            amount_q=order_with_payment.total_q,
            method="pix",
        )
        order_with_payment.data["payment"]["intent_ref"] = intent.ref
        order_with_payment.save(update_fields=["data", "updated_at"])
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)
        Order.objects.filter(pk=order_with_payment.pk).update(
            status="confirmed",
            updated_at=timezone.now(),
        )
        order_with_payment.refresh_from_db()

        response = client.get(f"/pedido/{order_with_payment.ref}/")

        assert response.status_code == 200
        body = response.content.decode()
        assert "Confirmado" in body
        assert "Reconhecemos o pagamento." in body
        assert "Nenhuma ação necessária agora." in body
        assert "Pagamento confirmado." not in body
        assert "Recebemos a confirmação do pagamento deste pedido." not in body
        assert "Aguardando pagamento" not in body

    def test_preparing_paid_tracking_hides_stale_payment_confirmation_alert(
        self,
        client: Client,
        order_with_payment,
    ) -> None:
        from shopman.orderman.models import Order
        from shopman.payman import PaymentService

        intent = PaymentService.create_intent(
            order_ref=order_with_payment.ref,
            amount_q=order_with_payment.total_q,
            method="pix",
        )
        order_with_payment.data["payment"]["intent_ref"] = intent.ref
        order_with_payment.save(update_fields=["data", "updated_at"])
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)
        Order.objects.filter(pk=order_with_payment.pk).update(
            status="preparing",
            updated_at=timezone.now(),
        )
        order_with_payment.refresh_from_db()

        response = client.get(f"/pedido/{order_with_payment.ref}/")

        assert response.status_code == 200
        body = response.content.decode()
        assert "Estamos preparando seu pedido." in body
        assert "Reconhecemos o pagamento." in body
        assert "Pagamento confirmado." not in body
        assert "Recebemos a confirmação do pagamento deste pedido." not in body
