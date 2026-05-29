from __future__ import annotations

from unittest.mock import patch

from django.test import override_settings

from shopman.backstage.services.integration_readiness import (
    build_provider_readiness,
    efi_pix_readiness,
    focus_nfe_readiness,
    stripe_card_readiness,
)


@override_settings(
    SHOPMAN_FISCAL_ADAPTER="shopman.shop.adapters.fiscal_focusnfe.FocusNFeBackend",
    SHOPMAN_FOCUS_NFE={
        "environment": "homologacao",
        "token": "focus-token",
        "cnpj_emitente": "12.345.678/0001-90",
        "serie_nfce": "1",
        "base_url": "",
    },
)
def test_focus_nfe_staging_readiness_accepts_homologation_config():
    readiness = focus_nfe_readiness(mode="staging")

    assert readiness.status == "ready"
    assert readiness.environment == "homologacao"
    assert readiness.missing == ()


@override_settings(
    SHOPMAN_FISCAL_ADAPTER="shopman.shop.adapters.fiscal_focusnfe.FocusNFeBackend",
    SHOPMAN_FOCUS_NFE={
        "environment": "producao",
        "token": "focus-token",
        "cnpj_emitente": "12345678000190",
        "base_url": "https://api.focusnfe.com.br",
    },
)
def test_focus_nfe_staging_readiness_rejects_production_target():
    readiness = focus_nfe_readiness(mode="staging")

    assert readiness.status == "error"
    assert "FOCUS_NFE_ENVIRONMENT_homologacao" in readiness.missing
    assert "FOCUS_NFE_BASE_URL_homologacao" in readiness.missing


@override_settings(
    SHOPMAN_FISCAL_ADAPTER="shopman.shop.adapters.fiscal_focusnfe.FocusNFeBackend",
    SHOPMAN_FOCUS_NFE={
        "environment": "homologacao",
        "token": "focus-token",
        "cnpj_emitente": "",
        "base_url": "",
    },
)
def test_focus_nfe_readiness_uses_shop_document_as_emitente_fallback():
    with patch(
        "shopman.backstage.services.integration_readiness._shop_document",
        return_value="12.345.678/0001-90",
    ):
        readiness = focus_nfe_readiness(mode="staging")

    assert readiness.status == "ready"
    assert readiness.missing == ()


def test_efi_and_stripe_staging_readiness_accepts_sandbox_adapters(tmp_path):
    certificate = tmp_path / "efi.pem"
    certificate.write_text("dummy cert")

    with override_settings(
        SHOPMAN_PAYMENT_ADAPTERS={
            "pix": "shopman.shop.adapters.payment_efi",
            "card": "shopman.shop.adapters.payment_stripe",
            "cash": None,
            "external": None,
        },
        SHOPMAN_EFI={
            "sandbox": True,
            "client_id": "efi-client",
            "client_secret": "efi-secret",
            "certificate_path": str(certificate),
            "pix_key": "pix@example.com",
        },
        SHOPMAN_EFI_WEBHOOK={"webhook_token": "efi-webhook-token"},
        SHOPMAN_STRIPE={
            "publishable_key": "pk_test_shopman",
            "secret_key": "sk_test_shopman",
            "webhook_secret": "whsec_shopman",
            "capture_method": "manual",
            "domain": "https://staging.example.com",
        },
    ):
        assert efi_pix_readiness(mode="staging").status == "ready"
        assert stripe_card_readiness(mode="staging").status == "ready"


@override_settings(
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_mock",
        "card": "shopman.shop.adapters.payment_stripe",
        "cash": None,
        "external": None,
    },
    SHOPMAN_STRIPE={
        "publishable_key": "pk_live_shopman",
        "secret_key": "sk_live_shopman",
        "webhook_secret": "whsec_shopman",
        "capture_method": "manual",
        "domain": "https://staging.example.com",
    },
)
def test_stripe_staging_readiness_rejects_live_keys():
    readiness = stripe_card_readiness(mode="staging")

    assert readiness.status == "error"
    assert "STRIPE_SECRET_KEY_test" in readiness.missing
    assert "STRIPE_PUBLISHABLE_KEY_test" in readiness.missing


def test_provider_readiness_projection_does_not_expose_secret_values(settings):
    settings.SHOPMAN_FISCAL_ADAPTER = "shopman.shop.adapters.fiscal_focusnfe.FocusNFeBackend"
    settings.SHOPMAN_FOCUS_NFE = {
        "environment": "homologacao",
        "token": "super-secret-focus",
        "cnpj_emitente": "12345678000190",
        "base_url": "",
    }

    projected = [item.as_projection() for item in build_provider_readiness(mode="staging")]
    encoded = str(projected)

    assert "super-secret-focus" not in encoded
    assert {item["provider"] for item in projected} == {"focus_nfe", "efi_pix", "stripe_card"}
