"""Testo degli avvisi, del messaggio di avvio, del report giornaliero e dell'allarme (R4.7, R5, R10.5)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from .alerts import EVENT_LABELS
from .pricing import Scored, fmt_eur, fmt_pct
from .sources.amazon import cart_url, dp_url

ROME = ZoneInfo("Europe/Rome")
TITLE_MAX = 120

MODEL_LONG = {
    "standard_disc": "PS5 Standard (con lettore)", "digital": "PS5 Digital", "pro": "PS5 Pro",
    "altro_console": "PS5 (altra versione)", "sconosciuto": "PS5 (modello non indicato)",
}
MODEL_SHORT = {"standard_disc": "PS5 Standard", "digital": "PS5 Digital", "pro": "PS5 Pro",
               "altro_console": "PS5", "sconosciuto": "PS5"}
COND = {"nuovo": "nuovo", "ricondizionato": "ricondizionato", "usato": "usato", "sconosciuta": "condizione non indicata"}
REF_SRC = {"dichiarato": "prezzo barrato dichiarato dal negozio", "storico": "mediana dei prezzi degli ultimi 30 giorni",
           "listino": "listino ufficiale"}
PRIO_LABEL = {
    1: "P1 · SCONTO · negozio o Amazon", 2: "P2 · SCONTO · venditore terzo o privato",
    3: "P3 · DISPONIBILE · negozio o Amazon", 4: "P4 · DISPONIBILE · venditore terzo o privato",
}
FALLBACK_STORES = "Disponibilità nei negozi di Milano non verificabile dal sito: verifica per telefono"


@dataclass
class Message:
    kind: str                     # sconto, disponibile, avvio, report, allarme, prova
    title: str
    blocks: list[str]
    header: str = ""
    footer: str = ""
    priority: int = 3             # priorità ntfy (5 = alta)
    click: str | None = None
    tags: list[str] = field(default_factory=list)
    silent: bool = False

    def text(self, blocks: list[str] | None = None) -> str:
        parts = [p for p in (self.header, "\n\n".join(self.blocks if blocks is None else blocks), self.footer) if p]
        return "\n\n".join(parts)

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d: dict) -> "Message":
        return cls(**d)


def fmt_dt(dt: datetime) -> str:
    return dt.astimezone(ROME).strftime("%d/%m/%Y %H:%M")


def fmt_age(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 60:
        return f"{s} {'secondo' if s == 1 else 'secondi'} fa"
    if s < 3600:
        m = s // 60
        return f"{m} {'minuto' if m == 1 else 'minuti'} fa"
    h = s // 3600
    return f"{h} {'ora' if h == 1 else 'ore'} fa"


def truncate(text: str, n: int = TITLE_MAX) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def main_link(sc: Scored) -> str:
    o = sc.offer
    return dp_url(o.offer_id) if o.source_id == "amazon" else o.url_canonico


def offer_block(sc: Scored, now: datetime, source_name: str, has_physical_stores: bool = False,
                chain_stores: list[dict] | None = None, events: list[str] | None = None) -> str:
    """Blocco di un'offerta con tutti i campi di R5.1, nell'ordine richiesto."""
    o = sc.offer
    label = PRIO_LABEL.get(sc.priorita, "Non disponibile ora")
    if events:
        label += " · " + ", ".join(EVENT_LABELS.get(e, e) for e in events)
    lines = [label, truncate(o.titolo), f"Negozio: {source_name}",
             f"Modello: {MODEL_LONG[o.modello]} · Condizione: {COND[o.condizione]}"]
    if o.bundle:
        lines.append(f"Bundle: {o.bundle}")
    lines.append(f"Prezzo: {fmt_eur(o.prezzo)}")
    ref = sc.riferimento
    if ref.valore is not None and not sc.sconto_eur:
        lines.append(f"Prezzo di riferimento: {fmt_eur(ref.valore)} ({REF_SRC[ref.fonte]}) · nessuno sconto")
    elif ref.valore is not None:
        lines.append(f"Prezzo di riferimento: {fmt_eur(ref.valore)} ({REF_SRC[ref.fonte]}) · "
                     f"Sconto: {fmt_eur(sc.sconto_eur)} (-{fmt_pct(sc.sconto_pct)})")
    else:
        lines.append("Prezzo di riferimento: non disponibile · sconto non valutabile")
    if o.spedizione_eur is None:
        lines.append(f"Spedizione: da verificare · Prezzo totale (spedizione esclusa): {fmt_eur(sc.totale)}")
    elif o.spedizione_eur == 0:
        lines.append(f"Spedizione: gratuita · Prezzo totale: {fmt_eur(sc.totale)}")
    else:
        lines.append(f"Spedizione: {fmt_eur(o.spedizione_eur)} · Prezzo totale: {fmt_eur(sc.totale)}")
    disp = {"disponibile": "disponibile", "ultime_unita": "ultime unità", "non_disponibile": "non disponibile",
            "in_arrivo": "in arrivo (preordine)", "sconosciuta": "da verificare"}[o.disponibilita]
    if o.quantita_disponibile:
        disp += f" ({o.quantita_disponibile} {'pezzo' if o.quantita_disponibile == 1 else 'pezzi'})"
    lines.append(f"Disponibilità: {disp}")
    if o.consegna_testo:
        lines.append(f"Consegna/ritiro: {o.consegna_testo}")
    if o.garanzia_testo:
        lines.append(f"Garanzia: {o.garanzia_testo}")
    if o.venditore_tipo == "amazon":
        lines.append("Venditore: Amazon (venduto e spedito da Amazon)")
    elif o.venditore_tipo == "negozio":
        lines.append(f"Venditore: {o.venditore or source_name} (negozio)")
    else:
        tipo = "venditore terzo" if o.venditore_tipo == "terzo" else "privato"
        v = f"Venditore: {o.venditore or 'non indicato'}"
        if o.feedback_pct is not None and o.feedback_n is not None:
            n_txt = f"{o.feedback_n:,}".replace(",", ".")
            v += f", feedback {fmt_pct(o.feedback_pct)} su {n_txt} valutazioni"
        lines.append(f"{v} ({tipo})")
        lines.append("Venditore terzo: controlla garanzia, resi e pagamento protetto")
        if o.localita_annuncio:
            lines.append(f"Località annuncio: {o.localita_annuncio}")
    if o.ritiro_milano and o.negozi_milano:
        lines.append("Ritiro a Milano:")
        for n in o.negozi_milano:
            extra = f" · {n.tempi_ritiro}" if n.tempi_ritiro else ""
            km = f"{n.distanza_km:.1f}".replace(".", ",") if n.distanza_km is not None else "?"
            lines.append(f"  - {n.nome}, {n.comune}, {km} km{extra}")
    elif has_physical_stores:
        lines.append(FALLBACK_STORES)
        for s in (chain_stores or [])[:3]:
            if s.get("telefono"):
                lines.append(f"  - {s.get('nome')}, {s.get('comune')}: tel. {s['telefono']}")
    if "prezzo_sospetto" in o.flags:
        lines.append("⚠️ Possibile errore di prezzo o truffa: verifica prima di agire")
    if "da_verificare_sul_negozio" in o.flags:
        lines.append("⚠️ Da verificare sul negozio: offerta letta da un comparatore di prezzi")
    if "non_verificata" in o.flags:
        lines.append("⚠️ Dato non verificato: la fonte al momento non risponde")
    age = (now - o.rilevata_il).total_seconds()
    lines.append(f"Rilevata il {fmt_dt(o.rilevata_il)} (ora di Roma), rilevata {fmt_age(age)}")
    lines.append(f"Link: {main_link(sc)}")
    if o.source_id == "amazon":
        lines.append(f"Aggiungi al carrello: {cart_url(o.offer_id)}")
    return "\n".join(lines)


def offer_title(sc: Scored, source_name: str) -> str:
    what = f"{MODEL_SHORT[sc.offer.modello]} a {fmt_eur(sc.totale)} su {source_name}"
    if sc.priorita in (1, 2):
        return f"[SCONTO -{fmt_pct(sc.sconto_pct)}] {what}"
    return f"[DISPONIBILE] {what}"


def alert_message(sc: Scored, block: str, source_name: str) -> Message:
    """Messaggio dedicato a un'offerta P1/P2 (R4.4)."""
    return Message(kind="sconto", title=offer_title(sc, source_name), blocks=[block], priority=5,
                   click=main_link(sc), tags=["rotating_light"], silent=False)


def batch_message(items: list[tuple[Scored, str, str]], overflow: int) -> Message:
    """Messaggio P3/P4 di fine ciclo: al massimo 10 offerte, le altre in "+N altre offerte" (R4.3)."""
    best, _, name = items[0]
    title = offer_title(best, name)
    if len(items) + overflow > 1:
        title += f" +{len(items) + overflow - 1} altre"
    footer = f"+{overflow} altre offerte" if overflow else ""
    return Message(kind="disponibile", title=title, blocks=[b for _, b, _ in items], footer=footer,
                   priority=3, click=main_link(best), tags=["video_game"], silent=True)


def startup_message(items: list[tuple[Scored, str, str]], overflow: int) -> Message:
    if not items:
        return Message(kind="avvio", title="[AVVIO] Monitor avviato",
                       blocks=["Nessuna offerta sotto il prezzo massimo al momento."],
                       header="Il monitor PS5 è attivo e controlla le fonti abilitate.", priority=3, tags=["white_check_mark"])
    return Message(kind="avvio", title="[AVVIO] Monitor avviato", header="Il monitor PS5 è attivo. Offerte attuali:",
                   blocks=[b for _, b, _ in items], footer=f"+{overflow} altre" if overflow else "",
                   priority=3, click=main_link(items[0][0]), tags=["white_check_mark"])


def blind_alarm_message(minutes: int) -> Message:
    return Message(kind="allarme", title="[ALLARME] Monitor cieco",
                   blocks=[f"Nessuna fonte risponde correttamente da circa {minutes} minuti: in questo momento "
                           "il monitor non vede le offerte. Controlla la tabella delle fonti con il workflow "
                           "\"monitor\" e l'opzione \"diagnostica\" (vedi SETUP.md, \"Se qualcosa non va\")."],
                   priority=4, tags=["warning"])


def prova_message(now: datetime) -> Message:
    return Message(kind="prova", title="[PROVA] Notifica di prova del monitor PS5",
                   blocks=[f"Se leggi questo messaggio il canale funziona. Inviato il {fmt_dt(now)} (ora di Roma)."],
                   priority=3, tags=["white_check_mark"])
