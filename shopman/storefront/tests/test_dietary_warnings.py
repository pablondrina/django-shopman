"""WP-5 — avisos de preferência alimentar (conservador: só conflito claro)."""
from __future__ import annotations

from shopman.storefront.presentation.dietary import dietary_warnings


def test_no_warning_without_active_prefs():
    assert dietary_warnings(frozenset(), dietary_info=["100% vegetal"], allergens=["glúten"]) == ()


def test_warns_gluten_for_sem_gluten_pref():
    w = dietary_warnings({"sem_gluten"}, dietary_info=[], allergens=["glúten"])
    assert "Contém glúten" in w


def test_safe_tag_clears_restriction():
    # "sem lactose" no dietary_info limpa o aviso de lactose mesmo com trigger.
    w = dietary_warnings({"sem_lactose"}, dietary_info=["sem lactose"], allergens=["leite"])
    assert w == ()


def test_vegan_warns_on_animal_trigger_without_vegan_tag():
    w = dietary_warnings({"vegano"}, dietary_info=[], allergens=["leite"])
    assert "Não é vegano" in w


def test_vegan_tag_clears_warning():
    w = dietary_warnings({"vegano"}, dietary_info=["100% vegetal"], allergens=["leite"])
    assert w == ()


def test_no_false_positive_on_absence():
    # Produto sem dado dietético + pref vegano → NÃO avisa (não cria lobo).
    assert dietary_warnings({"vegano"}, dietary_info=[], allergens=[]) == ()


def test_multiple_prefs_accumulate():
    w = dietary_warnings({"sem_gluten", "sem_lactose"}, dietary_info=[], allergens=["glúten", "leite"])
    assert "Contém glúten" in w and "Contém lactose" in w
