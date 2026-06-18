"""Distância geográfica loja→endereço para precificar a entrega.

Motor da taxa por faixa de distância (WP-11): a origem é a loja
(`Shop.latitude/longitude`) e o destino vem do endereço estruturado do checkout
(`delivery_address_structured.latitude/longitude`, já capturado via Google
Places). Função pura de haversine; a resolução em faixa/zona fica no
`DeliveryFeeModifier`.
"""

from __future__ import annotations

import math


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância em km entre dois pontos (lat/lng em graus) pela fórmula de haversine."""
    radius_km = 6371.0088  # raio médio da Terra
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius_km * math.asin(min(1.0, math.sqrt(a)))


def _to_float(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def store_distance_km(dest_lat, dest_lng) -> float | None:
    """Distância da loja (singleton) ao destino, ou None se faltar coordenada.

    Retorna None quando a loja não tem coordenadas configuradas ou o endereço
    ainda não foi geocodificado — o chamador trata como "não dá para precificar
    por distância" e cai na zona (ou bloqueia).
    """
    from shopman.shop.models import Shop

    dest_lat_f = _to_float(dest_lat)
    dest_lng_f = _to_float(dest_lng)
    if dest_lat_f is None or dest_lng_f is None:
        return None

    shop = Shop.load()
    if shop is None:
        return None
    origin_lat = _to_float(shop.latitude)
    origin_lng = _to_float(shop.longitude)
    if origin_lat is None or origin_lng is None:
        return None

    return haversine_km(origin_lat, origin_lng, dest_lat_f, dest_lng_f)
