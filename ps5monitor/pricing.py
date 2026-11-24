"""Prezzi in formato italiano, prezzo di riferimento, sconto e priorità (G10, R3, R7)."""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Iterable

from .models import Offer

CENT = Decimal("0.01")
TENTH = Decimal("0.1")


def q2(d: Decimal) -> Decimal:
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def q1(d: Decimal) -> Decimal:
    return d.quantize(TENTH, rounding=ROUND_HALF_UP)


_NUM_RE = re.compile(r"\d[\d.,\s  ']*")


def parse_price(value) -> Decimal | None:
    """Legge '1.099,00 €', '€ 469', '469,00', '469.00', 469 → Decimal. None se non leggibile."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, Decimal)):
        d = Decimal(value)
        return q2(d) if d.is_finite() else None
    if isinstance(value, float):
        return q2(Decimal(str(value)))
    text = str(value).strip()
    m = _NUM_RE.search(text)
    if not m:
        return None
    num = re.sub(r"[\s  ']", "", m.group(0)).rstrip(".,")
    if "," in num and "." in num:
        if num.rfind(",") > num.rfind("."):
            num = num.replace(".", "").replace(",", ".")
        else:
            num = num.replace(",", "")
    elif "," in num:
        parts = num.split(",")
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            num = num.replace(",", ".")
        elif len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
            num = num.replace(",", "")
        else:
            num = num.replace(",", ".")
    elif "." in num:
        parts = num.split(".")
        if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3):
            num = num.replace(".", "")
    try:
        d = Decimal(num)
    except InvalidOperation:
        return None
    return q2(d)


def fmt_eur(d: Decimal | None) -> str:
    if d is None:
        return "n.d."
    d = q2(Decimal(d))
    sign = "-" if d < 0 else ""
    intero, dec = f"{abs(d):.2f}".split(".")
    gruppi = []
    while len(intero) > 3:
        gruppi.insert(0, intero[-3:])
        intero = intero[:-3]
    gruppi.insert(0, intero)
    return f"{sign}{'.'.join(gruppi)},{dec} €"


def fmt_pct(d: Decimal | None) -> str:
    if d is None:
        return "n.d."
    return f"{q1(Decimal(d)):.1f}".replace(".", ",") + "%"


def prezzo_totale(offer: Offer) -> Decimal:
    """R3.1: prezzo + spedizione; spedizione ignota → solo prezzo e flag."""
    if offer.spedizione_eur is None:
        offer.add_flag("spedizione_da_verificare")
        return q2(offer.prezzo)
    return q2(offer.prezzo + offer.spedizione_eur)


@dataclass
class Reference:
    valore: Decimal | None
    fonte: str | None          # dichiarato, storico, listino
    note: list[str] = field(default_factory=list)


def history_median(observations: Iterable[tuple[datetime, Decimal]], now: datetime) -> Decimal | None:
    """R3.2 (2): mediana degli ultimi 30 giorni, solo osservazioni di almeno 24 ore fa,
    almeno 5 osservazioni su almeno 2 giorni di calendario."""
    lo = now - timedelta(days=30)
    hi = now - timedelta(hours=24)
    vals = [(t, p) for t, p in observations if lo <= t <= hi]
    if len(vals) < 5 or len({t.date() for t, _ in vals}) < 2:
        return None
    return q2(Decimal(statistics.median(sorted(p for _, p in vals))))


def reference_price(offer: Offer, cfg, median: Decimal | None) -> Reference:
    notes: list[str] = []
    listino = cfg.listino_ufficiale.get(offer.modello) if offer.modello in cfg.listino_ufficiale else None
    pb = offer.prezzo_barrato
    if pb is not None and pb > 0:
        if listino is not None and offer.modello in ("standard_disc", "digital", "pro"):
            limite = q2(cfg.fattore_riferimento_max * listino)
            if pb <= limite:
                return Reference(pb, "dichiarato")
            notes.append(f"riferimento gonfiato ({fmt_eur(pb)} > {fmt_eur(limite)})")
        else:
            if offer.prezzo is not None and offer.prezzo < pb <= q2(offer.prezzo * Decimal("1.5")):
                return Reference(pb, "dichiarato")
            notes.append("riferimento gonfiato o non plausibile")
    if median is not None:
        return Reference(median, "storico", notes)
    if offer.condizione == "nuovo" and listino is not None:
        return Reference(listino, "listino", notes)
    return Reference(None, None, notes)


def discount(prezzo: Decimal, riferimento: Decimal | None) -> tuple[Decimal | None, Decimal | None]:
    if riferimento is None or riferimento <= 0:
        return None, None
    if prezzo >= riferimento:
        return Decimal("0.00"), Decimal("0.0")
    eur = q2(riferimento - prezzo)
    pct = q1(eur / riferimento * 100)
    return eur, pct


def priority(disponibilita: str, in_sconto: bool, venditore_tipo: str) -> int | None:
    """R3.4: P1..P4, None per offerte non disponibili / in arrivo / sconosciute."""
    if disponibilita not in ("disponibile", "ultime_unita"):
        return None
    ufficiale = venditore_tipo in ("negozio", "amazon")
    if in_sconto:
        return 1 if ufficiale else 2
    return 3 if ufficiale else 4


@dataclass
class Scored:
    offer: Offer
    totale: Decimal
    riferimento: Reference
    sconto_eur: Decimal | None
    sconto_pct: Decimal | None
    in_sconto: bool
    priorita: int | None

    @property
    def key(self) -> str:
        return self.offer.key


def score(offer: Offer, cfg, median: Decimal | None = None) -> Scored:
    totale = prezzo_totale(offer)
    ref = reference_price(offer, cfg, median)
    eur, pct = discount(offer.prezzo, ref.valore)
    in_sconto = pct is not None and pct >= q1(cfg.soglia_sconto_pct)
    listino = cfg.listino_ufficiale.get(offer.modello)
    if (offer.condizione == "nuovo" and listino is not None
            and totale < q2(listino * cfg.soglia_prezzo_sospetto_pct / 100)):
        offer.add_flag("prezzo_sospetto")
    return Scored(offer, totale, ref, eur, pct, in_sconto,
                  priority(offer.disponibilita, in_sconto, offer.venditore_tipo))


def sort_key(s: Scored):
    """R3.4: priorità crescente, sconto decrescente, ritiro a Milano prima, totale crescente."""
    return (
        s.priorita if s.priorita is not None else 9,
        -(s.sconto_pct or Decimal(0)),
        0 if s.offer.ritiro_milano else 1,
        s.totale,
    )
