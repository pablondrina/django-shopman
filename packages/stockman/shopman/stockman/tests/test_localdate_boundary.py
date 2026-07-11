"""
Regressão de fuso: "hoje" é o dia LOCAL (timezone.localdate), não o dia UTC.

Cenário congelado: 01:00 UTC = 22:00 do dia ANTERIOR em America/Sao_Paulo.
Nessa janela (21h–00h BRT, quando a padaria fecha o dia e planeja produção),
``date.today()``/``now().date()`` num container UTC devolvem "amanhã" e a
classificação físico/planejado dos quants vira do avesso. Estes testes pinam
o comportamento correto: tudo que deriva "hoje" usa o dia local.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from shopman.stockman.models import Quant
from shopman.stockman.services.scope import quants_eligible_for

pytestmark = pytest.mark.django_db

# 01:00 UTC de 12/07 = 22:00 BRT de 11/07 — o dia local ainda é 11/07.
FROZEN_UTC = datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
LOCAL_TODAY = date(2026, 7, 11)
LOCAL_TOMORROW = date(2026, 7, 12)


@pytest.fixture
def frozen_boundary():
    with patch("django.utils.timezone.now", return_value=FROZEN_UTC):
        yield


def test_quant_for_local_today_is_physical_not_planned(frozen_boundary):
    """Quant com target_date = hoje (local) é físico às 22h BRT, não futuro."""
    quant = Quant.objects.create(
        sku="CROISSANT", target_date=LOCAL_TODAY, _quantity=Decimal("10"),
    )

    assert quant in Quant.objects.physical()
    assert quant not in Quant.objects.planned()
    assert quant.is_future is False


def test_quant_for_local_tomorrow_is_planned_not_physical(frozen_boundary):
    """Quant com target_date = amanhã (local) segue planejado às 22h BRT.

    Com o bug UTC, date.today() já devolvia 12/07 e a produção planejada de
    amanhã aparecia como estoque físico três horas antes de existir.
    """
    quant = Quant.objects.create(
        sku="CROISSANT", target_date=LOCAL_TOMORROW, _quantity=Decimal("10"),
    )

    assert quant in Quant.objects.planned()
    assert quant not in Quant.objects.physical()
    assert quant.is_future is True


def test_quants_eligible_for_defaults_to_local_today(frozen_boundary):
    """Sem target_date explícito, o scope canônico avalia o dia local."""
    today_quant = Quant.objects.create(
        sku="CROISSANT", target_date=LOCAL_TODAY, _quantity=Decimal("5"),
    )
    tomorrow_quant = Quant.objects.create(
        sku="CROISSANT", target_date=LOCAL_TOMORROW, _quantity=Decimal("5"),
    )

    eligible = list(quants_eligible_for("CROISSANT"))

    assert today_quant in eligible
    assert tomorrow_quant not in eligible
