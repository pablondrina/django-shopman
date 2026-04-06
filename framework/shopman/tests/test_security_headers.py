"""WP-C4: Security header tests — CSP, X-Frame-Options, nosniff, Referrer-Policy."""

from __future__ import annotations

import pytest

# Use /menu/ — a storefront page that does not override X-Frame-Options.
# (The home view intentionally sets SAMEORIGIN via @xframe_options_sameorigin for admin embed.)
PROBE_URL = "/menu/"


@pytest.fixture
def response(client, db):
    return client.get(PROBE_URL)


class TestSecurityHeaders:
    """HTTP security headers are present on storefront responses."""

    def test_csp_header_present(self, response):
        """Content-Security-Policy header must be set."""
        assert "Content-Security-Policy" in response, (
            "Content-Security-Policy header is missing — check CSPMiddleware is loaded."
        )

    def test_x_frame_options_deny(self, response):
        """X-Frame-Options must be DENY (prevents clickjacking)."""
        assert response.get("X-Frame-Options") == "DENY", (
            f"Expected X-Frame-Options: DENY, got: {response.get('X-Frame-Options')!r}"
        )

    def test_nosniff_header(self, response):
        """X-Content-Type-Options must be nosniff (prevents MIME sniffing)."""
        assert response.get("X-Content-Type-Options") == "nosniff", (
            f"Expected X-Content-Type-Options: nosniff, got: {response.get('X-Content-Type-Options')!r}"
        )

    def test_referrer_policy(self, response):
        """Referrer-Policy header must be present."""
        assert response.get("Referrer-Policy") == "strict-origin-when-cross-origin", (
            f"Expected strict-origin-when-cross-origin, got: {response.get('Referrer-Policy')!r}"
        )
