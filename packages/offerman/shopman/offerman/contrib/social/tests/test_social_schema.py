"""Unit tests for ProductSocialAttributes + metadata helpers (pure Python)."""

from __future__ import annotations

from shopman.offerman.contrib.social.schema import (
    ProductSocialAttributes,
    get_social_attributes,
    set_social_attributes,
)


class TestRoundTrip:
    def test_defaults_produce_empty_metadata(self):
        attrs = ProductSocialAttributes()
        assert attrs.to_metadata() == {}
        assert attrs.has_data is False

    def test_full_round_trip(self):
        attrs = ProductSocialAttributes(
            brand="Nelson",
            gtin="4006381333931",  # valid EAN-13
            mpn="PAO-001",
            condition="new",
            google_product_category="2271",
            tiktok_category_id="600123",
            hashtags=["pão", "artesanal"],
            social_caption="Feito à mão, todo dia.",
        )
        metadata = set_social_attributes({}, attrs)
        back = ProductSocialAttributes.from_metadata(metadata)
        # condition "new" is the default → dropped from metadata, re-defaults on read.
        assert back == attrs

    def test_only_non_default_keys_persisted(self):
        attrs = ProductSocialAttributes(brand="Nelson", condition="new")
        payload = attrs.to_metadata()
        assert payload == {"brand": "Nelson"}
        assert "condition" not in payload  # default dropped

    def test_non_default_condition_persists(self):
        attrs = ProductSocialAttributes(condition="used")
        assert attrs.to_metadata() == {"condition": "used"}

    def test_from_metadata_ignores_foreign_keys(self):
        metadata = {"fiscal": {"profile": "own"}, "gallery": ["x"], "social": {"brand": "N"}}
        attrs = get_social_attributes_from(metadata)
        assert attrs.brand == "N"

    def test_set_preserves_sibling_metadata_keys(self):
        metadata = {"fiscal": {"profile": "own"}, "gallery": ["x"]}
        out = set_social_attributes(metadata, ProductSocialAttributes(brand="N"))
        assert out["fiscal"] == {"profile": "own"}
        assert out["gallery"] == ["x"]
        assert out["social"] == {"brand": "N"}

    def test_clearing_removes_social_key(self):
        metadata = {"social": {"brand": "N"}, "fiscal": {"profile": "own"}}
        out = set_social_attributes(metadata, ProductSocialAttributes())
        assert "social" not in out
        assert out["fiscal"] == {"profile": "own"}


class TestHashtagNormalization:
    def test_string_input_splits(self):
        attrs = ProductSocialAttributes(hashtags="#pão, artesanal  #forno")
        assert attrs.hashtags == ["pão", "artesanal", "forno"]

    def test_list_input_strips_hashes_and_dedupes(self):
        attrs = ProductSocialAttributes(hashtags=["#pão", "pão", " forno "])
        assert attrs.hashtags == ["pão", "forno"]

    def test_empty_hashtags_omitted(self):
        assert ProductSocialAttributes(hashtags="  ,  ").to_metadata() == {}


class TestValidation:
    def test_valid_gtin13(self):
        # 4006381333931 is a canonical valid EAN-13.
        assert ProductSocialAttributes(gtin="4006381333931").errors() == []

    def test_invalid_gtin_checksum(self):
        errs = ProductSocialAttributes(gtin="4006381333930").errors()
        assert any("GTIN" in e for e in errs)

    def test_invalid_gtin_length(self):
        assert any("GTIN" in e for e in ProductSocialAttributes(gtin="123").errors())

    def test_empty_gtin_is_valid(self):
        assert ProductSocialAttributes(gtin="").errors() == []

    def test_invalid_condition(self):
        assert any("Condição" in e for e in ProductSocialAttributes(condition="broken").errors())

    def test_google_category_numeric_ok(self):
        assert ProductSocialAttributes(google_product_category="2271").errors() == []

    def test_google_category_path_ok(self):
        cat = "Food, Beverages & Tobacco > Food Items > Bakery"
        assert ProductSocialAttributes(google_product_category=cat).errors() == []

    def test_google_category_empty_segment_flagged(self):
        assert any(
            "Categoria Google" in e
            for e in ProductSocialAttributes(google_product_category="A >  > C").errors()
        )


class TestHelpers:
    def test_get_from_object_with_metadata(self):
        class FakeProduct:
            metadata = {"social": {"brand": "Nelson"}}

        assert get_social_attributes(FakeProduct()).brand == "Nelson"

    def test_get_from_none_metadata(self):
        class FakeProduct:
            metadata = None

        assert get_social_attributes(FakeProduct()) == ProductSocialAttributes()


def get_social_attributes_from(metadata: dict) -> ProductSocialAttributes:
    return ProductSocialAttributes.from_metadata(metadata)
