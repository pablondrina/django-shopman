"""
Mock courier adapter — dev e testes, sem rede.

Espelha a interface de :mod:`courier_machine`. O estado das corridas vive em
memória de processo e é controlável pelo teste/dev:

    from shopman.shop.adapters import courier_mock
    result = courier_mock.dispatch(payload)          # id determinístico
    courier_mock.set_status(result.courier_ref, "E") # simula coleta
    courier_mock.reset()                             # limpa entre testes
"""

from __future__ import annotations

from .courier_machine import (  # noqa: F401 — mesma semântica de status
    CANCELLABLE_STATUSES,
    TERMINAL_STATUSES,
    CourierDispatchResult,
    CourierError,
    CourierEstimate,
)

_rides: dict[str, dict] = {}
_counter = 0


def reset() -> None:
    global _counter
    _rides.clear()
    _counter = 0


def set_status(courier_ref: str, status: str) -> None:
    _rides.setdefault(courier_ref, {})["status"] = status


def set_driver(courier_ref: str, driver: dict) -> None:
    _rides.setdefault(courier_ref, {})["driver"] = driver


def rides() -> dict[str, dict]:
    """Estado interno (payloads despachados) — para asserts em testes."""
    return _rides


def is_configured() -> bool:
    return True


def estimate(*, pickup: dict, dropoff: dict) -> CourierEstimate | None:
    if not all([pickup.get("lat"), pickup.get("lng"), dropoff.get("lat"), dropoff.get("lng")]):
        return None
    return CourierEstimate(value_q=1250, minutes=18.0, km=4.2)


def dispatch(payload: dict) -> CourierDispatchResult:
    global _counter
    _counter += 1
    external = ""
    for parada in payload.get("paradas") or []:
        external = str(parada.get("id_externo") or "")
        if external:
            break
    courier_ref = f"MOCK-{external or _counter}"
    _rides[courier_ref] = {"status": "D", "payload": payload, "driver": None}
    return CourierDispatchResult(courier_ref=courier_ref)


def get_status(courier_ref: str) -> str:
    ride = _rides.get(courier_ref)
    if ride is None:
        raise CourierError("Solicitacao não encontrada.", transient=False)
    return ride.get("status") or "D"


def get_details(courier_ref: str) -> dict:
    ride = _rides.get(courier_ref) or {}
    driver = ride.get("driver") or {
        "name": "Entregador Mock",
        "phone": "(43) 99999-0000",
        "vehicle_plate": "MCK0A00",
        "vehicle_model": "Moto Mock",
    }
    return {"request_id": courier_ref, "driver": driver, "progress": {}, "finished": {}}


def get_position(courier_ref: str) -> dict | None:
    ride = _rides.get(courier_ref) or {}
    if ride.get("status") in ("A", "S", "E"):
        return {"lat": -23.3045, "lng": -51.1696}
    return None


def cancel(courier_ref: str, *, reason_id: int | None = None) -> bool:
    ride = _rides.get(courier_ref)
    if ride is None:
        raise CourierError("Solicitacao não encontrada.", transient=False)
    if ride.get("status") in TERMINAL_STATUSES:
        raise CourierError("Solicitação já finalizada/cancelada.", transient=False)
    ride["status"] = "C"
    return True


def tracking_links(courier_ref: str) -> list[dict]:
    if courier_ref not in _rides:
        return []
    return [
        {
            "parada_id": "1",
            "link_rastreio": f"https://rastreio.mock/pedido/{courier_ref}",
            "codigo_confirmacao": 1234,
        }
    ]


def register_webhook(url: str, *, kind: str) -> bool:
    return True
