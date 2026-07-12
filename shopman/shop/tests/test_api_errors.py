"""Dialeto canônico de erro HTTP (``shopman/shop/api_errors.py``).

O EXCEPTION_HANDLER converte ValidationError de serializer para
``{detail, field, errors}`` — o shape que os fronts leem (``data.detail`` +
roteamento por ``data.field``). As demais exceções DRF passam intactas pelo
handler default (já carregam ``detail``).
"""

from __future__ import annotations

from rest_framework import exceptions, serializers

from shopman.shop.api_errors import exception_handler, validation_error_payload


class _CheckoutLikeSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    phone = serializers.CharField(max_length=32)
    qty = serializers.IntegerField(required=False, min_value=0, max_value=99)


def _validation_exc(data: dict) -> exceptions.ValidationError:
    serializer = _CheckoutLikeSerializer(data=data)
    assert not serializer.is_valid()
    return exceptions.ValidationError(serializer.errors)


def test_field_error_becomes_detail_field_errors():
    exc = _validation_exc({"name": "Ana"})  # phone ausente
    response = exception_handler(exc, context={})

    assert response.status_code == 400
    assert response.data["field"] == "phone"
    assert response.data["detail"] == response.data["errors"]["phone"][0]
    assert isinstance(response.data["errors"]["phone"], list)


def test_serializer_messages_are_pt_br():
    # LANGUAGE_CODE=pt-br + locale pt_BR do DRF: a mensagem do validator chega
    # traduzida ao cliente, nunca em inglês.
    exc = _validation_exc({"name": "Ana", "phone": "43999", "qty": 1000000})
    response = exception_handler(exc, context={})

    assert response.data["field"] == "qty"
    assert "igual a 99" in response.data["detail"]
    assert "Ensure" not in response.data["detail"]


def test_first_field_wins_and_all_fields_are_preserved():
    exc = _validation_exc({})
    response = exception_handler(exc, context={})

    # `field` = primeiro campo na ordem do serializer; o mapa completo fica em errors.
    assert response.data["field"] == "name"
    assert set(response.data["errors"]) == {"name", "phone"}


def test_non_field_error_has_detail_without_field():
    response = exception_handler(exceptions.ValidationError("Carrinho expirou."), context={})

    assert response.status_code == 400
    assert response.data["detail"] == "Carrinho expirou."
    assert "field" not in response.data
    assert response.data["errors"]["non_field_errors"] == ["Carrinho expirou."]


def test_nested_errors_flatten_to_dotted_paths():
    payload = validation_error_payload(
        {
            "delivery_address_structured": {"cep": ["CEP inválido."]},
            "items": [{}, {"sku": ["SKU obrigatório."]}],
        }
    )

    assert payload["field"] == "delivery_address_structured.cep"
    assert payload["detail"] == "CEP inválido."
    assert payload["errors"]["delivery_address_structured.cep"] == ["CEP inválido."]
    assert payload["errors"]["items.1.sku"] == ["SKU obrigatório."]


def test_status_and_shape_preserved_for_other_drf_exceptions():
    # NotAuthenticated/Throttled/NotFound já saem {"detail": ...} do handler
    # default — o dialeto exige apenas que detail exista, e ele existe.
    for exc, status in (
        (exceptions.NotAuthenticated(), 401),
        (exceptions.NotFound(), 404),
        (exceptions.Throttled(wait=10), 429),
    ):
        response = exception_handler(exc, context={})
        assert response.status_code == status
        assert "detail" in response.data


def test_non_drf_exception_returns_none_for_500_path():
    assert exception_handler(RuntimeError("bug"), context={}) is None
