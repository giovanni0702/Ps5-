"""Distanze con la formula di Haversine (R8.1) e punti vendita da data/negozi.yaml (R8.3)."""
from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import yaml

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> Decimal:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    km = 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))
    return Decimal(str(km)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def load_stores(path: str | Path = "data/negozi.yaml") -> dict[str, list[dict]]:
    """Restituisce {catena: [negozi]}; file assente o vuoto → dizionario vuoto."""
    p = Path(path)
    if not p.exists():
        return {}
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    catene = raw.get("catene") or {}
    return {k: list(v or []) for k, v in catene.items()}
