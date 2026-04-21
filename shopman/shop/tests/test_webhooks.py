"""Tests for shop webhook views and dispatch."""

from __future__ import annotations

from django.urls import reverse


class TestWebhookURLs:
    """Webhook URLs resolve correctly."""

    def test_efi_pix(self, db):
        assert reverse("webhooks:efi-pix-webhook") == "/api/webhooks/efi/pix/"

    def test_stripe(self, db):
        assert reverse("webhooks:stripe-webhook") == "/api/webhooks/stripe/"


class TestWebhookImports:
    def test_efi_webhook_importable(self):
        from shopman.shop.webhooks.efi import EfiPixWebhookView

        assert EfiPixWebhookView is not None

    def test_stripe_webhook_importable(self):
        from shopman.shop.webhooks.stripe import StripeWebhookView

        assert StripeWebhookView is not None

    def test_efi_uses_flows_dispatch(self):
        """EFI webhook delegates to confirm_pix, which dispatches on_paid."""
        import inspect

        from shopman.shop.services import pix_confirmation
        from shopman.shop.webhooks import efi

        webhook_source = inspect.getsource(efi)
        assert "confirm_pix" in webhook_source

        service_source = inspect.getsource(pix_confirmation._apply_order_payment)
        assert "dispatch(order" in service_source
        assert "on_paid" in service_source
        assert "on_payment_confirmed" not in service_source

    def test_stripe_uses_flows_dispatch(self):
        """Stripe webhook uses shopman.lifecycle.dispatch, not channels.hooks."""
        import inspect

        from shopman.shop.webhooks.stripe import StripeWebhookView

        source = inspect.getsource(StripeWebhookView._trigger_order_hooks)
        assert "dispatch(order" in source
        assert "on_payment_confirmed" not in source
