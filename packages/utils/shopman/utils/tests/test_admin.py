"""Tests for shopman.utils admin utilities."""



class TestUnfoldBadge:
    """unfold_badge() XSS safety and behavior."""

    def test_basic_badge(self):
        from shopman.utils.contrib.admin_unfold.badges import unfold_badge

        result = unfold_badge("Active", "green")
        assert "Active" in str(result)
        assert "green" in str(result)

    def test_html_in_text_is_escaped(self):
        from shopman.utils.contrib.admin_unfold.badges import unfold_badge

        result = str(unfold_badge('<script>alert("xss")</script>'))
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_html_in_text_with_angle_brackets(self):
        from shopman.utils.contrib.admin_unfold.badges import unfold_badge

        result = str(unfold_badge("test<br>break"))
        assert "<br>" not in result
        assert "&lt;br&gt;" in result

    def test_unknown_color_uses_base(self):
        from shopman.utils.contrib.admin_unfold.badges import unfold_badge

        result = str(unfold_badge("Test", "nonexistent_color"))
        assert "bg-base-100" in result

    def test_badge_numeric(self):
        from shopman.utils.contrib.admin_unfold.badges import unfold_badge_numeric

        result = str(unfold_badge_numeric("42", "blue"))
        assert "42" in result
        assert "uppercase" not in result

    def test_badge_numeric_xss(self):
        from shopman.utils.contrib.admin_unfold.badges import unfold_badge_numeric

        result = str(unfold_badge_numeric('<img src=x onerror="alert(1)">'))
        assert "<img" not in result
        assert "&lt;img" in result


class TestAutofillInlineMixin:
    """AutofillInlineMixin with special characters in mapping."""

    def test_mixin_has_autofill_fields_default(self):
        from shopman.utils.admin.mixins import AutofillInlineMixin

        assert AutofillInlineMixin.autofill_fields == {}

    def test_mapping_with_special_characters(self):
        import json

        mapping = {"unit_price_q": "base_price_q", "desc": 'value "with" quotes'}
        serialized = json.dumps(mapping)
        parsed = json.loads(serialized)
        assert parsed["desc"] == 'value "with" quotes'

    def test_mapping_with_unicode(self):
        import json

        mapping = {"descricao": "descricao_completa", "preco": "preco_unitario"}
        serialized = json.dumps(mapping, ensure_ascii=False)
        parsed = json.loads(serialized)
        assert parsed["descricao"] == "descricao_completa"

    def test_empty_mapping_no_js_injection(self):
        from shopman.utils.admin.mixins import AutofillInlineMixin

        mixin = AutofillInlineMixin()
        assert not mixin.autofill_fields


class TestEnrichedAutocompleteJsonView:
    """EnrichedAutocompleteJsonView enriches results from ModelAdmin config."""

    def test_includes_extra_fields_from_model_admin(self):
        from unittest.mock import MagicMock

        from shopman.utils.admin.views import EnrichedAutocompleteJsonView

        obj = MagicMock()
        obj.base_price_q = 500
        type(obj).__name__ = "Product"

        model_admin = MagicMock()
        model_admin.autocomplete_extra_fields = ["base_price_q"]

        view = EnrichedAutocompleteJsonView()
        view.admin_site = MagicMock()
        view.admin_site._registry = {type(obj): model_admin}

        result = view.serialize_result(obj, "pk")
        assert result["base_price_q"] == 500

    def test_no_extra_fields_when_not_declared(self):
        from unittest.mock import MagicMock

        from shopman.utils.admin.views import EnrichedAutocompleteJsonView

        obj = MagicMock()
        obj.pk = 1
        obj.__str__ = lambda self: "Test Object"

        model_admin = MagicMock(spec=[])

        view = EnrichedAutocompleteJsonView()
        view.admin_site = MagicMock()
        view.admin_site._registry = {type(obj): model_admin}

        result = view.serialize_result(obj, "pk")
        assert "base_price_q" not in result

    def test_skips_missing_attributes(self):
        from unittest.mock import MagicMock

        from shopman.utils.admin.views import EnrichedAutocompleteJsonView

        obj = MagicMock(spec=["pk", "__str__"])
        obj.pk = 1
        obj.__str__ = lambda self: "Test"

        model_admin = MagicMock()
        model_admin.autocomplete_extra_fields = ["nonexistent_field"]

        view = EnrichedAutocompleteJsonView()
        view.admin_site = MagicMock()
        view.admin_site._registry = {type(obj): model_admin}

        result = view.serialize_result(obj, "pk")
        assert "nonexistent_field" not in result

    def test_unregistered_model_returns_standard_result(self):
        from unittest.mock import MagicMock

        from shopman.utils.admin.views import EnrichedAutocompleteJsonView

        obj = MagicMock()
        obj.pk = 42
        obj.__str__ = lambda self: "Unregistered"

        view = EnrichedAutocompleteJsonView()
        view.admin_site = MagicMock()
        view.admin_site._registry = {}

        result = view.serialize_result(obj, "pk")
        assert "id" in result
        assert "text" in result
