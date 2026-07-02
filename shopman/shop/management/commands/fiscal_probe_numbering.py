"""Sondagem de numeração NFC-e por série — resolve o limbo de migração.

Ao migrar de sistema, ninguém consegue "cravar" o último número emitido de uma
série; a numeração automática (painel Focus) exige exatamente esse dado. Este
comando descobre a fronteira EMITINDO sondas com ``numero`` explícito:

- SEFAZ rejeita por **duplicidade** → número já usado. Rejeição não consome
  número nem cria documento — custo ZERO. Avança para o próximo.
- SEFAZ **autoriza** → achamos o primeiro número livre. A sonda é cancelada na
  sequência (janela de 30 min) — consome exatamente 1 número, o custo aceito.

Uso (o operador informa a série e o palpite dos últimos relatórios):

    python manage.py fiscal_probe_numbering --serie 1 --start 4800
    python manage.py fiscal_probe_numbering --serie 1 --start 4800 --max-probes 50

O passo é linear (palpite costuma errar por pouco); ``--max-probes`` é o teto.
Em produção, rodar com a loja FECHADA (a sonda autorizada e cancelada é um
documento fiscal real; o cancelamento a neutraliza).
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)

PROBE_ITEM = {
    "sku": "SONDA-NUMERACAO",
    "name": "Sonda de numeracao (cancelar)",
    "qty": "1",
    "unit": "UN",
    "unit_price_q": 10,
    "total_q": 10,
    # Pao (producao propria) — NCM valido para o CNPJ da padaria.
    "fiscal": {
        "ncm": "19059090", "cfop": "5102", "unit": "UN", "icms_origem": "0",
        "icms_situacao_tributaria": "102",
        "pis_situacao_tributaria": "99", "cofins_situacao_tributaria": "99",
    },
}

_DUPLICITY_MARKERS = ("duplicidade", "539")


class Command(BaseCommand):
    help = "Descobre o próximo número NFC-e livre de uma série emitindo sondas (duplicidade = grátis)."

    def add_arguments(self, parser):
        parser.add_argument("--serie", required=True, help="Série NFC-e a sondar (ex.: 1).")
        parser.add_argument("--start", type=int, required=True, help="Número inicial (palpite dos relatórios).")
        parser.add_argument("--max-probes", type=int, default=30, help="Máximo de tentativas (default 30).")
        parser.add_argument(
            "--gallop",
            action="store_true",
            help=(
                "Palpite distante: dobra o passo em duplicidades consecutivas e fecha com "
                "busca binária. Cada número LIVRE testado autoriza+cancela uma nota — "
                "grátis em homologação; em produção prefira o linear com palpite bom."
            ),
        )

    def handle(self, *args, **options):
        from shopman.shop.adapters import fiscal_focusnfe as focus

        config = focus._get_config()
        missing = focus._missing_config(config)
        if missing:
            raise CommandError(f"Focus NFe sem configuração: {', '.join(missing)}")

        env = config.get("environment") or "homologacao"
        serie = str(options["serie"]).strip()
        number = int(options["start"])
        max_probes = max(1, int(options["max_probes"]))

        self.stdout.write(f"Ambiente: {env} | série {serie} | sondando a partir de {number}")
        if number < 1:
            raise CommandError("--start deve ser >= 1")

        self._focus = focus
        self._config = config
        self._backend = focus.FocusNFeBackend()
        self._serie = serie
        self._probes = 0
        self._max_probes = max_probes
        self._cancelled: list[int] = []

        gallop = bool(options["gallop"])
        last_used = None  # maior número CONFIRMADO usado (legado)
        step = 1
        consecutive_used = 0

        # Fase 1 — avanço: duplicidade é grátis; passo dobra no modo gallop.
        while True:
            free = self._probe(number)
            if free:
                first_free = number
                break
            last_used = number
            consecutive_used += 1
            if gallop and consecutive_used >= 4:
                step = min(step * 2, 512)
            number += step

        # Fase 2 — gallop pulou? Busca binária fecha a fronteira exata.
        if last_used is not None and first_free - last_used > 1:
            lo, hi = last_used, first_free
            while hi - lo > 1 and self._probes < self._max_probes:
                mid = (lo + hi) // 2
                if self._probe(mid):
                    hi = mid
                else:
                    lo = mid
            last_used = lo

        consumed_max = max(self._cancelled) if self._cancelled else last_used or 0
        next_free = consumed_max + 1
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"RESULTADO — série {serie}: último número USADO (legado) = "
            f"{last_used if last_used is not None else f'< {options['start']} (nenhum usado a partir do palpite)'}"
        ))
        if self._cancelled:
            self.stdout.write(
                f"Sondas autorizadas e CANCELADAS (números consumidos): {sorted(self._cancelled)}"
            )
        self.stdout.write(self.style.SUCCESS(
            f"→ Configure a série {serie} para iniciar em {next_free} "
            "(painel Focus → numeração; ou emita com numero explícito)."
        ))
        if last_used is not None and next_free - last_used > 2:
            self.stdout.write(
                f"→ Buraco {last_used + 1}–{next_free - 1} nunca emitido (exceto sondas canceladas): "
                "se o contador pedir, inutilize a faixa (endpoint de inutilização da Focus)."
            )

    def _probe(self, number: int) -> bool:
        """Emite sonda no nº; True se estava LIVRE (autorizada e cancelada)."""
        if self._probes >= self._max_probes:
            raise CommandError(
                f"Teto de {self._max_probes} sondas atingido — rode de novo a partir de {number} "
                "ou aumente --max-probes."
            )
        self._probes += 1
        probe_ref = f"PROBE-S{self._serie}-N{number}"
        result = self._emit_probe(self._focus, self._config, probe_ref, self._serie, number)

        if result.success:
            self.stdout.write(self.style.SUCCESS(f"  nº {number}: LIVRE (sonda autorizada)"))
            cancel = self._backend.cancel(
                reference=probe_ref,
                reason="Sonda de numeracao em migracao de sistema - documento sem circulacao",
            )
            if cancel.success:
                self._cancelled.append(number)
                self.stdout.write(f"  nº {number}: sonda cancelada (protocolo {cancel.protocol_number}).")
            else:
                self.stderr.write(self.style.ERROR(
                    f"  ⚠ CANCELAR MANUALMENTE a sonda {probe_ref}: {cancel.error_message}"
                ))
                self._cancelled.append(number)
            return True

        message = str(result.error_message or "").lower()
        if any(marker in message for marker in _DUPLICITY_MARKERS):
            self.stdout.write(f"  nº {number}: usado (duplicidade — custo zero)")
            return False

        raise CommandError(
            f"Sonda nº {number} rejeitada por outro motivo ({result.error_code}): {result.error_message}"
        )

    @staticmethod
    def _emit_probe(focus, config, probe_ref: str, serie: str, number: int):
        """Emite a sonda com numero/serie EXPLÍCITOS (bypass da numeração automática)."""
        payload = focus._build_nfce_payload(
            config=config,
            reference=probe_ref,
            items=[dict(PROBE_ITEM)],
            customer={},
            payment={"method": "cash", "amount_q": PROBE_ITEM["total_q"]},
            additional_info="SONDA DE NUMERACAO - MIGRACAO DE SISTEMA",
        )
        payload["serie"] = serie
        payload["numero"] = str(number)
        try:
            response = focus._request("POST", focus._nfce_path(probe_ref, config), payload, config)
        except Exception as exc:  # HTTPError 422 etc. viram resultado estruturado
            logger.warning("fiscal_probe: request falhou ref=%s: %s", probe_ref, exc)
            return focus._document_error_result(exc)
        return focus._document_result(response, config)
