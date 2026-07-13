"""Contrato: serializer DRF ↔ dataclass de projection (sem drop silencioso).

Um `serializers.Serializer` de campos declarados só emite os campos que declara.
Quando uma dataclass de projection ganha um campo e o serializer não acompanha, o
valor é descartado do payload sem erro — o cliente recebe `undefined` e a tela
renderiza vazio. Foi exatamente assim que o botão "Cancelar pedido" (danger) do
card de Ações do acompanhamento saiu em branco (TRACKING_CANCEL_CTA resolvia certo
no Python, mas `cancel_cta` não estava no `OrderTrackingCopySerializer`).

Este guardrail trava a classe inteira do bug, não só aquele botão:

- `MIRROR_CONTRACTS`: serializers que DEVEM espelhar a dataclass 1:1. Todo campo
  da dataclass tem de aparecer no serializer, salvo omissões explícitas e
  revisadas (3º item da tupla). Adicionar campo à dataclass sem expor no
  serializer (nem justificar a omissão) quebra o teste.
- `NON_MIRROR`: serializers sem dataclass-espelho único (corpo de request,
  envelope de erro, resposta montada como dict ad-hoc, card/sub-objeto enxuto de
  propósito). Exemptos de parity, mas listados: o meta-teste falha se surgir um
  serializer novo fora das duas listas, forçando uma decisão consciente.

Só há `serializers.Serializer` de resposta em `shopman/storefront/api/serializers.py`
— o backstage serializa via `projection_data` (asdict), que nunca descarta campo.
"""

from __future__ import annotations

import dataclasses
import inspect

from rest_framework import serializers

from shopman.shop.projections.types import (
    Action,
    OrderItemProjection,
    SavedAddressProjection,
    TimelineEventProjection,
)
from shopman.shop.services.conversation import RemoteConversationProjection
from shopman.storefront.api import serializers as api_serializers
from shopman.storefront.presentation.order_tracking import (
    OrderTrackingCopyProjection,
    OrderTrackingProjection,
    OrderTrackingPromiseProjection,
    OrderTrackingPromiseRowProjection,
    PickupInfoProjection,
)
from shopman.storefront.presentation.types import (
    FulfillmentProjection,
    OrderProgressStepProjection,
)

# (serializer, dataclass, campos da dataclass conscientemente NÃO expostos)
MIRROR_CONTRACTS = [
    (api_serializers.ActionSerializer, Action, set()),
    # Timeline do storefront mostra só label/hora; actor/detail servem a outras superfícies.
    (api_serializers.TimelineEventSerializer, TimelineEventProjection, {"actor", "detail"}),
    (api_serializers.OrderItemSerializer, OrderItemProjection, set()),
    (api_serializers.PickupInfoSerializer, PickupInfoProjection, set()),
    (api_serializers.OrderProgressStepSerializer, OrderProgressStepProjection, set()),
    # O cliente recebe os ISOs crus (dispatched_at/delivered_at); os *_display são internos.
    (
        api_serializers.FulfillmentSerializer,
        FulfillmentProjection,
        {"dispatched_at_display", "delivered_at_display"},
    ),
    (api_serializers.OrderTrackingCopySerializer, OrderTrackingCopyProjection, set()),
    (api_serializers.OrderTrackingPromiseSerializer, OrderTrackingPromiseProjection, set()),
    (
        api_serializers.OrderTrackingPromiseRowSerializer,
        OrderTrackingPromiseRowProjection,
        set(),
    ),
    # `order_ref` é usado só server-side (support_url/share_text); o cliente lê `ref`.
    (api_serializers.OrderTrackingSerializer, OrderTrackingProjection, {"order_ref"}),
    (api_serializers.AddressSerializer, SavedAddressProjection, set()),
    (api_serializers.RemoteConversationSerializer, RemoteConversationProjection, set()),
]

# Serializers sem dataclass-espelho único — exemptos de parity, mas classificados.
NON_MIRROR = {
    # Corpos de request (entrada, não projection).
    "SetSkuQtySerializer",
    "CheckoutSerializer",
    "ReverseGeocodeRequestSerializer",
    # Envelope de erro canônico ({detail, ...}).
    "DetailSerializer",
    # Respostas montadas como dict ad-hoc no view (não há dataclass fonte).
    "CheckoutResponseSerializer",
    "AvailabilityResponseSerializer",
    "ReverseGeocodeResponseSerializer",
    "CollectionSerializer",
    "OrderHistoryItemSerializer",
    # Card/sub-objeto enxuto de propósito: expõe um subconjunto deliberado.
    "ProductListItemSerializer",  # card do menu ⊂ CatalogItemProjection
    "CustomerProfileSerializer",  # perfil resumido, não o CustomerProfileProjection inteiro
}


def _serializer_field_names(serializer_cls: type[serializers.Serializer]) -> set[str]:
    return set(serializer_cls().get_fields().keys())


def _dataclass_field_names(dataclass_type: type) -> set[str]:
    return {f.name for f in dataclasses.fields(dataclass_type)}


def _all_response_serializers() -> set[str]:
    """Toda subclasse de Serializer declarada no módulo de serializers do storefront."""
    return {
        name
        for name, obj in inspect.getmembers(api_serializers, inspect.isclass)
        if issubclass(obj, serializers.Serializer)
        and obj is not serializers.Serializer
        and obj.__module__ == api_serializers.__name__
    }


def test_every_serializer_is_classified():
    """Serializer novo tem de entrar em MIRROR_CONTRACTS ou NON_MIRROR (decisão consciente)."""
    classified = {ser.__name__ for ser, _dc, _omit in MIRROR_CONTRACTS} | NON_MIRROR
    declared = _all_response_serializers()

    unclassified = declared - classified
    assert not unclassified, (
        "Serializer(s) sem classificação de contrato: "
        f"{sorted(unclassified)}. Adicione a MIRROR_CONTRACTS (com a dataclass "
        "espelhada) ou a NON_MIRROR (request/dict ad-hoc/card enxuto)."
    )

    stale = classified - declared
    assert not stale, (
        f"Classificação obsoleta (serializer não existe mais): {sorted(stale)}."
    )


def test_mirror_serializers_expose_every_dataclass_field():
    """Todo campo da dataclass aparece no serializer, salvo omissão explícita."""
    for serializer_cls, dataclass_type, omitted in MIRROR_CONTRACTS:
        dc_fields = _dataclass_field_names(dataclass_type)
        ser_fields = _serializer_field_names(serializer_cls)

        stale_omissions = omitted - dc_fields
        assert not stale_omissions, (
            f"{serializer_cls.__name__}: omissões que não existem mais em "
            f"{dataclass_type.__name__}: {sorted(stale_omissions)}."
        )

        dropped = dc_fields - omitted - ser_fields
        assert not dropped, (
            f"{serializer_cls.__name__} NÃO expõe campo(s) de "
            f"{dataclass_type.__name__}: {sorted(dropped)}. Declare no serializer "
            "ou registre como omissão consciente na tupla do contrato."
        )
