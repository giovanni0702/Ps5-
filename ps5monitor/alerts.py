"""Ammissione delle offerte, eventi e anti-spam (R2.6, R4, R7, R9)."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from .classify import is_console_cfg
from .geo import haversine_km
from .models import Offer
from .pricing import Scored, q2
from .state import parse_iso


def validate_offer(offer: Offer, cfg) -> tuple[bool, str]:
    """Scarti a monte (prima dello stato): valuta, prezzo, console vera, annunci privati senza foto."""
    if (offer.valuta or "EUR").upper() != "EUR":
        return False, "valuta_non_eur"
    if offer.prezzo is None or offer.prezzo <= 0:
        return False, "prezzo_non_leggibile"
    ok, motivo = is_console_cfg(offer.titolo, offer.prezzo, offer.categoria, cfg)
    if not ok:
        return False, motivo
    if offer.venditore_tipo == "privato" and offer.ha_foto is False:
        return False, "annuncio privato senza foto"
    return True, "ok"


def alert_eligible(sc: Scored, cfg, source_tipo: str = "retailer") -> tuple[bool, str]:
    """Un'offerta valida genera avvisi solo se rispetta tutte le preferenze (R2.6, R7.1, R9.2, R9.3)."""
    o = sc.offer
    if sc.totale > cfg.prezzo_max_eur:
        return False, "sopra_soglia"
    if o.modello not in cfg.modelli_ammessi:
        return False, "modello_non_ammesso"
    if o.condizione not in cfg.condizioni_ammesse:
        return False, "condizione_non_ammessa"
    if source_tipo in ("marketplace", "classificati") and not cfg.marketplace_ammessi:
        return False, "marketplace_non_ammesso"
    if o.venditore_tipo == "terzo" and not cfg.venditori_terzi:
        return False, "venditori_terzi_non_ammessi"
    if o.venditore_tipo == "privato" and not cfg.privati:
        return False, "privati_non_ammessi"
    if o.solo_ritiro:
        if o.localita_lat is None or o.localita_lon is None:
            return False, "solo_ritiro_localita_ignota"
        if haversine_km(cfg.lat, cfg.lon, o.localita_lat, o.localita_lon) > Decimal(str(cfg.raggio_km)):
            return False, "solo_ritiro_fuori_raggio"
    if sc.priorita is None:
        return False, "non_disponibile" if o.disponibilita != "in_arrivo" else "in_arrivo"
    return True, "ok"


def price_dropped(prev: Decimal | None, now: Decimal, cfg) -> bool:
    if prev is None:
        return False
    drop = prev - now
    if drop <= 0:
        return False
    return drop >= cfg.delta_prezzo_min_eur or q2(drop / prev * 100) >= cfg.delta_prezzo_min_pct


def compute_events(rec: dict, sc: Scored, cfg) -> list[str]:
    """Eventi rispetto all'ultima notifica salvata nello stato (R4.2, R6.7): nessun evento va perso."""
    if not sc.offer.disponibile:
        return []
    if rec.get("notificato_il") is None:
        return ["nuova_disponibile"]
    ev = []
    if rec.get("esaurita"):
        ev.append("tornata_disponibile")
    if sc.in_sconto and not rec.get("notificato_in_sconto"):
        ev.append("nuovo_sconto")
    prev = rec.get("notificato_totale")
    if price_dropped(Decimal(prev) if prev else None, sc.totale, cfg):
        ev.append("prezzo_sceso")
    prev_p = rec.get("notificato_priorita")
    if sc.priorita is not None and prev_p is not None and sc.priorita < prev_p:
        ev.append("priorita_migliorata")
    return ev


def cooldown_allows(rec: dict, sc: Scored, events: list[str], cfg, now: datetime) -> bool:
    """R4.3: entro il cooldown passa solo un nuovo calo di prezzo o un salto verso P1/P2."""
    last = parse_iso(rec.get("notificato_il"))
    if last is None or now - last >= timedelta(minutes=cfg.cooldown_minuti):
        return True
    if "prezzo_sceso" in events:
        return True
    if "priorita_migliorata" in events and sc.priorita in (1, 2):
        return True
    return False


EVENT_LABELS = {
    "nuova_disponibile": "nuova offerta disponibile",
    "tornata_disponibile": "tornata disponibile",
    "nuovo_sconto": "nuovo sconto",
    "prezzo_sceso": "prezzo sceso",
    "priorita_migliorata": "priorità migliorata",
}
