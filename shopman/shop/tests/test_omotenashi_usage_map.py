"""Gate de deriva do mapa chave↔tela da copy omotenashi.

O snapshot `usage_map.py` é gerado por `manage.py omotenashi_usage_map`. Se o
consumo de copy mudar (chave nova, arquivo novo, chave órfã) sem regenerar, este
teste falha ANTES do catálogo do Admin mentir para o operador.
"""

from __future__ import annotations

from shopman.shop.omotenashi.copy import all_keys
from shopman.shop.omotenashi.usage import (
    CONSUMER_SCREENS,
    UNMAPPED_SURFACE,
    load_usage_map,
    scan_usages,
)


def test_usage_snapshot_matches_live_scan():
    assert load_usage_map() == scan_usages(), (
        "usage_map.py desatualizado — rode `manage.py omotenashi_usage_map` e commite."
    )


def test_every_registered_key_is_in_the_snapshot():
    snapshot = load_usage_map()
    assert set(snapshot) == set(all_keys())


def test_every_consumer_file_has_a_curated_screen_label():
    unlabeled = {
        ref.path
        for refs in load_usage_map().values()
        for ref in refs
        if ref.surface == UNMAPPED_SURFACE
    }
    assert not unlabeled, (
        f"Arquivos consumidores sem rótulo em CONSUMER_SCREENS: {sorted(unlabeled)} — "
        "adicione (superfície, tela) em shopman/shop/omotenashi/usage.py."
    )


def test_curated_labels_point_to_real_files():
    from shopman.shop.omotenashi.usage import REPO_ROOT

    stale = [path for path in CONSUMER_SCREENS if not (REPO_ROOT / path).exists()]
    assert not stale, f"CONSUMER_SCREENS com paths mortos: {stale}"


def test_unmapped_keys_are_the_known_review_bucket():
    # CART_EMPTY ficou sem consumidor no cutover headless — está no catálogo como
    # "sem uso mapeado" de propósito (candidata a limpeza ou religação). Se esta
    # lista crescer, é sinal de copy órfã nova: revise antes de aceitar aqui.
    unused = sorted(key for key, refs in load_usage_map().items() if not refs)
    assert unused == ["CART_EMPTY"], unused
