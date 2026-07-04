"""SessionEvent — append-only audit log anchored on session_key."""

from __future__ import annotations

from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase
from shopman.orderman.models import Session, SessionEvent


class SessionEventTests(TestCase):
    def _session(self, key: str = "S-AUDIT-1") -> Session:
        return Session.objects.create(session_key=key, channel_ref="pos")

    def test_emit_appends_with_monotonic_seq(self) -> None:
        session = self._session()
        e0 = session.emit_event("line_added", actor="op1", payload={"sku": "PAO"})
        e1 = session.emit_event(
            "line_removed", actor="op1", payload={"sku": "PAO", "qty_before": 3, "qty_after": 0}
        )
        self.assertEqual((e0.seq, e1.seq), (0, 1))
        self.assertEqual(e0.session_key, "S-AUDIT-1")
        self.assertEqual(
            list(SessionEvent.objects.filter(session_key="S-AUDIT-1").values_list("type", flat=True)),
            ["line_added", "line_removed"],
        )

    def test_emit_recovers_from_real_seq_collision(self) -> None:
        """Colisão REAL no unique (session_key, seq): o retry recalcula MAX+1 e sucede.

        Simula a corrida forçando o helper a computar um seq que JÁ existe (aggregate
        stale na 1ª tentativa) → o create bate no unique de verdade → o retry
        recomputa e sucede. Sem o retry, seria 500.
        """
        from django.db.models import QuerySet

        session = self._session()
        session.emit_event("e0", actor="op")  # seq 0 real

        real_aggregate = QuerySet.aggregate
        state = {"n": 0}

        def stale_once(self_qs, *a, **k):
            state["n"] += 1
            if state["n"] == 1:
                return {"m": -1}  # stale → força seq=0, que já existe
            return real_aggregate(self_qs, *a, **k)

        with patch.object(QuerySet, "aggregate", autospec=True, side_effect=stale_once):
            ev = session.emit_event("e1", actor="op")

        # 1ª tentativa: seq=0 colide (IntegrityError real) → exists(0)=True → retry
        # → MAX=0 → seq=1.
        self.assertEqual(ev.seq, 1)
        self.assertEqual(
            list(
                SessionEvent.objects.filter(session_key=session.session_key)
                .order_by("seq")
                .values_list("seq", flat=True)
            ),
            [0, 1],
        )

    def test_non_seq_integrity_error_reraises_immediately(self) -> None:
        """Erro que NÃO é colisão de seq (outra constraint) re-levanta na 1ª tentativa,
        sem gastar 6 tentativas nem mascarar o erro real."""
        session = self._session()
        calls = {"n": 0}

        def bad_create(**kwargs):
            calls["n"] += 1
            raise IntegrityError("violação de outra constraint (não seq)")

        with patch.object(SessionEvent.objects, "create", side_effect=bad_create):
            with self.assertRaises(IntegrityError):
                session.emit_event("x", actor="op")

        # Nada foi inserido → exists(seq) é False → re-levanta já (não 6×).
        self.assertEqual(calls["n"], 1)

    def test_seq_is_independent_per_session_key(self) -> None:
        a = self._session("S-A")
        b = self._session("S-B")
        a.emit_event("x", actor="op")
        eb = b.emit_event("y", actor="op")
        self.assertEqual(eb.seq, 0)

    def test_payload_and_actor_preserved(self) -> None:
        session = self._session()
        event = session.emit_event(
            "discount_applied", actor="gerente", payload={"value": 10, "reason": "cortesia", "approved_by": "mgr"}
        )
        event.refresh_from_db()
        self.assertEqual(event.actor, "gerente")
        self.assertEqual(event.payload["approved_by"], "mgr")

    def test_trail_survives_session_deletion(self) -> None:
        # Anti-fraud invariant: anchored on session_key (no FK), so clearing or
        # deleting the session does NOT cascade-wipe the evidence of a removal.
        session = self._session("S-DEL")
        session.emit_event("line_removed", actor="op", payload={"sku": "X"})
        session.delete()
        self.assertEqual(SessionEvent.objects.filter(session_key="S-DEL").count(), 1)
