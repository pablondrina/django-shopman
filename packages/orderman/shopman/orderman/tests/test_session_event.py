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

    def test_emit_recovers_from_seq_collision(self) -> None:
        """Emissão concorrente colide no unique (session_key, seq): o retry recalcula
        MAX+1 e sucede, em vez de estourar 500 (o select_for_update sobre aggregate
        não travava nada — o Django o remove).
        """
        session = self._session()
        session.emit_event("e0", actor="op")  # seq 0
        session.emit_event("e1", actor="op")  # seq 1 (MAX=1)

        real_create = SessionEvent.objects.create
        state = {"failed": False}

        def flaky_create(**kwargs):
            # 1ª chamada: simula outro emissor tendo tomado este seq (IntegrityError),
            # sem inserir (o insert real seria revertido junto com o savepoint).
            if not state["failed"]:
                state["failed"] = True
                raise IntegrityError("simulated concurrent seq collision")
            return real_create(**kwargs)

        with patch.object(SessionEvent.objects, "create", side_effect=flaky_create):
            ev = session.emit_event("e2", actor="op")

        # Recomputou MAX(=1)+1 = 2, sem duplicar nem pular.
        self.assertEqual(ev.seq, 2)
        self.assertEqual(
            list(
                SessionEvent.objects.filter(session_key=session.session_key)
                .order_by("seq")
                .values_list("seq", flat=True)
            ),
            [0, 1, 2],
        )

    def test_emit_reraises_after_exhausting_retries(self) -> None:
        """Colisão persistente (bug real, não corrida) ainda propaga — não mascara."""
        session = self._session()

        with patch.object(
            SessionEvent.objects, "create", side_effect=IntegrityError("boom")
        ):
            with self.assertRaises(IntegrityError):
                session.emit_event("x", actor="op")

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
