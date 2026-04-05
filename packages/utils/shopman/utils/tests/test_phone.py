"""Tests for shopman.utils.phone — phone normalization via phonenumbers."""

from shopman.utils.phone import is_valid_phone, normalize_phone


class TestNormalizePhoneBrazilian:
    """Brazilian phone numbers."""

    def test_mobile_11_digits_no_prefix(self):
        """43984049009 → +5543984049009"""
        assert normalize_phone("43984049009") == "+5543984049009"

    def test_mobile_with_plus55(self):
        """+5543984049009 stays the same."""
        assert normalize_phone("+5543984049009") == "+5543984049009"

    def test_mobile_with_55_no_plus(self):
        """5543984049009 → +5543984049009"""
        assert normalize_phone("5543984049009") == "+5543984049009"

    def test_landline_10_digits(self):
        """4330281234 → +554330281234"""
        assert normalize_phone("4330281234") == "+554330281234"

    def test_landline_with_plus55(self):
        """+554330281234 stays the same."""
        assert normalize_phone("+554330281234") == "+554330281234"

    def test_sao_paulo_mobile(self):
        """11999887766 → +5511999887766"""
        assert normalize_phone("11999887766") == "+5511999887766"

    def test_with_formatting(self):
        """(43) 98404-9009 → +5543984049009"""
        assert normalize_phone("(43) 98404-9009") == "+5543984049009"

    def test_with_dashes(self):
        """43-98404-9009 → +5543984049009"""
        assert normalize_phone("43-98404-9009") == "+5543984049009"

    def test_ios_autofill_zero_ddd(self):
        """(043) 98404-9009 → +5543984049009 (iOS autofill adds zero to DDD)."""
        assert normalize_phone("(043) 98404-9009") == "+5543984049009"

    def test_ios_autofill_zero_ddd_same_as_without(self):
        """(043) and (43) must resolve to the same E.164 number."""
        assert normalize_phone("(043) 98404-9009") == normalize_phone("(43) 98404-9009")

    def test_zero_prefix_ddd_sao_paulo(self):
        """(011) 99988-7766 → +5511999887766"""
        assert normalize_phone("(011) 99988-7766") == "+5511999887766"

    def test_zero_prefix_ddd_rio(self):
        """(021) 99988-7766 → +5521999887766"""
        assert normalize_phone("(021) 99988-7766") == "+5521999887766"


class TestNormalizePhoneManychat:
    """Manychat bug: +DDD9XXXXXXXX missing country code 55."""

    def test_manychat_bug_detected(self):
        """+43984049009 → +5543984049009 (Manychat bug, not Austria)."""
        assert normalize_phone("+43984049009") == "+5543984049009"

    def test_manychat_bug_sao_paulo(self):
        """+11999887766 → +5511999887766"""
        assert normalize_phone("+11999887766") == "+5511999887766"

    def test_manychat_bug_rio(self):
        """+21999887766 → +5521999887766"""
        assert normalize_phone("+21999887766") == "+5521999887766"


class TestNormalizePhoneInternational:
    """International numbers."""

    def test_us_number(self):
        """+12025551234 stays the same."""
        result = normalize_phone("+12025551234")
        assert result == "+12025551234"

    def test_portugal(self):
        """+351912345678 stays the same."""
        result = normalize_phone("+351912345678")
        assert result == "+351912345678"

    def test_argentina(self):
        """+5491112345678"""
        result = normalize_phone("+5491112345678")
        assert result.startswith("+549")


class TestNormalizePhonePassthrough:
    """Non-phone values: email, instagram."""

    def test_email_lowercase(self):
        """Email is lowercased and returned as-is."""
        assert normalize_phone("John@Example.COM") == "john@example.com"

    def test_instagram_passthrough(self):
        """Instagram handle lowercased, @ stripped."""
        assert normalize_phone("@MyShop", contact_type="instagram") == "myshop"

    def test_instagram_no_at(self):
        assert normalize_phone("MyShop", contact_type="instagram") == "myshop"

    def test_empty_returns_empty(self):
        assert normalize_phone("") == ""

    def test_none_like_empty(self):
        assert normalize_phone("  ") == ""


class TestIsValidPhone:
    """is_valid_phone validation."""

    def test_valid_brazilian_mobile(self):
        assert is_valid_phone("+5543984049009") is True

    def test_valid_us(self):
        assert is_valid_phone("+12025551234") is True

    def test_email_not_valid(self):
        assert is_valid_phone("test@email.com") is False

    def test_empty_not_valid(self):
        assert is_valid_phone("") is False

    def test_too_short(self):
        assert is_valid_phone("123") is False
