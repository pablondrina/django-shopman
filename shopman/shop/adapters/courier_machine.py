"""
Machine courier adapter — despacho de entregadores via API da Machine (Gaudium).

A Machine (api.taximachine.com.br) é a plataforma por trás da central de
entregas usada pelo estabelecimento. Este adapter é a ÚNICA borda HTTP com a
Machine: dinheiro entra/sai daqui já convertido para centavos (`_q`) — a API
fala float em reais (`estimativa_valor`, `final_value`) e nenhum float de
dinheiro cruza esta borda.

Auth: HTTP Basic (usuário de integração) + header `api-key`. Permissão
"API - Entrega" no usuário. Config em settings.SHOPMAN_MACHINE.

Status de solicitação (letra crua; labels só na projection):
  D distribuindo · G aguardando aceite · P pendente · A aceita · S em espera ·
  E em andamento (coletou) · F finalizada · N não atendida · C cancelada ·
  U agrupada. Terminais: F, N, C.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

#: Letras de status terminais — a corrida não muda mais depois delas.
TERMINAL_STATUSES = frozenset({"F", "N", "C"})

#: Fases em que a corrida ainda pode ser cancelada (antes da coleta).
CANCELLABLE_STATUSES = frozenset({"D", "G", "P", "A", "S"})


class CourierError(Exception):
    """Falha na chamada à Machine.

    ``transient=True`` (timeout, rede, 5xx) → o chamador pode re-tentar
    (Directive re-agenda). ``transient=False`` (4xx) → erro de dados/config,
    re-tentar não resolve.
    """

    def __init__(self, message: str, *, transient: bool):
        super().__init__(message)
        self.transient = transient


@dataclass(frozen=True)
class CourierEstimate:
    value_q: int
    minutes: float
    km: float


@dataclass(frozen=True)
class CourierDispatchResult:
    courier_ref: str
    inert: bool = False


def _cfg() -> dict:
    return getattr(settings, "SHOPMAN_MACHINE", {}) or {}


def _base_url() -> str:
    return str(_cfg().get("base_url") or "https://api.taximachine.com.br/api/integracao").rstrip("/")


def _details_base() -> str:
    return str(_cfg().get("details_base") or "https://api.taximachine.com.br/integracao/v1").rstrip("/")


def _to_q(value) -> int:
    """Converte valor decimal em reais (float da API) para centavos int."""
    try:
        return int(round(float(value) * 100))
    except (TypeError, ValueError):
        return 0


def _inert() -> bool:
    from ._external import inert

    if inert("SHOPMAN_MACHINE_ALLOW_IN_DEBUG"):
        logger.info("Machine externo inerte (trava dev/seed)")
        return True
    return False


def is_configured() -> bool:
    cfg = _cfg()
    return bool(cfg.get("username") and cfg.get("password") and cfg.get("api_key"))


def _request(method: str, path: str, *, base: str | None = None, params: dict | None = None,
             json_body: dict | None = None) -> dict:
    """Chamada autenticada à Machine. Retorna o dict `response` do envelope.

    Envelope da API: `{"success": true, "response": {...}}` ou
    `{"success": false, "errors": [{code, message}]}`.
    """
    cfg = _cfg()
    if not is_configured():
        raise CourierError("Machine não configurada (username/password/api_key)", transient=False)

    url = f"{base or _base_url()}{path}"
    try:
        resp = requests.request(
            method,
            url,
            params=params,
            json=json_body,
            auth=(cfg["username"], cfg["password"]),
            headers={"api-key": cfg["api_key"]},
            timeout=int(cfg.get("timeout") or 15),
        )
    except requests.RequestException as exc:
        raise CourierError(f"Machine indisponível: {exc}", transient=True) from exc

    if resp.status_code >= 500:
        raise CourierError(
            f"Machine HTTP {resp.status_code}: {resp.text[:200]}", transient=True
        )

    try:
        payload = resp.json()
    except ValueError as exc:
        raise CourierError(
            f"Machine HTTP {resp.status_code}: resposta não-JSON: {resp.text[:200]}",
            transient=resp.status_code >= 500,
        ) from exc

    # O endpoint de detalhes (/integracao/v1) responde o objeto direto, sem envelope.
    if "success" not in payload:
        if resp.status_code >= 400:
            raise CourierError(
                f"Machine HTTP {resp.status_code}: {resp.text[:200]}", transient=False
            )
        return payload

    if not payload.get("success"):
        errors = payload.get("errors") or []
        detail = "; ".join(
            f"[{e.get('code')}] {e.get('message')}" for e in errors if isinstance(e, dict)
        ) or resp.text[:200]
        raise CourierError(f"Machine recusou ({resp.status_code}): {detail}", transient=False)

    response = payload.get("response")
    return response if isinstance(response, (dict, list)) else {}


def estimate(*, pickup: dict, dropoff: dict) -> CourierEstimate | None:
    """Cota a corrida (GET /estimarSolicitacao) por coordenadas.

    ``pickup``/``dropoff``: dicts com ``lat``/``lng``. Retorna None quando
    inerte ou sem coordenadas — a cotação é sempre best-effort.
    """
    if _inert():
        return None
    if not all([pickup.get("lat"), pickup.get("lng"), dropoff.get("lat"), dropoff.get("lng")]):
        return None
    response = _request(
        "GET",
        "/estimarSolicitacao",
        params={
            "lat_partida": pickup["lat"],
            "lng_partida": pickup["lng"],
            "lat_desejado": dropoff["lat"],
            "lng_desejado": dropoff["lng"],
        },
    )
    return CourierEstimate(
        value_q=_to_q(response.get("estimativa_valor")),
        minutes=float(response.get("estimativa_minutos") or 0),
        km=float(response.get("estimativa_km") or 0),
    )


def dispatch(payload: dict) -> CourierDispatchResult:
    """Abre a corrida (POST /abrirSolicitacao). Retorna o ``id_mch``.

    ``payload`` é o corpo pronto da Machine (montado por
    ``shopman.shop.services.courier.build_machine_payload``).
    """
    if _inert():
        return CourierDispatchResult(courier_ref="", inert=True)
    response = _request("POST", "/abrirSolicitacao", json_body=payload)
    courier_ref = str(response.get("id_mch") or "")
    if not courier_ref:
        raise CourierError("Machine abriu a solicitação mas não devolveu id_mch", transient=False)
    return CourierDispatchResult(courier_ref=courier_ref)


def get_status(courier_ref: str) -> str:
    """Status atual da corrida (GET /solicitacaoStatus) — letra crua ("" se inerte)."""
    if _inert():
        return ""
    response = _request("GET", "/solicitacaoStatus", params={"id_mch": courier_ref})
    return str(response.get("status") or "")


def get_details(courier_ref: str) -> dict:
    """Detalhes da corrida (GET /integracao/v1/request/:id): driver, progress, finished."""
    if _inert():
        return {}
    return _request("GET", f"/request/{courier_ref}", base=_details_base())


def get_position(courier_ref: str) -> dict | None:
    """Posição do entregador (GET /posicaoCondutor). None fora da fase ativa."""
    if _inert():
        return None
    response = _request("GET", "/posicaoCondutor", params={"id_mch": courier_ref})
    lat, lng = response.get("lat_condutor"), response.get("lng_condutor")
    if lat is None or lng is None:
        return None
    return {"lat": float(lat), "lng": float(lng)}


def cancel(courier_ref: str, *, reason_id: int | None = None) -> bool:
    """Cancela a corrida (POST /cancelar). Só antes de F/N/C."""
    if _inert():
        return True
    _request(
        "POST",
        "/cancelar",
        json_body={
            "id_mch": courier_ref,
            "motivo_id": reason_id if reason_id is not None else int(_cfg().get("cancel_reason_id") or 1),
        },
    )
    return True


def tracking_links(courier_ref: str) -> list[dict]:
    """Links de rastreio por parada (GET /obterLinkRastreio/:id).

    Retorna ``[{parada_id, link_rastreio, codigo_confirmacao}]`` (lista vazia
    se inerte ou indisponível).
    """
    if _inert():
        return []
    response = _request("GET", f"/obterLinkRastreio/{courier_ref}")
    return response if isinstance(response, list) else []


def register_webhook(url: str, *, kind: str) -> bool:
    """Cadastra a URL de webhook na Machine (POST /cadastrarWebhook).

    ``kind``: "status" ou "posicao". Usado só na homologação, via
    ``manage.py machine_register_webhook``.
    """
    if kind not in ("status", "posicao"):
        raise ValueError(f"kind inválido: {kind!r} (use 'status' ou 'posicao')")
    _request(
        "POST",
        "/cadastrarWebhook",
        json_body={"tipo": kind, "url": url, "responsabilidade": "solicitante"},
    )
    return True
