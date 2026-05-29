from __future__ import annotations

from base64 import b64encode
import json
from unittest.mock import patch

from django.test import override_settings


def _settings():
    return {
        "environment": "homologacao",
        "token": "focus-token",
        "cnpj_emitente": "12.345.678/0001-99",
        "serie_nfce": "1",
        "timeout": 10,
    }


def test_focus_nfe_backend_is_the_only_canonical_class_name():
    from shopman.shop.adapters import fiscal_focusnfe

    assert hasattr(fiscal_focusnfe, "FocusNFeBackend")
    assert not hasattr(fiscal_focusnfe, "FocusNFCeBackend")
    assert fiscal_focusnfe.__all__ == ["FocusNFeBackend"]


@override_settings(SHOPMAN_FOCUS_NFE=_settings())
def test_focus_nfe_emit_maps_nfce_payload_to_homologation_endpoint():
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    captured = {}

    def fake_request(method, path, payload, config):
        captured.update(method=method, path=path, payload=payload, config=config)
        return {
            "status": "autorizado",
            "ref": "ORD-1",
            "numero": "123",
            "serie": "1",
            "protocolo": "141240000000000",
            "chave_nfe": "NFC-E-KEY",
            "caminho_danfe": "https://example.test/danfe.pdf",
            "qrcode_url": "https://example.test/qrcode",
        }

    with patch("shopman.shop.adapters.fiscal_focusnfe._request", side_effect=fake_request):
        result = FocusNFeBackend().emit(
            reference="ORD-1",
            items=[{
                "sku": "SKU-1",
                "name": "Pao",
                "qty": "2",
                "unit": "un",
                "unit_price_q": 500,
                "total_q": 1000,
                "fiscal": {"ncm": "19059090", "cfop": "5102"},
            }],
            customer={"name": "Ana", "tax_id": "123.456.789-09"},
            payment={"method": "pix", "amount_q": 1000},
        )

    assert result.success is True
    assert result.access_key == "NFC-E-KEY"
    assert result.protocol_number == "141240000000000"
    assert captured["method"] == "POST"
    assert captured["path"] == "/v2/nfce?ref=ORD-1&completa=1"
    assert captured["payload"]["cnpj_emitente"] == "12345678000199"
    assert captured["payload"]["local_destino"] == "1"
    assert captured["payload"]["valor_produtos"] == "10.00"
    assert captured["payload"]["valor_total"] == "10.00"
    assert captured["payload"]["cpf_destinatario"] == "12345678909"
    assert captured["payload"]["indicador_inscricao_estadual_destinatario"] == "9"
    assert captured["payload"]["items"][0]["codigo_ncm"] == "19059090"
    assert captured["payload"]["formas_pagamento"] == [{
        "forma_pagamento": "17",
        "valor_pagamento": "10.00",
    }]


@override_settings(SHOPMAN_FOCUS_NFE=_settings())
def test_focus_nfe_emit_fails_before_http_when_product_has_no_ncm():
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    with patch("shopman.shop.adapters.fiscal_focusnfe._request") as request:
        result = FocusNFeBackend().emit(
            reference="ORD-2",
            items=[{
                "sku": "SKU-2",
                "name": "Produto sem fiscal",
                "qty": "1",
                "unit_price_q": 1000,
                "total_q": 1000,
                "fiscal": {},
            }],
            customer={},
            payment={"method": "cash", "amount_q": 1000},
        )

    assert result.success is False
    assert result.error_code == "focus_nfe_invalid_payload"
    assert "sem NCM" in result.error_message
    request.assert_not_called()


@override_settings(
    SHOPMAN_FOCUS_NFE={
        "environment": "homologacao",
        "token": "focus-token",
        "cnpj_emitente": "",
        "serie_nfce": "1",
        "timeout": 10,
    }
)
def test_focus_nfe_emit_uses_shop_document_as_emitente_fallback():
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    captured = {}

    def fake_request(method, path, payload, config):
        captured.update(method=method, path=path, payload=payload, config=config)
        return {
            "status": "autorizado",
            "ref": "ORD-3",
            "chave_nfe": "NFC-E-KEY",
        }

    with (
        patch("shopman.shop.adapters.fiscal_focusnfe._shop_document", return_value="12.345.678/0001-99"),
        patch("shopman.shop.adapters.fiscal_focusnfe._request", side_effect=fake_request),
    ):
        result = FocusNFeBackend().emit(
            reference="ORD-3",
            items=[{
                "sku": "SKU-3",
                "name": "Pao",
                "qty": "1",
                "unit_price_q": 1000,
                "total_q": 1000,
                "fiscal": {"ncm": "19059090", "cfop": "5102"},
            }],
            customer={},
            payment={"method": "cash", "amount_q": 1000},
        )

    assert result.success is True
    assert captured["payload"]["cnpj_emitente"] == "12345678000199"


@override_settings(SHOPMAN_FOCUS_NFE=_settings())
def test_focus_nfe_query_asks_for_complete_response():
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    captured = {}

    def fake_request(method, path, payload, config):
        captured.update(method=method, path=path, payload=payload, config=config)
        return {
            "status": "autorizado",
            "ref": "ORD-1",
            "chave_nfe": "NFC-E-KEY",
        }

    with patch("shopman.shop.adapters.fiscal_focusnfe._request", side_effect=fake_request):
        result = FocusNFeBackend().query_status(reference="ORD-1")

    assert result.success is True
    assert captured["method"] == "GET"
    assert captured["path"] == "/v2/nfce/ORD-1?completa=1"
    assert captured["payload"] is None


def test_focus_nfe_request_uses_homologation_basic_auth_and_json():
    from shopman.shop.adapters import fiscal_focusnfe

    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"status":"autorizado"}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["authorization"] = request.get_header("Authorization")
        captured["content_type"] = request.get_header("Content-type")
        captured["accept"] = request.get_header("Accept")
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    with patch("shopman.shop.adapters.fiscal_focusnfe.urlopen", side_effect=fake_urlopen):
        response = fiscal_focusnfe._request(
            "POST",
            "/v2/nfce?ref=ORD-1&completa=1",
            {"cnpj_emitente": "12345678000199"},
            _settings(),
        )

    expected_auth = b64encode(b"focus-token:").decode("ascii")
    assert response == {"status": "autorizado"}
    assert captured["url"] == "https://homologacao.focusnfe.com.br/v2/nfce?ref=ORD-1&completa=1"
    assert captured["method"] == "POST"
    assert captured["authorization"] == f"Basic {expected_auth}"
    assert captured["content_type"] == "application/json"
    assert captured["accept"] == "application/json"
    assert captured["payload"] == {"cnpj_emitente": "12345678000199"}
    assert captured["timeout"] == 10
