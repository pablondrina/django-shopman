from __future__ import annotations

from django.test import RequestFactory
from django.utils import timezone

from shopman.shop.services import customer_orders, payment_status


class StubCartService:
    calls: list[dict] = []

    @classmethod
    def add_item(cls, request, **kwargs):
        cls.calls.append(kwargs)


def test_customer_order_history_summaries_filter_and_label(customer):
    from shopman.orderman.models import Order

    Order.objects.create(
        ref="ORD-HIST-ACTIVE",
        channel_ref="web",
        status="new",
        total_q=1200,
        handle_type="phone",
        handle_ref=customer.phone,
        data={},
    )
    Order.objects.create(
        ref="ORD-HIST-DONE",
        channel_ref="web",
        status="completed",
        total_q=2400,
        handle_type="phone",
        handle_ref=customer.phone,
        data={},
    )

    summaries = customer_orders.history_summaries_for_phone(
        customer.phone,
        filter_param="anteriores",
    )

    assert [summary.ref for summary in summaries] == ["ORD-HIST-DONE"]
    assert summaries[0].status_label == "Concluído"
    assert summaries[0].total_q == 2400


def test_customer_order_history_uses_same_identity_contract_for_ref_and_phone(customer):
    from shopman.orderman.models import Order

    by_ref = Order.objects.create(
        ref="ORD-HIST-BY-REF",
        channel_ref="web",
        status="completed",
        total_q=1500,
        data={"customer_ref": customer.ref},
    )
    by_phone = Order.objects.create(
        ref="ORD-HIST-BY-PHONE",
        channel_ref="web",
        status="completed",
        total_q=2100,
        handle_type="phone",
        handle_ref=customer.phone,
        data={},
    )

    summaries = customer_orders.history_summaries_for_customer(
        customer_ref=customer.ref,
        phone=customer.phone,
    )

    refs = {summary.ref for summary in summaries}
    assert refs == {by_ref.ref, by_phone.ref}


def test_reorder_service_uses_listing_price(order_items, listing_item):
    request = RequestFactory().post("/")
    StubCartService.calls = []

    skipped = customer_orders.add_reorder_items(
        request,
        order_items,
        cart_service=StubCartService,
        channel_ref=listing_item.listing.ref,
    )

    assert skipped == []
    price_by_sku = {call["sku"]: call["unit_price_q"] for call in StubCartService.calls}
    name_by_sku = {call["sku"]: call["name"] for call in StubCartService.calls}
    assert price_by_sku[listing_item.product.sku] == listing_item.price_q
    assert name_by_sku[listing_item.product.sku] == listing_item.product.name


def test_payment_status_invalid_expiry_degrades_to_pending(order_with_payment):
    order_with_payment.data["payment"]["expires_at"] = "not-a-datetime"
    order_with_payment.save(update_fields=["data"])

    projection = payment_status.build_payment_status(order_with_payment)

    assert projection.is_expired is False
    assert projection.is_terminal is False


def test_payment_status_expired_pix_is_terminal(order_with_payment):
    order_with_payment.data["payment"]["expires_at"] = (
        timezone.now().replace(microsecond=0) - timezone.timedelta(minutes=5)
    ).isoformat()
    order_with_payment.save(update_fields=["data"])

    projection = payment_status.build_payment_status(order_with_payment)

    assert projection.is_expired is True
    assert projection.is_terminal is True


def test_customer_cancel_gate_preserves_payment_specific_refusal(order_with_payment):
    from shopman.payman import PaymentService

    intent = PaymentService.create_intent(
        order_ref=order_with_payment.ref,
        amount_q=order_with_payment.total_q,
        method="pix",
    )
    order_with_payment.data["payment"]["intent_ref"] = intent.ref
    order_with_payment.save(update_fields=["data"])
    PaymentService.authorize(intent.ref, gateway_id="test-gw-cancel")
    PaymentService.capture(intent.ref)

    assert customer_orders.can_cancel(order_with_payment) is False
    assert payment_status.can_cancel(order_with_payment) is False
