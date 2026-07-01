"""Collection admin — editor JSON da regra (smart collection).

Vive na suíte orquestrador (não em offerman/tests) porque a camada admin/unfold +
import_export só está instalada com o settings completo; a fatia test-offerman roda
o kernel isolado, sem django.contrib.admin.
"""

from __future__ import annotations

import pytest
from shopman.offerman.contrib.admin_unfold.admin import CollectionAdminForm


@pytest.mark.django_db
def test_form_parses_and_saves_rule():
    form = CollectionAdminForm(
        data={
            "ref": "veganos",
            "name": "Veganos",
            "sort_order": 0,
            "rule": '{"match":"all","conditions":[{"field":"keyword","op":"eq","value":"vegano"}]}',
        }
    )
    assert form.is_valid(), form.errors
    coll = form.save()
    assert coll.rule["match"] == "all"
    assert coll.is_smart is True


@pytest.mark.django_db
def test_empty_rule_is_manual_collection():
    form = CollectionAdminForm(data={"ref": "manual", "name": "Manual", "sort_order": 0, "rule": ""})
    assert form.is_valid(), form.errors
    coll = form.save()
    assert coll.rule == {}
    assert coll.is_smart is False


@pytest.mark.django_db
def test_rejects_bad_json():
    form = CollectionAdminForm(data={"ref": "x", "name": "X", "sort_order": 0, "rule": "{not json"})
    assert not form.is_valid()
    assert "rule" in form.errors


@pytest.mark.django_db
def test_rejects_invalid_rule_schema():
    form = CollectionAdminForm(
        data={
            "ref": "x",
            "name": "X",
            "sort_order": 0,
            "rule": '{"conditions":[{"field":"nope","op":"eq","value":1}]}',
        }
    )
    assert not form.is_valid()
    assert "rule" in form.errors
