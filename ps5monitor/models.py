"""Modello dati delle offerte (R2.1)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

MODELLI = ("standard_disc", "digital", "pro", "altro_console", "sconosciuto")
CONDIZIONI = ("nuovo", "ricondizionato", "usato", "sconosciuta")
DISPONIBILITA = ("disponibile", "ultime_unita", "non_disponibile", "in_arrivo", "sconosciuta")
DISPONIBILI = ("disponibile", "ultime_unita")
VENDITORE_TIPI = ("negozio", "amazon", "terzo", "privato")
CANALI = ("spedizione", "ritiro_milano", "entrambi")
FLAGS = ("spedizione_da_verificare", "prezzo_sospetto", "da_verificare_sul_negozio", "non_verificata")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class NegozioMilano:
    nome: str
    comune: str = ""
    telefono: str = ""
    distanza_km: Decimal | None = None
    tempi_ritiro: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["distanza_km"] = None if self.distanza_km is None else str(self.distanza_km)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "NegozioMilano":
        d = dict(d)
        if d.get("distanza_km") is not None:
            d["distanza_km"] = Decimal(d["distanza_km"])
        return cls(**d)


_DECIMAL_FIELDS = ("prezzo", "prezzo_barrato", "spedizione_eur", "feedback_pct")


@dataclass
class Offer:
    source_id: str
    offer_id: str
    url_canonico: str
    titolo: str
    prezzo: Decimal | None
    modello: str = "sconosciuto"
    condizione: str = "sconosciuta"
    bundle: str = ""
    prezzo_barrato: Decimal | None = None
    spedizione_eur: Decimal | None = None
    disponibilita: str = "sconosciuta"
    venditore: str = ""
    venditore_tipo: str = "negozio"
    canale: str = "spedizione"
    negozi_milano: list[NegozioMilano] = field(default_factory=list)
    localita_annuncio: str = ""
    rilevata_il: datetime = field(default_factory=utcnow)
    verificata_su_pagina_prodotto: bool = False
    valuta: str = "EUR"
    categoria: str = ""
    quantita_disponibile: int | None = None
    consegna_testo: str = ""
    garanzia_testo: str = ""
    feedback_pct: Decimal | None = None
    feedback_n: int | None = None
    ha_foto: bool | None = None
    flags: list[str] = field(default_factory=list)
    # Campi di supporto (non mostrati): coordinate dell'annuncio e "solo ritiro" (Subito, R9.3)
    localita_lat: float | None = None
    localita_lon: float | None = None
    solo_ritiro: bool = False

    @property
    def key(self) -> str:
        return f"{self.source_id}:{self.offer_id}"

    @property
    def disponibile(self) -> bool:
        return self.disponibilita in DISPONIBILI

    @property
    def ritiro_milano(self) -> bool:
        return self.canale in ("ritiro_milano", "entrambi")

    def add_flag(self, flag: str) -> None:
        if flag not in self.flags:
            self.flags.append(flag)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k in _DECIMAL_FIELDS:
            d[k] = None if getattr(self, k) is None else str(getattr(self, k))
        d["rilevata_il"] = self.rilevata_il.astimezone(timezone.utc).isoformat()
        d["negozi_milano"] = [n.to_dict() for n in self.negozi_milano]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Offer":
        d = dict(d)
        for k in _DECIMAL_FIELDS:
            if d.get(k) is not None:
                d[k] = Decimal(d[k])
        d["rilevata_il"] = datetime.fromisoformat(d["rilevata_il"])
        d["negozi_milano"] = [NegozioMilano.from_dict(n) for n in d.get("negozi_milano", [])]
        known = cls.__dataclass_fields__
        return cls(**{k: v for k, v in d.items() if k in known})
