"""stock.hold() é idempotente por presença de order.data["hold_ids"].

Sem o guard, um re-dispatch de on_commit (retry após falha parcial, comando de
diagnóstico) sobrescrevia hold_ids e deixava os holds da 1ª passada órfãos — dupla
reserva até o backstop de 48h.
"""

from types import SimpleNamespace
from unittest.mock import patch

from shopman.shop.services import stock


def test_hold_skips_when_hold_ids_already_present():
    existing = [{"sku": "PAO", "hold_id": 42, "qty": 2.0}]
    order = SimpleNamespace(ref="WEB-1", data={"hold_ids": list(existing)})

    with patch("shopman.shop.services.stock.get_adapter") as get_adapter:
        stock.hold(order)

    get_adapter.assert_not_called()  # não tocou o adapter → não recriou holds
    assert order.data["hold_ids"] == existing  # inalterado


def test_hold_skips_even_when_prior_run_created_zero_holds():
    """Chave presente com lista vazia = fase já rodou (0 holds criados). Não repetir."""
    order = SimpleNamespace(ref="WEB-2", data={"hold_ids": []})

    with patch("shopman.shop.services.stock.get_adapter") as get_adapter:
        stock.hold(order)

    get_adapter.assert_not_called()
    assert order.data["hold_ids"] == []
