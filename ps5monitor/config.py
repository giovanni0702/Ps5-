"""Caricamento e validazione di config.yaml (G7).

Ogni errore produce una frase in italiano che indica la chiave e il valore sbagliati.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

MODELLI = ["standard_disc", "digital", "pro", "altro_console", "sconosciuto"]
CONDIZIONI = ["nuovo", "ricondizionato", "usato", "sconosciuta"]
CANALI_NOTIFICA = ["ntfy", "telegram", "email"]


class ConfigError(Exception):
    """Errore di configurazione con messaggio in italiano."""


@dataclass
class SourceConfig:
    abilitata: bool
    prodotti: list[str]
    ricerca: str | None
    ricerca_ogni_cicli: int


@dataclass
class Config:
    prezzo_max_eur: Decimal
    prezzo_min_console_eur: Decimal
    modelli_ammessi: list[str]
    condizioni_ammesse: list[str]
    marketplace_ammessi: bool
    venditori_terzi: bool
    privati: bool
    soglia_sconto_pct: Decimal
    listino_ufficiale: dict[str, Decimal | None]
    soglia_prezzo_sospetto_pct: Decimal
    fattore_riferimento_max: Decimal
    delta_prezzo_min_eur: Decimal
    delta_prezzo_min_pct: Decimal
    cooldown_minuti: int
    durata_run_secondi: int
    intervallo_ciclo_secondi: int
    intervallo_dominio_secondi: int
    citta: str
    lat: float
    lon: float
    raggio_km: float
    canali: list[str]
    report_ora: str
    ntfy_server: str
    parole_escluse_forti: list[str]
    parole_escluse_deboli: list[str]
    parole_difetto: list[str]
    fonti: dict[str, SourceConfig] = field(default_factory=dict)

    @property
    def report_hour_minute(self) -> tuple[int, int]:
        h, m = self.report_ora.split(":")
        return int(h), int(m)


def _err(chiave: str, valore: Any, atteso: str) -> ConfigError:
    return ConfigError(
        f"Errore in config.yaml: la chiave '{chiave}' ha valore {valore!r}, ma {atteso}."
    )


def _get(d: dict, key: str, path: str) -> Any:
    if not isinstance(d, dict) or key not in d:
        raise ConfigError(f"Errore in config.yaml: manca la chiave '{path}'.")
    return d[key]


def _decimal(d: dict, key: str, path: str, positive: bool = True, allow_zero: bool = False) -> Decimal:
    v = _get(d, key, path)
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        raise _err(path, v, "deve essere un numero")
    try:
        dec = Decimal(str(v).replace(",", "."))
    except InvalidOperation:
        raise _err(path, v, "deve essere un numero") from None
    if not dec.is_finite():
        raise _err(path, v, "deve essere un numero")
    if positive and (dec < 0 or (dec == 0 and not allow_zero)):
        raise _err(path, v, "deve essere un numero maggiore di zero")
    return dec


def _int(d: dict, key: str, path: str, minimo: int = 1, massimo: int | None = None) -> int:
    v = _get(d, key, path)
    if isinstance(v, bool) or not isinstance(v, int):
        raise _err(path, v, "deve essere un numero intero")
    if v < minimo:
        raise _err(path, v, f"deve essere almeno {minimo}")
    if massimo is not None and v > massimo:
        raise _err(path, v, f"non può superare {massimo}")
    return v


def _bool(d: dict, key: str, path: str) -> bool:
    v = _get(d, key, path)
    if not isinstance(v, bool):
        raise _err(path, v, "deve essere true oppure false")
    return v


def _list_of(d: dict, key: str, path: str, allowed: list[str] | None = None, allow_empty: bool = False) -> list[str]:
    v = _get(d, key, path)
    if not isinstance(v, list) or (not v and not allow_empty):
        raise _err(path, v, "deve essere un elenco non vuoto")
    out = []
    for item in v:
        if not isinstance(item, str) or not item.strip():
            raise _err(path, item, "ogni elemento deve essere un testo")
        item = item.strip()
        if allowed is not None and item not in allowed:
            raise _err(path, item, f"i valori ammessi sono: {', '.join(allowed)}")
        out.append(item.lower() if allowed is None else item)
    return out


def parse_config(raw: Any) -> Config:
    if not isinstance(raw, dict):
        raise ConfigError("Errore in config.yaml: il file è vuoto o non è nel formato chiave: valore.")
    mp = _get(raw, "marketplace", "marketplace")
    listino_raw = _get(raw, "listino_ufficiale", "listino_ufficiale")
    listino: dict[str, Decimal | None] = {}
    for m in ("standard_disc", "digital", "pro"):
        path = f"listino_ufficiale.{m}"
        v = _get(listino_raw, m, path)
        listino[m] = None if v is None else _decimal(listino_raw, m, path)
    area = _get(raw, "area", "area")
    notif = _get(raw, "notifiche", "notifiche")
    report_ora = str(_get(notif, "report_ora", "notifiche.report_ora"))
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", report_ora):
        raise _err("notifiche.report_ora", report_ora, "deve essere un orario HH:MM, per esempio \"09:00\"")
    server = _get(notif, "ntfy_server", "notifiche.ntfy_server")
    if not isinstance(server, str) or not server.startswith(("https://", "http://")):
        raise _err("notifiche.ntfy_server", server, "deve essere un indirizzo che inizia con https://")

    def _float(d, key, path, lo, hi):
        v = _get(d, key, path)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
            raise _err(path, v, f"deve essere un numero tra {lo} e {hi}")
        return float(v)

    citta = _get(area, "citta", "area.citta")
    if not isinstance(citta, str) or not citta.strip():
        raise _err("area.citta", citta, "deve essere il nome di una città")

    fonti_raw = _get(raw, "fonti", "fonti")
    if not isinstance(fonti_raw, dict) or not fonti_raw:
        raise _err("fonti", fonti_raw, "deve contenere almeno una fonte")
    fonti: dict[str, SourceConfig] = {}
    for sid, sc in fonti_raw.items():
        p = f"fonti.{sid}"
        if not isinstance(sc, dict):
            raise _err(p, sc, "deve contenere abilitata, prodotti, ricerca, ricerca_ogni_cicli")
        prodotti = _get(sc, "prodotti", p + ".prodotti")
        if prodotti is None:
            prodotti = []
        if not isinstance(prodotti, list) or any(not isinstance(u, str) or not u.startswith("http") for u in prodotti):
            raise _err(p + ".prodotti", prodotti, "deve essere un elenco di indirizzi che iniziano con https://")
        ricerca = _get(sc, "ricerca", p + ".ricerca")
        if ricerca is not None and (not isinstance(ricerca, str) or not ricerca.startswith("http")):
            raise _err(p + ".ricerca", ricerca, "deve essere un indirizzo che inizia con https:// oppure null")
        fonti[str(sid)] = SourceConfig(
            abilitata=_bool(sc, "abilitata", p + ".abilitata"),
            prodotti=list(prodotti),
            ricerca=ricerca,
            ricerca_ogni_cicli=_int(sc, "ricerca_ogni_cicli", p + ".ricerca_ogni_cicli", 1),
        )

    cfg = Config(
        prezzo_max_eur=_decimal(raw, "prezzo_max_eur", "prezzo_max_eur"),
        prezzo_min_console_eur=_decimal(raw, "prezzo_min_console_eur", "prezzo_min_console_eur", allow_zero=True),
        modelli_ammessi=_list_of(raw, "modelli_ammessi", "modelli_ammessi", MODELLI),
        condizioni_ammesse=_list_of(raw, "condizioni_ammesse", "condizioni_ammesse", CONDIZIONI),
        marketplace_ammessi=_bool(mp, "ammessi", "marketplace.ammessi"),
        venditori_terzi=_bool(mp, "venditori_terzi", "marketplace.venditori_terzi"),
        privati=_bool(mp, "privati", "marketplace.privati"),
        soglia_sconto_pct=_decimal(raw, "soglia_sconto_pct", "soglia_sconto_pct", allow_zero=True),
        listino_ufficiale=listino,
        soglia_prezzo_sospetto_pct=_decimal(raw, "soglia_prezzo_sospetto_pct", "soglia_prezzo_sospetto_pct", allow_zero=True),
        fattore_riferimento_max=_decimal(raw, "fattore_riferimento_max", "fattore_riferimento_max"),
        delta_prezzo_min_eur=_decimal(raw, "delta_prezzo_min_eur", "delta_prezzo_min_eur", allow_zero=True),
        delta_prezzo_min_pct=_decimal(raw, "delta_prezzo_min_pct", "delta_prezzo_min_pct", allow_zero=True),
        cooldown_minuti=_int(raw, "cooldown_minuti", "cooldown_minuti", 0),
        durata_run_secondi=_int(raw, "durata_run_secondi", "durata_run_secondi", 30, 330),
        intervallo_ciclo_secondi=_int(raw, "intervallo_ciclo_secondi", "intervallo_ciclo_secondi", 30),
        intervallo_dominio_secondi=_int(raw, "intervallo_dominio_secondi", "intervallo_dominio_secondi", 30),
        citta=citta.strip(),
        lat=_float(area, "lat", "area.lat", -90, 90),
        lon=_float(area, "lon", "area.lon", -180, 180),
        raggio_km=_float(area, "raggio_km", "area.raggio_km", 0.1, 500),
        canali=_list_of(notif, "canali", "notifiche.canali", CANALI_NOTIFICA),
        report_ora=report_ora,
        ntfy_server=server.rstrip("/"),
        parole_escluse_forti=_list_of(raw, "parole_escluse_forti", "parole_escluse_forti"),
        parole_escluse_deboli=_list_of(raw, "parole_escluse_deboli", "parole_escluse_deboli"),
        parole_difetto=_list_of(raw, "parole_difetto", "parole_difetto"),
        fonti=fonti,
    )
    if cfg.prezzo_min_console_eur >= cfg.prezzo_max_eur:
        raise _err("prezzo_min_console_eur", str(cfg.prezzo_min_console_eur),
                   "deve essere minore di prezzo_max_eur")
    return cfg


def load_config(path: str | Path = "config.yaml") -> Config:
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"Errore: non trovo il file di configurazione '{p}'.")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        riga = f" alla riga {mark.line + 1}" if mark else ""
        raise ConfigError(f"Errore in config.yaml{riga}: formato non valido (controlla rientri e due punti).") from None
    return parse_config(raw)
