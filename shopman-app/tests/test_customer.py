"""
Tests for customer module.

Covers:
- PART A: WhatsApp/Manychat subscriber recognition and creation
- PART B: PDV/Balcão anonymous, CPF-only, and phone-identified
- PART D: iFood customer handling
- Edge cases: Guestman not installed

Note: Notification routing tests (PART C) are deferred to WP-R4
when the notifications module is migrated.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase

from shopman.customer.handlers import CustomerEnsureHandler
from shopman.ordering.models import Channel, Directive, Order

# Path prefix for patching handler internals
_H = "shopman.customer.handlers"


def _make_channel(code: str, name: str, **config_overrides) -> Channel:
    """Helper to create test channels with common defaults."""
    defaults = {
        "balcao": {
            "pricing_policy": "internal",
            "edit_policy": "open",
            "config": {
                "notification_routing": {"backend": "none"},
                "post_commit_directives": ["customer.ensure"],
            },
        },
        "whatsapp": {
            "pricing_policy": "internal",
            "edit_policy": "open",
            "config": {
                "notification_routing": {"backend": "manychat", "fallback": "sms"},
                "post_commit_directives": ["customer.ensure", "notification.send"],
            },
        },
        "ifood": {
            "pricing_policy": "external",
            "edit_policy": "locked",
            "config": {
                "notification_routing": {"backend": "none"},
                "post_commit_directives": ["customer.ensure"],
            },
        },
    }

    channel_defaults = defaults.get(code, {
        "pricing_policy": "internal",
        "edit_policy": "open",
        "config": {},
    })

    if config_overrides:
        channel_defaults["config"].update(config_overrides)

    channel, _ = Channel.objects.update_or_create(
        ref=code,
        defaults=dict(
            name=name,
            is_active=True,
            **channel_defaults,
        ),
    )
    return channel


def _make_order(channel, *, handle_type=None, handle_ref=None, customer_data=None, **kwargs) -> Order:
    """Helper to create test orders."""
    data = kwargs.pop("data", {})
    if customer_data:
        data["customer"] = customer_data
    return Order.objects.create(
        ref=f"ORD-{uuid.uuid4().hex[:8].upper()}",
        channel=channel,
        session_key=f"SESS-{uuid.uuid4().hex[:8]}",
        handle_type=handle_type,
        handle_ref=handle_ref,
        status="new",
        snapshot={"items": [], "data": {}, "pricing": {}, "rev": 0},
        data=data,
        total_q=2400,
        **kwargs,
    )


def _make_directive(order_ref: str) -> Directive:
    """Create a customer.ensure directive for testing."""
    d = Directive(
        topic="customer.ensure",
        status="running",
        payload={"order_ref": order_ref},
    )
    d.save()
    d.refresh_from_db()
    return d


def _mock_customer(ref: str = "CLI-TEST", first_name: str = "Test") -> MagicMock:
    """Create a mock Customer object."""
    customer = MagicMock()
    customer.ref = ref
    customer.first_name = first_name
    customer.is_active = True
    return customer


def _mock_svc(
    get_by_phone=None,
    get_by_document=None,
    create=None,
) -> MagicMock:
    """Create a mock customer service module."""
    svc = MagicMock()
    svc.get_by_phone.return_value = get_by_phone
    svc.get_by_document.return_value = get_by_document
    svc.create.return_value = create
    return svc


# ======================================================================
# PART A — WhatsApp / Manychat
# ======================================================================


class WhatsAppSubscriberRecognizedTests(TestCase):

    def setUp(self) -> None:
        self.channel = _make_channel("whatsapp", "WhatsApp")
        self.handler = CustomerEnsureHandler()

    @patch(f"{_H}._update_insights")
    @patch(f"{_H}._create_timeline_event")
    @patch(f"{_H}._maybe_update_name")
    @patch(f"{_H}._find_by_identifier")
    @patch(f"{_H}._identifiers_available", return_value=True)
    @patch(f"{_H}._guestman_available", return_value=True)
    def test_whatsapp_subscriber_recognized(
        self, mock_avail, mock_id_avail, mock_find, mock_update_name, mock_timeline, mock_insights,
    ):
        mock_customer = _mock_customer("MC-EXISTING1", "Maria")
        mock_find.return_value = mock_customer

        order = _make_order(
            self.channel,
            handle_type="manychat",
            handle_ref="12345",
            customer_data={"name": "Maria Silva", "phone": "+5543999999999"},
        )
        directive = _make_directive(order.ref)

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

        mock_find.assert_called_once_with("manychat", "12345")

        order.refresh_from_db()
        self.assertEqual(order.data["customer_ref"], "MC-EXISTING1")


class WhatsAppNewSubscriberCreatedTests(TestCase):

    def setUp(self) -> None:
        self.channel = _make_channel("whatsapp", "WhatsApp")
        self.handler = CustomerEnsureHandler()

    @patch(f"{_H}._update_insights")
    @patch(f"{_H}._create_timeline_event")
    @patch(f"{_H}._add_identifier")
    @patch(f"{_H}._find_by_identifier", return_value=None)
    @patch(f"{_H}._identifiers_available", return_value=True)
    @patch(f"{_H}._guestman_available", return_value=True)
    def test_whatsapp_new_subscriber_created(
        self, mock_avail, mock_id_avail, mock_find, mock_add_id, mock_timeline, mock_insights,
    ):
        mock_new_customer = _mock_customer("MC-NEW12345", "João")
        svc = _mock_svc(get_by_phone=None, create=mock_new_customer)

        with patch(f"{_H}._get_customer_service", return_value=svc):
            order = _make_order(
                self.channel,
                handle_type="manychat",
                handle_ref="99999",
                customer_data={"name": "João Santos", "phone": "+5543988888888"},
            )
            directive = _make_directive(order.ref)

            self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

        svc.create.assert_called_once()
        call_kwargs = svc.create.call_args[1]
        self.assertEqual(call_kwargs["first_name"], "João")
        self.assertEqual(call_kwargs["last_name"], "Santos")
        self.assertEqual(call_kwargs["source_system"], "manychat")

        mock_add_id.assert_called_once_with(
            mock_new_customer, "manychat", "99999", is_primary=True,
        )


# ======================================================================
# PART B — PDV / Balcão
# ======================================================================


class BalcaoAnonymousTests(TestCase):

    def setUp(self) -> None:
        self.channel = _make_channel("balcao", "Balcão")
        self.handler = CustomerEnsureHandler()

    @patch(f"{_H}._guestman_available", return_value=True)
    def test_balcao_anonymous(self, mock_avail):
        order = _make_order(
            self.channel,
            handle_type=None,
            handle_ref=None,
            customer_data={},
        )
        directive = _make_directive(order.ref)

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

        order.refresh_from_db()
        self.assertNotIn("customer_ref", order.data)


class BalcaoCpfOnlyTests(TestCase):

    def setUp(self) -> None:
        self.channel = _make_channel("balcao", "Balcão")
        self.handler = CustomerEnsureHandler()

    @patch(f"{_H}._update_insights")
    @patch(f"{_H}._create_timeline_event")
    @patch(f"{_H}._add_identifier")
    @patch(f"{_H}._find_by_identifier", return_value=None)
    @patch(f"{_H}._identifiers_available", return_value=True)
    @patch(f"{_H}._guestman_available", return_value=True)
    def test_balcao_cpf_only(
        self, mock_avail, mock_id_avail, mock_find_id, mock_add_id, mock_timeline, mock_insights,
    ):
        mock_customer = _mock_customer("CLI-CPF12345")
        svc = _mock_svc(get_by_document=None, create=mock_customer)

        with patch(f"{_H}._get_customer_service", return_value=svc):
            order = _make_order(
                self.channel,
                handle_type=None,
                handle_ref=None,
                customer_data={"cpf": "123.456.789-00", "name": "Ana Lima"},
            )
            directive = _make_directive(order.ref)

            self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

        svc.create.assert_called_once()
        call_kwargs = svc.create.call_args[1]
        self.assertEqual(call_kwargs["document"], "12345678900")
        self.assertEqual(call_kwargs["source_system"], "balcao")

        mock_add_id.assert_called_once_with(
            mock_customer, "cpf", "12345678900", is_primary=True,
        )

        order.refresh_from_db()
        self.assertEqual(order.data["customer_ref"], "CLI-CPF12345")

    def test_balcao_cpf_in_order_data_for_fiscal(self):
        order = _make_order(
            self.channel,
            handle_type=None,
            handle_ref=None,
            customer_data={"cpf": "123.456.789-00"},
        )

        cpf = order.data.get("customer", {}).get("cpf")
        self.assertEqual(cpf, "123.456.789-00")


class BalcaoPhoneIdentifiedTests(TestCase):

    def setUp(self) -> None:
        self.channel = _make_channel("balcao", "Balcão")
        self.handler = CustomerEnsureHandler()

    @patch(f"{_H}._update_insights")
    @patch(f"{_H}._create_timeline_event")
    @patch(f"{_H}._maybe_update_name")
    @patch(f"{_H}._guestman_available", return_value=True)
    def test_balcao_phone_identified(self, mock_avail, mock_update_name, mock_timeline, mock_insights):
        mock_customer = _mock_customer("CLI-PHONE123", "Carlos")
        svc = _mock_svc(get_by_phone=mock_customer)

        with patch(f"{_H}._get_customer_service", return_value=svc):
            order = _make_order(
                self.channel,
                handle_type=None,
                handle_ref=None,
                customer_data={"phone": "+5543977777777", "name": "Carlos Souza"},
            )
            directive = _make_directive(order.ref)

            self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

        order.refresh_from_db()
        self.assertEqual(order.data["customer_ref"], "CLI-PHONE123")


# ======================================================================
# PART D — iFood
# ======================================================================


class IFoodCustomerHandlingTests(TestCase):

    def setUp(self) -> None:
        self.channel = _make_channel("ifood", "iFood")
        self.handler = CustomerEnsureHandler()

    @patch(f"{_H}._update_insights")
    @patch(f"{_H}._create_timeline_event")
    @patch(f"{_H}._add_identifier")
    @patch(f"{_H}._find_by_identifier", return_value=None)
    @patch(f"{_H}._identifiers_available", return_value=True)
    @patch(f"{_H}._guestman_available", return_value=True)
    def test_ifood_new_customer_created(
        self, mock_avail, mock_id_avail, mock_find_id, mock_add_id, mock_timeline, mock_insights,
    ):
        mock_customer = _mock_customer("IF-NEW12345")
        svc = _mock_svc(create=mock_customer)

        with patch(f"{_H}._get_customer_service", return_value=svc):
            order = _make_order(
                self.channel,
                handle_type="ifood",
                handle_ref="IFOOD-ORDER-789",
                external_ref="IFOOD-ORDER-789",
                customer_data={"name": "João via iFood"},
            )
            directive = _make_directive(order.ref)

            self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

        svc.create.assert_called_once()
        call_kwargs = svc.create.call_args[1]
        self.assertEqual(call_kwargs["source_system"], "ifood")
        self.assertEqual(call_kwargs["first_name"], "João")
        self.assertEqual(call_kwargs["last_name"], "via iFood")

        mock_add_id.assert_called_once_with(
            mock_customer, "ifood", "IFOOD-ORDER-789", is_primary=True,
        )

    @patch(f"{_H}._update_insights")
    @patch(f"{_H}._create_timeline_event")
    @patch(f"{_H}._maybe_update_name")
    @patch(f"{_H}._find_by_identifier")
    @patch(f"{_H}._identifiers_available", return_value=True)
    @patch(f"{_H}._guestman_available", return_value=True)
    def test_ifood_existing_customer_linked(
        self, mock_avail, mock_id_avail, mock_find_id, mock_update_name, mock_timeline, mock_insights,
    ):
        mock_customer = _mock_customer("IF-EXISTING", "Existing")
        mock_find_id.return_value = mock_customer

        order = _make_order(
            self.channel,
            handle_type="ifood",
            handle_ref="IFOOD-ORDER-111",
            external_ref="IFOOD-ORDER-111",
            customer_data={"name": "Existing Customer"},
        )
        directive = _make_directive(order.ref)

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

        mock_find_id.assert_called_once_with("ifood", "IFOOD-ORDER-111")

        order.refresh_from_db()
        self.assertEqual(order.data["customer_ref"], "IF-EXISTING")


# ======================================================================
# Edge cases
# ======================================================================


class GuestmanNotInstalledTests(TestCase):

    def setUp(self) -> None:
        self.channel = _make_channel("whatsapp", "WhatsApp")
        self.handler = CustomerEnsureHandler()

    @patch(f"{_H}._guestman_available", return_value=False)
    def test_guestman_not_installed_skips_gracefully(self, mock_avail):
        order = _make_order(
            self.channel,
            handle_type="manychat",
            handle_ref="12345",
        )
        directive = _make_directive(order.ref)

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
