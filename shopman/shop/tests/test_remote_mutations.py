from __future__ import annotations

from types import SimpleNamespace

import pytest

from shopman.shop.services import remote_mutations

pytestmark = pytest.mark.django_db


def test_run_idempotent_mutation_replays_cached_response():
    calls = 0

    def execute():
        nonlocal calls
        calls += 1
        return {"ok": True, "calls": calls}, 200

    first = remote_mutations.run_idempotent_mutation(
        scope="remote-test",
        key="same-key",
        execute=execute,
    )
    second = remote_mutations.run_idempotent_mutation(
        scope="remote-test",
        key="same-key",
        execute=execute,
    )

    assert first.response_body == {"ok": True, "calls": 1}
    assert first.replayed is False
    assert second.response_body == {"ok": True, "calls": 1}
    assert second.replayed is True
    assert calls == 1


def test_idempotency_key_from_request_prefers_header_then_body_then_fallback():
    header_request = SimpleNamespace(
        headers={"Idempotency-Key": "header-key"},
        data={"idempotency_key": "body-key"},
    )
    body_request = SimpleNamespace(headers={}, data={"idempotency_key": "body-key"})
    fallback_request = SimpleNamespace(headers={}, data={})

    assert remote_mutations.idempotency_key_from_request(header_request, fallback="fallback") == "header-key"
    assert remote_mutations.idempotency_key_from_request(body_request, fallback="fallback") == "body-key"
    assert remote_mutations.idempotency_key_from_request(fallback_request, fallback="fallback") == "fallback"


def test_run_idempotent_mutation_can_skip_caching_precondition_failures():
    calls = 0

    def execute():
        nonlocal calls
        calls += 1
        return {"ok": False, "calls": calls}, 409

    first = remote_mutations.run_idempotent_mutation(
        scope="remote-test-no-cache",
        key="same-key",
        execute=execute,
        cache_response=lambda _body, code: code < 400,
    )
    second = remote_mutations.run_idempotent_mutation(
        scope="remote-test-no-cache",
        key="same-key",
        execute=execute,
        cache_response=lambda _body, code: code < 400,
    )

    assert first.response_body == {"ok": False, "calls": 1}
    assert second.response_body == {"ok": False, "calls": 2}
    assert second.replayed is False
    assert calls == 2


def test_idempotency_key_from_request_hashes_overlong_values():
    request = SimpleNamespace(headers={"Idempotency-Key": "x" * 200}, data={})

    key = remote_mutations.idempotency_key_from_request(request, fallback="fallback")

    assert key.startswith("sha256:")
    assert len(key) <= 128
