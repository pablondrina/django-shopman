"""Category 5 (follow-up) — the rate-limit client-IP key is proxy-depth aware.

Empirically, behind DO App Platform the RIGHTMOST X-Forwarded-For entry rotates
across ingress nodes, so a fixed ``TRUSTED_PROXY_DEPTH=1`` scatters one client
across many rate-limit buckets and dilutes every per-IP limit. The remediation
is to select the correct entry by depth; these tests lock that the depth knob
actually picks the intended entry, so once the real XFF shape is known the fix
is a single ``DOORMAN_TRUSTED_PROXY_DEPTH`` config change.
"""
from __future__ import annotations

import pytest
from django.test import RequestFactory
from shopman.doorman.utils import get_client_ip

pytestmark = pytest.mark.django_db


def _req(xff: str, remote: str = "10.0.0.1"):
    return RequestFactory().get("/", HTTP_X_FORWARDED_FOR=xff, REMOTE_ADDR=remote)


def test_depth_selects_nth_from_right():
    """XFF = 'client, hop1, hop2'. depth N picks the N-th entry from the right,
    so the correct depth isolates the real client regardless of how many proxy
    hops the platform appends."""
    xff = "203.0.113.9, 172.16.0.1, 172.16.0.2"
    assert get_client_ip(_req(xff), 1) == "172.16.0.2"  # rightmost hop
    assert get_client_ip(_req(xff), 2) == "172.16.0.1"
    assert get_client_ip(_req(xff), 3) == "203.0.113.9"  # the real client


def test_depth_clamps_and_falls_back():
    """A depth deeper than the chain clamps to the leftmost entry rather than
    indexing out of range, and REMOTE_ADDR is used only when no XFF is present."""
    assert get_client_ip(_req("203.0.113.9"), 5) == "203.0.113.9"
    no_xff = RequestFactory().get("/", REMOTE_ADDR="198.51.100.7")
    assert get_client_ip(no_xff, 1) == "198.51.100.7"


def test_client_ip_wrapper_reads_configured_depth(settings):
    """The app-level ``client_ip`` honors the configured depth so a deployment
    can correct for its proxy topology without a code change (doorman settings
    are re-read live, so ``DOORMAN_TRUSTED_PROXY_DEPTH`` takes effect at runtime)."""
    from shopman.shop.services.auth import client_ip

    settings.DOORMAN = {**getattr(settings, "DOORMAN", {}), "TRUSTED_PROXY_DEPTH": 2}
    resolved = client_ip(_req("203.0.113.9, 172.16.0.1, 172.16.0.2"))
    assert resolved == "172.16.0.1"  # depth=2 → 2nd from the right
