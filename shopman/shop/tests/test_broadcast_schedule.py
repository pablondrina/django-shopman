"""Janela de publicação — a hora certa de falar com o cliente (F12).

O teste mais importante deste arquivo é o da config torta: janela quebrada
devolve ``None`` (publica agora). Marketing não pode virar gargalo da operação,
então na dúvida o post sai — nunca fica preso esperando uma janela que não
existe.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from django.utils import timezone

from shopman.shop.services import broadcast_schedule


def _at(*, hour: int, minute: int = 0, weekday: int | None = None) -> datetime:
    """Um instante local determinístico, opcionalmente num dia da semana dado."""
    now = timezone.localtime().replace(hour=hour, minute=minute, second=0, microsecond=0)
    if weekday is not None:
        now += timedelta(days=(weekday - now.weekday()) % 7)
    return now


MANHA = {"type": "preferred_hours", "windows": [["07:00", "11:00"]]}
DOIS_TURNOS = {
    "type": "preferred_hours",
    "windows": [["07:00", "11:00"], ["15:00", "18:00"]],
}


# ── Publica agora ────────────────────────────────────────────────────


class TestPublicaAgora:
    """``None`` é a resposta "pode sair na hora"."""

    @pytest.mark.parametrize(
        "schedule",
        [
            None,
            {},
            {"type": "immediate"},
            "nao-e-dict",
            {"type": "preferred_hours"},  # sem windows
            {"type": "preferred_hours", "windows": []},
        ],
        ids=["none", "vazio", "immediate", "nao-dict", "sem-windows", "windows-vazio"],
    )
    def test_config_ausente_ou_neutra_publica_agora(self, schedule):
        assert broadcast_schedule.next_publish_at(schedule, now=_at(hour=5)) is None

    def test_dentro_da_janela_publica_agora(self):
        assert broadcast_schedule.next_publish_at(MANHA, now=_at(hour=9)) is None

    def test_inicio_da_janela_esta_dentro(self):
        """Início é inclusivo: às 7h em ponto a janela já está aberta."""
        assert broadcast_schedule.next_publish_at(MANHA, now=_at(hour=7)) is None

    def test_fim_da_janela_esta_fora(self):
        """Fim é exclusivo: às 11h em ponto a janela já fechou."""
        assert broadcast_schedule.next_publish_at(MANHA, now=_at(hour=11)) is not None


# ── Agenda para a próxima abertura ───────────────────────────────────


class TestProximaAbertura:
    def test_antes_da_janela_espera_a_abertura_de_hoje(self):
        """Fornada das 5h30 não vira post às 5h30: espera as 7h."""
        agendado = broadcast_schedule.next_publish_at(MANHA, now=_at(hour=5, minute=30))
        assert (agendado.hour, agendado.minute) == (7, 0)
        assert agendado.date() == _at(hour=5).date()

    def test_entre_dois_turnos_pega_o_turno_seguinte(self):
        agendado = broadcast_schedule.next_publish_at(DOIS_TURNOS, now=_at(hour=12))
        assert (agendado.hour, agendado.minute) == (15, 0)

    def test_depois_do_ultimo_turno_vai_para_amanha(self):
        now = _at(hour=20)
        agendado = broadcast_schedule.next_publish_at(DOIS_TURNOS, now=now)
        assert (agendado.hour, agendado.minute) == (7, 0)
        assert agendado.date() == (now + timedelta(days=1)).date()

    def test_o_agendamento_e_timezone_aware(self):
        agendado = broadcast_schedule.next_publish_at(MANHA, now=_at(hour=5))
        assert timezone.is_aware(agendado)

    def test_janelas_fora_de_ordem_sao_normalizadas(self):
        """A config pode vir em qualquer ordem; a próxima abertura é a mais cedo."""
        embaralhado = {
            "type": "preferred_hours",
            "windows": [["15:00", "18:00"], ["07:00", "11:00"]],
        }
        agendado = broadcast_schedule.next_publish_at(embaralhado, now=_at(hour=5))
        assert agendado.hour == 7


# ── Dias da semana ───────────────────────────────────────────────────


class TestDiasDaSemana:
    def test_dia_nao_permitido_pula_para_o_proximo_liberado(self):
        """Domingo (6) fechado: um evento de domingo espera a segunda."""
        schedule = {**MANHA, "weekdays": [0]}  # só segunda
        domingo = _at(hour=9, weekday=6)

        agendado = broadcast_schedule.next_publish_at(schedule, now=domingo)

        assert agendado.weekday() == 0
        assert agendado.hour == 7

    def test_dia_permitido_e_dentro_da_janela_publica_agora(self):
        schedule = {**MANHA, "weekdays": [2]}  # quarta
        assert broadcast_schedule.next_publish_at(schedule, now=_at(hour=9, weekday=2)) is None

    @pytest.mark.parametrize(
        "weekdays", [None, [], ["nao-numero"], [99]], ids=["none", "vazio", "texto", "fora-range"]
    )
    def test_weekdays_invalido_libera_a_semana_toda(self, weekdays):
        """Config torta não pode prender o post: cai na semana inteira."""
        schedule = {**MANHA, "weekdays": weekdays}
        assert broadcast_schedule.next_publish_at(schedule, now=_at(hour=9)) is None


# ── Parsing tolerante ────────────────────────────────────────────────


class TestParsingTolerante:
    @pytest.mark.parametrize(
        "windows",
        [
            [["11:00", "07:00"]],  # fim antes do início
            [["07:00", "07:00"]],  # janela de duração zero
            [["07:00"]],  # par incompleto
            ["07:00-11:00"],  # não é par
            [["hora-errada", "11:00"]],
            [[None, None]],
        ],
        ids=["invertida", "vazia", "incompleta", "nao-par", "texto", "none"],
    )
    def test_janela_torta_e_ignorada_e_publica_agora(self, windows):
        schedule = {"type": "preferred_hours", "windows": windows}
        assert broadcast_schedule.next_publish_at(schedule, now=_at(hour=5)) is None

    def test_janela_boa_sobrevive_ao_lado_de_uma_torta(self):
        schedule = {
            "type": "preferred_hours",
            "windows": [["11:00", "07:00"], ["15:00", "18:00"]],
        }
        agendado = broadcast_schedule.next_publish_at(schedule, now=_at(hour=12))
        assert agendado.hour == 15

    def test_hora_sem_minutos_vale(self):
        schedule = {"type": "preferred_hours", "windows": [["7", "11"]]}
        assert broadcast_schedule.next_publish_at(schedule, now=_at(hour=9)) is None


# ── Descrição legível ────────────────────────────────────────────────


class TestDescribe:
    @pytest.mark.parametrize(
        "schedule",
        [None, {"type": "immediate"}, {"type": "preferred_hours", "windows": []}],
        ids=["none", "immediate", "sem-janela"],
    )
    def test_sem_janela_util_diz_publica_na_hora(self, schedule):
        assert broadcast_schedule.describe(schedule) == "publica na hora"

    def test_janela_unica(self):
        assert broadcast_schedule.describe(MANHA) == "publica entre 07:00 às 11:00"

    def test_duas_janelas(self):
        assert broadcast_schedule.describe(DOIS_TURNOS) == (
            "publica entre 07:00 às 11:00, 15:00 às 18:00"
        )

    def test_semana_toda_nao_lista_os_dias(self):
        """Sem restrição de dia, listar "seg, ter, qua…" só polui o card."""
        schedule = {**MANHA, "weekdays": [0, 1, 2, 3, 4, 5, 6]}
        assert broadcast_schedule.describe(schedule) == "publica entre 07:00 às 11:00"

    def test_dias_restritos_aparecem(self):
        schedule = {**MANHA, "weekdays": [0, 5]}
        assert broadcast_schedule.describe(schedule) == "publica entre 07:00 às 11:00 (seg, sáb)"
