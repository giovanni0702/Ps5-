"""Stato persistente (state.json sul branch "stato"): offerte, storico prezzi, stato delle fonti (R1.5, R4.1, R6.3).

Tutti gli orari sono in UTC (G9).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from .models import Offer
from .pricing import history_median

MAX_BYTES = 1_000_000
HISTORY_DAYS = 30
OBS_EVERY = timedelta(hours=6)
BLOCK_BACKOFF_MIN = (30, 60, 120, 240)
HEARTBEAT_EVERY = timedelta(hours=1)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_iso(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def _empty() -> dict[str, Any]:
    return {
        "versione": 1,
        "avviato": False,
        "battito": None,
        "offerte": {},
        "fonti": {},
        "coda": [],
        "non_consegnati": [],
        "avvisi_inviati": [],
        "transizioni": [],
        "ultimo_report": None,
        "ultimo_allarme_cieco": None,
        # Dati che cambiano a ogni ciclo: salvati, ma da soli non causano una pubblicazione.
        "volatile": {"domini": {}, "cicli": 0, "rr": {}, "ultima_offerta": {}, "visto": {}, "ultimo_ok": None},
    }


class State:
    def __init__(self, data: dict | None = None):
        base = _empty()
        if data:
            base.update(data)
            vol = _empty()["volatile"]
            vol.update(base.get("volatile") or {})
            base["volatile"] = vol
        self.data = base
        self._published_fp = self.fingerprint() if data else None
        self._published_beat = self.data.get("battito")

    # --- file --------------------------------------------------------------
    @classmethod
    def load(cls, path: str | Path) -> "State":
        p = Path(path)
        if not p.exists() or not p.read_text(encoding="utf-8").strip():
            return cls()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return cls()
        return cls(data if isinstance(data, dict) and data else None)

    def dumps(self) -> str:
        return json.dumps(self.data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.dumps(), encoding="utf-8")

    def fingerprint(self) -> str:
        d = {k: v for k, v in self.data.items() if k not in ("volatile", "battito")}
        return hashlib.sha256(json.dumps(d, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def needs_publish(self, now: datetime) -> bool:
        """R6.3: si pubblica se è cambiato qualcosa oltre al battito; il battito si aggiorna al massimo ogni ora."""
        beat = parse_iso(self.data.get("battito"))
        if beat is None or now - beat >= HEARTBEAT_EVERY:
            self.data["battito"] = iso(now)
        return self.fingerprint() != self._published_fp or self.data["battito"] != self._published_beat

    def mark_published(self) -> None:
        self._published_fp = self.fingerprint()
        self._published_beat = self.data.get("battito")

    # --- avvio -------------------------------------------------------------
    @property
    def is_new(self) -> bool:
        return not self.data.get("avviato")

    @property
    def vol(self) -> dict:
        return self.data["volatile"]

    # --- offerte -----------------------------------------------------------
    @property
    def offers(self) -> dict[str, dict]:
        return self.data["offerte"]

    def record(self, key: str) -> dict | None:
        return self.offers.get(key)

    def upsert(self, offer: Offer, totale: Decimal, in_sconto: bool, priorita: int | None, now: datetime) -> tuple[dict, bool]:
        """Aggiorna il record dell'offerta. Restituisce (record, era_nuova)."""
        rec = self.offers.get(offer.key)
        new = rec is None
        if new:
            rec = {
                "primo_visto": iso(now), "notificato_il": None, "notificato_totale": None,
                "notificato_priorita": None, "notificato_in_sconto": False,
                "non_disp_consecutivi": 0, "esaurita": False, "storico": [],
            }
            self.offers[offer.key] = rec
        if offer.disponibile:
            rec["non_disp_consecutivi"] = 0
        elif offer.disponibilita == "non_disponibile":
            rec["non_disp_consecutivi"] = rec.get("non_disp_consecutivi", 0) + 1
            if rec["non_disp_consecutivi"] >= 2:   # R4.6: due controlli consecutivi
                rec["esaurita"] = True
        snap = offer.to_dict()
        self.vol["visto"][offer.key] = snap.pop("rilevata_il")
        rec.update({
            "offerta": snap, "totale": str(totale), "disponibilita": offer.disponibilita,
            "in_sconto": in_sconto, "priorita": priorita, "non_verificata": False,
            "fonte": offer.source_id, "modello": offer.modello, "condizione": offer.condizione,
        })
        self._observe(rec, totale, now)
        return rec, new

    def _observe(self, rec: dict, totale: Decimal, now: datetime) -> None:
        """R3.2: un'osservazione quando il totale cambia, oppure al massimo una ogni 6 ore."""
        hist = rec.setdefault("storico", [])
        if hist:
            last_t, last_p = parse_iso(hist[-1][0]), Decimal(hist[-1][1])
            if last_p == totale and now - last_t < OBS_EVERY:
                return
        hist.append([iso(now), str(totale)])

    def median_for(self, source_id: str, modello: str, condizione: str, now: datetime) -> Decimal | None:
        obs = []
        for rec in self.offers.values():
            if rec.get("fonte") == source_id and rec.get("modello") == modello and rec.get("condizione") == condizione:
                obs.extend((parse_iso(t), Decimal(p)) for t, p in rec.get("storico", []))
        return history_median(obs, now)

    def offer_of(self, key: str) -> Offer | None:
        rec = self.offers.get(key)
        if not rec or "offerta" not in rec:
            return None
        d = dict(rec["offerta"])
        d["rilevata_il"] = self.vol["visto"].get(key) or rec.get("primo_visto")
        o = Offer.from_dict(d)
        if rec.get("non_verificata"):
            o.add_flag("non_verificata")
        return o

    def mark_unverified(self, source_id: str) -> None:
        """R1.6: le offerte di una fonte in errore restano, marcate "non verificate"."""
        for rec in self.offers.values():
            if rec.get("fonte") == source_id:
                rec["non_verificata"] = True

    def mark_notified(self, rec: dict, totale: Decimal, priorita: int | None, in_sconto: bool, now: datetime) -> None:
        rec.update({"notificato_il": iso(now), "notificato_totale": str(totale),
                    "notificato_priorita": priorita, "notificato_in_sconto": in_sconto, "esaurita": False})
        self.data["avvisi_inviati"].append(iso(now))

    # --- fonti (R1.5) --------------------------------------------------------
    def source(self, sid: str) -> dict:
        return self.data["fonti"].setdefault(sid, {
            "stato": "ok", "errori_consecutivi": 0, "livello_blocco": 0, "bloccata_fino": None,
            "ha_dato_offerte": False, "ultimo_errore": "",
        })

    def _transition(self, sid: str, new: str, motivo: str, now: datetime) -> None:
        s = self.source(sid)
        if s["stato"] != new:
            self.data["transizioni"].append({"ts": iso(now), "fonte": sid, "da": s["stato"], "a": new, "motivo": motivo})
            s["stato"] = new

    def source_ok(self, sid: str, n_offers: int, now: datetime) -> None:
        s = self.source(sid)
        s["errori_consecutivi"] = 0
        s["livello_blocco"] = 0
        s["bloccata_fino"] = None
        last = parse_iso(self.vol["ultima_offerta"].get(sid))
        if n_offers > 0:
            self.vol["ultima_offerta"][sid] = iso(now)
            if not s["ha_dato_offerte"]:
                s["ha_dato_offerte"] = True
            self._transition(sid, "ok", "risposta valida", now)
        elif s["ha_dato_offerte"] and last is not None and now - last >= timedelta(hours=24):
            self._transition(sid, "da_riparare", "0 offerte da 24 ore", now)
        elif s["stato"] != "da_riparare":
            self._transition(sid, "ok", "risposta valida", now)
        if s["stato"] == "ok":
            self.vol["ultimo_ok"] = iso(now)

    def source_error(self, sid: str, motivo: str, now: datetime) -> None:
        s = self.source(sid)
        s["errori_consecutivi"] += 1
        s["ultimo_errore"] = motivo[:200]
        if s["errori_consecutivi"] >= 3 and s["stato"] in ("ok", "da_riparare"):
            self._transition(sid, "degradata", f"3 errori consecutivi: {motivo[:120]}", now)

    def source_blocked(self, sid: str, motivo: str, now: datetime) -> None:
        s = self.source(sid)
        livello = min(s.get("livello_blocco", 0), len(BLOCK_BACKOFF_MIN) - 1)
        s["bloccata_fino"] = iso(now + timedelta(minutes=BLOCK_BACKOFF_MIN[livello]))
        s["livello_blocco"] = min(livello + 1, len(BLOCK_BACKOFF_MIN) - 1)
        s["ultimo_errore"] = motivo[:200]
        self._transition(sid, "bloccata", motivo[:120], now)

    def source_disabled(self, sid: str, now: datetime) -> None:
        self._transition(sid, "disattivata", "disattivata in config.yaml", now)

    def source_can_run(self, sid: str, now: datetime) -> bool:
        s = self.source(sid)
        until = parse_iso(s.get("bloccata_fino"))
        return not (s["stato"] == "bloccata" and until and now < until)

    # --- manutenzione (R6.3) -----------------------------------------------
    def prune(self, now: datetime) -> None:
        limit = now - timedelta(days=HISTORY_DAYS)
        for key in list(self.offers):
            rec = self.offers[key]
            rec["storico"] = [h for h in rec.get("storico", []) if parse_iso(h[0]) >= limit]
            seen = parse_iso(self.vol["visto"].get(key)) or parse_iso(rec.get("primo_visto"))
            if seen and seen < limit:
                del self.offers[key]
                self.vol["visto"].pop(key, None)
        week = now - timedelta(days=7)
        self.data["transizioni"] = [t for t in self.data["transizioni"] if parse_iso(t["ts"]) >= week]
        day2 = now - timedelta(days=2)
        self.data["avvisi_inviati"] = [t for t in self.data["avvisi_inviati"] if parse_iso(t) >= day2]
        self.data["non_consegnati"] = self.data["non_consegnati"][-100:]
        # Sotto 1 MB: pota le osservazioni più vecchie, a blocchi, finché serve.
        size = len(self.dumps().encode())
        while size > MAX_BYTES:
            obs = sorted((h[0], id(rec), rec) for rec in self.offers.values() for h in rec.get("storico", [])[:1])
            if not obs:
                break
            excess = size - MAX_BYTES
            n = max(1, min(len(obs), excess // 30 + 1))
            for _, _, rec in obs[:n]:
                rec["storico"].pop(0)
            size = len(self.dumps().encode())
