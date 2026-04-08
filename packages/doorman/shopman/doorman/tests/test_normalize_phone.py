"""Tests for shopman.doorman.utils.normalize_phone and get_client_ip."""

import pytest

from shopman.doorman.utils import get_client_ip, normalize_phone


class TestNormalizePhone:
    """Edge cases for the unified normalize_phone function."""

    def test_empty_string(self):
        assert normalize_phone("") == ""

    def test_none_like(self):
        assert normalize_phone("   ") == ""

    def test_only_letters(self):
        assert normalize_phone("abcdef") == ""

    def test_brazilian_mobile_11_digits(self):
        """DDD + 9-digit mobile."""
        assert normalize_phone("41999887766") == "+5541999887766"

    def test_brazilian_landline_10_digits(self):
        """DDD + 8-digit landline."""
        assert normalize_phone("4133445566") == "+554133445566"

    def test_brazilian_with_country_code_13_digits(self):
        """55 + DDD + 9-digit mobile."""
        assert normalize_phone("5541999887766") == "+5541999887766"

    def test_brazilian_with_country_code_12_digits(self):
        """55 + DDD + 8-digit landline."""
        assert normalize_phone("554133445566") == "+554133445566"

    def test_with_plus_prefix(self):
        """Already in E.164 format."""
        assert normalize_phone("+5541999887766") == "+5541999887766"

    def test_formatted_brazilian(self):
        """Common formatted input."""
        assert normalize_phone("(41) 99988-7766") == "+5541999887766"

    def test_formatted_with_country_code(self):
        assert normalize_phone("+55 (41) 99988-7766") == "+5541999887766"

    def test_short_number(self):
        """Too short to be a valid phone."""
        assert normalize_phone("12345") == ""

    def test_email_lowercase(self):
        """Email should be lowercased."""
        assert normalize_phone("User@Example.COM") == "user@example.com"

    def test_email_with_spaces(self):
        assert normalize_phone("  user@example.com  ") == "user@example.com"

    def test_international_number(self):
        """Non-Brazilian international number."""
        assert normalize_phone("+14155551234") == "+14155551234"

    def test_dashes_and_dots(self):
        assert normalize_phone("41-9-9988-7766") == "+5541999887766"


class TestGetClientIp:
    """Tests for get_client_ip with configurable proxy depth."""

    def _make_request(self, xff=None, remote_addr="127.0.0.1"):
        class FakeRequest:
            META = {}
        req = FakeRequest()
        if xff:
            req.META["HTTP_X_FORWARDED_FOR"] = xff
        req.META["REMOTE_ADDR"] = remote_addr
        return req

    def test_no_xff_uses_remote_addr(self):
        req = self._make_request(remote_addr="10.0.0.1")
        assert get_client_ip(req) == "10.0.0.1"

    def test_xff_single_ip_depth_1(self):
        req = self._make_request(xff="203.0.113.50")
        assert get_client_ip(req, trusted_proxy_depth=1) == "203.0.113.50"

    def test_xff_multiple_ips_depth_1(self):
        """Depth 1: rightmost entry (direct client seen by proxy)."""
        req = self._make_request(xff="203.0.113.50, 70.41.3.18, 150.172.238.178")
        assert get_client_ip(req, trusted_proxy_depth=1) == "150.172.238.178"

    def test_xff_multiple_ips_depth_2(self):
        """Depth 2: second from right (CDN + proxy)."""
        req = self._make_request(xff="203.0.113.50, 70.41.3.18, 150.172.238.178")
        assert get_client_ip(req, trusted_proxy_depth=2) == "70.41.3.18"

    def test_xff_multiple_ips_depth_3(self):
        """Depth 3: original client."""
        req = self._make_request(xff="203.0.113.50, 70.41.3.18, 150.172.238.178")
        assert get_client_ip(req, trusted_proxy_depth=3) == "203.0.113.50"

    def test_xff_spoofed_depth_1(self):
        """Attacker can spoof first entry, but depth=1 reads last."""
        req = self._make_request(xff="1.2.3.4, 10.0.0.1")
        assert get_client_ip(req, trusted_proxy_depth=1) == "10.0.0.1"
