"""
Management command: sweep_orphan_holds

Backstop de higiene para holds INDEFINIDOS (``expires_at IS NULL`` — holds
planejados/demanda do AVAILABILITY-PLAN §8). Eles nunca caem no
``release_expired``; se o dono morre sem liberar, seguram o plano do dia para
sempre — o "fantasma" do WP-A do AVAILABILITY-SALE-PRODUCTION-PLAN. O caminho
normal de liberação é a morte da sessão (``abandon_session``,
``assign_phone_handle``, ``cleanup_stale_sessions``); esta varredura pega o
que escapar (crash entre abandono e release, deletes manuais, legado).

Libera, com alerta de operador (o plano do dia foi devolvido — a operação
precisa saber):

1. Hold indefinido cuja ``metadata.reference`` é uma session key SEM Session
   aberta (inexistente, abandonada ou committed — pós-commit os holds adotados
   são re-tagueados para ``order:<ref>`` e os restantes liberados; sobrar
   referência de sessão morta é vazamento).
2. Hold indefinido com ``target_date`` no passado: a fornada daquele dia já
   aconteceu (ou não); a reserva não promete mais nada.

NUNCA toca holds de produção (``metadata.purpose == "workorder"``) nem holds
adotados por pedido (``reference`` com prefixo ``order:``) — nem mesmo pela
regra de data passada: o dono é o pedido e pedido travado é problema do
``sweep_stuck_orders``. Hold manual sem referência (decisão do operador) só
cai pela regra de data passada.

Idempotente: cada hold é liberado uma única vez.

Usage::

    python manage.py sweep_orphan_holds
    python manage.py sweep_orphan_holds --dry-run
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Libera holds indefinidos órfãos (sem sessão viva ou com data passada) com alerta."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Lista os holds candidatos sem liberar.",
        )

    def handle(self, *args, **options):
        from shopman.orderman.models import Session
        from shopman.stockman import Hold, HoldStatus
        from shopman.stockman.service import Stock as stock

        dry_run = options["dry_run"]
        today = timezone.localdate()

        candidates = Hold.objects.filter(
            status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
            expires_at__isnull=True,
        ).order_by("pk")

        open_session_keys = set(
            Session.objects.filter(state="open").values_list("session_key", flat=True)
        )

        orphans: list[tuple[Hold, str]] = []
        for hold in candidates:
            # Reserva de produção (insumos de WorkOrder) não é desta varredura.
            # Filtro em Python: excluir por chave JSON ausente descartaria
            # holds sem ``purpose`` no queryset.
            if (hold.metadata or {}).get("purpose") == "workorder":
                continue
            reference = str((hold.metadata or {}).get("reference") or "")
            # Hold de PEDIDO nunca é desta varredura (nem por data passada):
            # o dono é o pedido, o ciclo termina por fulfill/release/cancel, e
            # pedido travado é problema do sweep_stuck_orders — liberar aqui
            # faria o fulfill tardio falhar por baixo dos panos.
            if reference.startswith("order:"):
                continue
            if hold.target_date and hold.target_date < today:
                orphans.append((hold, "data passada"))
                continue
            if not reference:
                # Sem referência rastreável (hold manual do operador): decisão
                # humana, não órfão — só a regra de data passada se aplica.
                continue
            if reference not in open_session_keys:
                orphans.append((hold, "sessão morta"))

        if not orphans:
            self.stdout.write("Nenhum hold órfão encontrado.")
            return

        if dry_run:
            for hold, why in orphans:
                self.stdout.write(f"[dry-run] {hold.hold_id} {hold.quantity}x {hold.sku} ({why})")
            self.stdout.write(f"[dry-run] {len(orphans)} hold(s) seriam liberados.")
            return

        released: list[tuple[Hold, str]] = []
        for hold, why in orphans:
            try:
                stock.release(hold.hold_id, reason=f"Órfão liberado pela varredura ({why})")
                released.append((hold, why))
            except Exception:
                logger.warning("sweep_orphan_holds: release falhou %s", hold.hold_id, exc_info=True)

        if released:
            from shopman.shop.services.observability import create_operator_alert

            summary = ", ".join(
                f"{hold.quantity:g}x {hold.sku}" for hold, _ in released[:8]
            )
            if len(released) > 8:
                summary += f" (+{len(released) - 8})"
            create_operator_alert(
                type="orphan_holds_released",
                severity="warning",
                message=(
                    f"{len(released)} reserva(s) órfã(s) devolvida(s) ao estoque/plano: "
                    f"{summary}. A disponibilidade da vitrine aumentou."
                ),
                dedupe_key="orphan_holds:" + ",".join(str(h.pk) for h, _ in released),
            )

        logger.info("sweep_orphan_holds: released %d holds", len(released))
        self.stdout.write(self.style.SUCCESS(f"{len(released)} hold(s) órfão(s) liberado(s)."))
