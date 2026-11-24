"""Report giornaliero (R7.3, R10.5)."""
from __future__ import annotations

from datetime import datetime, timedelta

from .alerts import alert_eligible
from .messages import ROME, Message, fmt_dt, truncate
from .pricing import fmt_eur, fmt_pct, score, sort_key
from .state import State, parse_iso

STATE_LABEL = {"ok": "ok", "degradata": "degradata", "bloccata": "bloccata", "da_riparare": "da riparare",
               "disattivata": "disattivata"}


def _scored_offers(state: State, cfg, now: datetime):
    out = []
    for key in state.offers:
        o = state.offer_of(key)
        if o is None:
            continue
        median = state.median_for(o.source_id, o.modello, o.condizione, now)
        out.append(score(o, cfg, median))
    return out


def daily_report(state: State, cfg, now: datetime, sources) -> Message:
    names = {s.id: s.nome for s in sources}
    tipi = {s.id: s.tipo for s in sources}
    day = now - timedelta(hours=24)
    blocks = []

    lines = ["Stato delle fonti:"]
    for s in sources:
        info = state.data["fonti"].get(s.id, {})
        stato = "disattivata" if not s.enabled() else STATE_LABEL.get(info.get("stato", "ok"), info.get("stato", "?"))
        extra = f" ({info['ultimo_errore'][:60]})" if stato in ("degradata", "bloccata") and info.get("ultimo_errore") else ""
        lines.append(f"- {s.nome}: {stato}{extra}")
    trans = [t for t in state.data.get("transizioni", []) if parse_iso(t["ts"]) >= day]
    if trans:
        lines.append("Cambi di stato nelle ultime 24 ore:")
        for t in trans[-15:]:
            lines.append(f"- {fmt_dt(parse_iso(t['ts']))} {names.get(t['fonte'], t['fonte'])}: "
                         f"{t['da']} → {t['a']} ({t['motivo'][:60]})")
    blocks.append("\n".join(lines))

    scored = _scored_offers(state, cfg, now)
    elig = [s for s in scored if alert_eligible(s, cfg, tipi.get(s.offer.source_id, "retailer"))[0]]
    best = sorted(elig, key=sort_key)[:5]
    lines = ["Offerte migliori del momento (anche già notificate):"]
    if not best:
        lines.append("- nessuna offerta disponibile sotto il prezzo massimo")
    for s in best:
        sconto = f", sconto {fmt_pct(s.sconto_pct)}" if s.in_sconto else ""
        lines.append(f"- P{s.priorita} {truncate(s.offer.titolo, 70)}: {fmt_eur(s.totale)} su "
                     f"{names.get(s.offer.source_id, s.offer.source_id)}{sconto}\n  {s.offer.url_canonico}")
    blocks.append("\n".join(lines))

    sent = [t for t in state.data.get("avvisi_inviati", []) if parse_iso(t) >= day]
    blocks.append(f"Avvisi inviati nelle ultime 24 ore: {len(sent)}"
                  + (f"\nAvvisi non consegnati in attesa: {len(state.data['non_consegnati'])}"
                     if state.data.get("non_consegnati") else ""))

    above = sorted([s for s in scored if s.totale > cfg.prezzo_max_eur], key=lambda s: s.totale)
    lines = [f"Offerte sopra {fmt_eur(cfg.prezzo_max_eur)}: {len(above)}"]
    for s in above[:3]:
        lines.append(f"- {truncate(s.offer.titolo, 70)}: {fmt_eur(s.totale)} su {names.get(s.offer.source_id, '')}")
    blocks.append("\n".join(lines))

    coming = [s for s in scored if s.offer.disponibilita == "in_arrivo"]
    lines = [f"Offerte in arrivo / preordine: {len(coming)}"]
    for s in sorted(coming, key=lambda s: s.totale)[:5]:
        lines.append(f"- {truncate(s.offer.titolo, 70)}: {fmt_eur(s.totale)} su {names.get(s.offer.source_id, '')}")
    blocks.append("\n".join(lines))

    unknown = [s for s in scored if s.offer.disponibilita in ("sconosciuta", "non_disponibile")
               and s.totale <= cfg.prezzo_max_eur]
    blocks.append(f"Offerte sotto soglia ma non disponibili o da verificare: {len(unknown)}")

    title = f"[REPORT] Monitor PS5 – {now.astimezone(ROME).strftime('%d/%m/%Y')}"
    return Message(kind="report", title=title, blocks=blocks, priority=2, tags=["bar_chart"], silent=True)
