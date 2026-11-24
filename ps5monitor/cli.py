"""Riga di comando: python -m ps5monitor <comando> (R11.3). Tutti i messaggi sono in italiano."""
from __future__ import annotations

import argparse
import os
import secrets
import string
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .alerts import validate_offer
from .config import ConfigError, load_config
from .fixture_mode import fixture_setup
from .geo import load_stores
from .http import BlockedError, DomainScheduler, HttpFetcher
from .messages import prova_message
from .models import utcnow
from .notify import Notifier, mask
from .report import daily_report
from .runner import Monitor
from .sources import build_sources
from .state import State

STATE_LABEL = {"ok": "ok", "degradata": "degradata", "bloccata": "bloccata", "da_riparare": "da riparare",
               "disattivata": "disattivata", "errore": "errore"}


def _print(text: str) -> None:
    print(mask(text), flush=True)


def _summary(lines: list[str]) -> None:
    """Scrive nel riepilogo del workflow di GitHub Actions, se presente."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(mask("\n".join(lines)) + "\n")


def _load(args):
    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        _print(str(exc))
        sys.exit(2)
    return cfg


def _setup(args, cfg, state: State):
    stores = load_stores(args.negozi)
    if args.fixture:
        cfg, fetcher = fixture_setup(cfg)
    else:
        sched = DomainScheduler(cfg.intervallo_dominio_secondi, last=state.vol.get("domini"))
        fetcher = HttpFetcher(sched)
    return cfg, fetcher, stores


def _table(rows: list[tuple]) -> list[str]:
    out = ["| Fonte | Stato | Offerte trovate | Tempo di risposta (ms) |", "|---|---|---|---|"]
    out += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in rows]
    return out


# --- run -----------------------------------------------------------------------
def cmd_run(args) -> int:
    cfg = _load(args)
    if args.fixture:
        args.dry_run = True
        state = State()
        state.data.update(avviato=True, avviato_il=utcnow().isoformat(),
                          ultimo_report=utcnow().date().isoformat())
        _print("Modalità --fixture: pagine sintetiche di tests/fixtures, nessuna rete, nessun invio (--dry-run).")
    else:
        state = State.load(args.stato)
    cfg, fetcher, stores = _setup(args, cfg, state)
    notifier = Notifier(cfg, dry_run=args.dry_run, out=_print)
    missing = notifier.missing()
    for ch, why in missing.items():
        if not args.dry_run:
            _print(f"Errore canale {ch}: {why} (vedi SETUP.md, passo 3).")
    if missing and len(missing) == len(notifier.channels) and not args.dry_run:
        _print("Errore: nessun canale di notifica utilizzabile. Il monitor non parte.")
        return 1
    sources = build_sources(cfg, fetcher, stores, only=args.fonte)
    if args.fonte and not sources:
        _print(f"Errore: la fonte '{args.fonte}' non esiste in config.yaml.")
        return 2
    publisher = None
    if os.environ.get("PS5_PUBBLICA_STATO") == "1" and not args.dry_run:
        from .publish import publish_state
        publisher = publish_state
    mon = Monitor(cfg, state, sources, notifier, out=_print,
                  state_path=None if args.dry_run else args.stato, publisher=publisher, stores=stores,
                  immediate=not args.fixture)
    t0 = time.monotonic()
    logs = mon.run(once=args.once)
    elapsed = time.monotonic() - t0
    last = logs[-1]
    lines = [f"Cicli eseguiti: {len(logs)} in {elapsed:.0f} s",
             f"Messaggi inviati: {sum(l.inviati for l in logs)}",
             f"Avvisi non consegnati in attesa: {len(state.data['non_consegnati'])}"]
    rows = []
    for s in sources:
        n, ms = last.diag.get(s.id, ("-", "-"))
        stato = "disattivata" if not s.enabled() else state.data["fonti"].get(s.id, {}).get("stato", "ok")
        rows.append((s.nome, STATE_LABEL.get(stato, stato), n, ms))
    for line in lines:
        _print(line)
    if args.dry_run:
        scartate = [x for l in logs for x in l.scartate]
        if scartate:
            _print(f"Titoli scartati ({len(scartate)}):")
            for sid, titolo, motivo in scartate:
                _print(f"  - [{sid}] {titolo[:70]} → {motivo}")
        for sid, titolo in [x for l in logs for x in l.non_confermate]:
            _print(f"  - non_confermata [{sid}] {titolo[:70]}")
    _summary(["## Monitor PS5", *lines, "", *_table(rows)])
    return 0


# --- diagnostica ---------------------------------------------------------------
def cmd_diagnostica(args) -> int:
    cfg = _load(args)
    state = State.load(args.stato) if not args.fixture else State()
    cfg, fetcher, stores = _setup(args, cfg, state)
    sources = build_sources(cfg, fetcher, stores, only=args.fonte)

    def probe(s):
        if not s.enabled():
            return (s.nome, "disattivata", "-", "-")
        t0 = time.monotonic()
        try:
            offers = s.fetch_offers(cfg)
        except BlockedError as exc:
            return (s.nome, f"bloccata ({exc})", 0, int((time.monotonic() - t0) * 1000))
        except Exception as exc:
            return (s.nome, f"errore ({type(exc).__name__}: {str(exc)[:60]})", 0, int((time.monotonic() - t0) * 1000))
        ms = int((time.monotonic() - t0) * 1000)
        valid = [o for o in offers if validate_offer(o, cfg)[0]]
        stato = "ok" if valid else ("ok, 0 console riconosciute" if offers else "ok, 0 offerte lette (pagina cambiata?)")
        return (s.nome, stato, len(valid), ms)

    with ThreadPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(probe, sources))
    table = _table(rows)
    for line in table:
        _print(line)
    _summary(["## Diagnostica delle fonti", "", *table, "",
              "Nota: 'offerte trovate' conta solo le console vere riconosciute (accessori esclusi)."])
    return 0


# --- prova-notifica ------------------------------------------------------------
def cmd_prova(args) -> int:
    cfg = _load(args)
    notifier = Notifier(cfg, dry_run=args.dry_run, out=_print)
    results = notifier.send(prova_message(utcnow()))
    ok_all = True
    lines = []
    for ch, (ok, why) in results.items():
        lines.append(f"{ch}: {'inviato' if ok else 'fallito'}" + ("" if ok else f" ({why})"))
        ok_all &= ok
    for line in lines:
        _print(line)
    _summary(["## Prova notifica", *[f"- {line}" for line in lines]])
    return 0 if ok_all else 1


# --- scopri ----------------------------------------------------------------------
KNOWN_PHYSICAL = {"mediaworld", "unieuro", "euronics", "expert", "trony", "gamestop", "carrefour", "coop", "esselunga",
                  "comet", "bennet", "ipercoop", "auchan", "conad", "decathlon", "gamelife"}


def cmd_scopri(args) -> int:
    cfg = _load(args)
    cfg, fetcher, stores = _setup(args, cfg, State())
    sources = build_sources(cfg, fetcher, stores)
    known = {s.nome.lower().replace(".it", "").replace(" ", "") for s in sources}
    known |= {s.dominio.replace("www.", "").split(".")[0] for s in sources}
    found: dict[str, tuple[str, str]] = {}
    for s in sources:
        if s.tipo != "aggregatore" or not s.enabled():
            continue
        try:
            offers = s.fetch_offers(cfg)
        except Exception as exc:
            _print(f"{s.nome}: non raggiungibile ({type(exc).__name__})")
            continue
        for o in offers:
            if not validate_offer(o, cfg)[0]:
                continue
            seller = (o.venditore or "").strip()
            key = seller.lower().replace(".it", "").replace(" ", "")
            if not seller or key in known or any(k and k in key for k in known):
                continue
            found.setdefault(seller, (o.url_canonico, s.nome))
    lines = ["# Fonti candidate", "",
             "Negozi trovati sugli aggregatori che vendono PS5 e non sono ancora in config.yaml.",
             "Il monitor non abilita mai una fonte da solo: per aggiungerne una serve un nuovo adapter.", "",
             f"Ultimo aggiornamento: {utcnow().strftime('%d/%m/%Y %H:%M')} UTC", "",
             "| Negozio (dominio) | Esempio di URL | Trovato su | Ha negozi fisici |", "|---|---|---|---|"]
    for seller, (url, via) in sorted(found.items()):
        fisici = "sì" if any(k in seller.lower().replace(" ", "") for k in KNOWN_PHYSICAL) else "non so"
        lines.append(f"| {seller} | {url} | {via} | {fisici} |")
    if not found:
        lines.append("| (nessun negozio nuovo trovato in questa esecuzione) | | | |")
    Path(args.output).write_text("\n".join(lines) + "\n", encoding="utf-8")
    _print(f"Scritte {len(found)} fonti candidate in {args.output}")
    return 0


# --- genera-topic ----------------------------------------------------------------
def cmd_genera_topic(args) -> int:
    alphabet = string.ascii_lowercase + string.digits
    topic = "ps5-" + "".join(secrets.choice(alphabet) for _ in range(24))
    print("Valore per il secret NTFY_TOPIC (copialo senza spazi, non condividerlo):")
    print(topic)
    return 0


# --- report ---------------------------------------------------------------------
def cmd_report(args) -> int:
    cfg = _load(args)
    state = State.load(args.stato)
    cfg, fetcher, stores = _setup(args, cfg, state)
    msg = daily_report(state, cfg, utcnow(), build_sources(cfg, fetcher, stores))
    res = Notifier(cfg, dry_run=args.dry_run, out=_print).send(msg)
    if not args.dry_run:
        for ch, (ok, why) in res.items():
            _print(f"{ch}: {'inviato' if ok else f'fallito ({why})'}")
    return 0


# --- parser ----------------------------------------------------------------------
class _ItalianParser(argparse.ArgumentParser):
    def __init__(self, *a, **k):
        k.setdefault("add_help", False)
        super().__init__(*a, **k)
        self.add_argument("-h", "--help", action="help", help="mostra questo aiuto ed esce")

    def format_help(self):
        return (super().format_help().replace("usage:", "uso:")
                .replace("options:", "opzioni:").replace("positional arguments:", "argomenti:"))

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, f"Errore: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    p = _ItalianParser(prog="python -m ps5monitor",
                       description="Monitor delle offerte PS5 sui siti italiani. Avvisa sul telefono con ntfy.")
    sub = p.add_subparsers(dest="comando", metavar="COMANDO", parser_class=_ItalianParser)

    def common(sp, fixture=True, once=False):
        sp.add_argument("--config", default="config.yaml", help="file di configurazione (predefinito: config.yaml)")
        sp.add_argument("--stato", default="state.json", help="file dello stato (predefinito: state.json)")
        sp.add_argument("--negozi", default="data/negozi.yaml", help="elenco dei negozi di Milano")
        sp.add_argument("--dry-run", action="store_true", help="stampa i messaggi invece di inviarli")
        sp.add_argument("--fonte", metavar="ID", help="usa solo questa fonte (es. amazon)")
        if fixture:
            sp.add_argument("--fixture", action="store_true",
                            help="legge le pagine di prova in tests/fixtures invece della rete")
        if once:
            sp.add_argument("--once", action="store_true", help="esegue un solo ciclo e termina")

    sp = sub.add_parser("run", help="avvia il monitor (su GitHub resta attivo circa 4,5 minuti)",
                        description="Controlla le fonti a cicli e invia gli avvisi.")
    common(sp, once=True)
    sp.set_defaults(func=cmd_run)
    sp = sub.add_parser("diagnostica", help="prova ogni fonte una volta e stampa la tabella",
                        description="Tabella: fonte, stato, offerte trovate, tempo di risposta.")
    common(sp)
    sp.set_defaults(func=cmd_diagnostica)
    sp = sub.add_parser("prova-notifica", help="invia un messaggio di prova su tutti i canali attivi",
                        description="Invia una notifica di prova e stampa l'esito per canale.")
    common(sp, fixture=False)
    sp.set_defaults(func=cmd_prova)
    sp = sub.add_parser("scopri", help="cerca sugli aggregatori negozi non ancora in config.yaml",
                        description="Scrive FONTI_CANDIDATE.md. Non abilita mai una fonte da solo.")
    common(sp)
    sp.add_argument("--output", default="FONTI_CANDIDATE.md", help="file da scrivere")
    sp.set_defaults(func=cmd_scopri)
    sp = sub.add_parser("genera-topic", help="crea un valore casuale per il secret NTFY_TOPIC",
                        description="Stampa una stringa casuale da usare come NTFY_TOPIC.")
    sp.set_defaults(func=cmd_genera_topic)
    sp = sub.add_parser("report", help="invia (o stampa con --dry-run) il report giornaliero ora",
                        description="Report: stato delle fonti, offerte migliori, avvisi delle ultime 24 ore.")
    common(sp)
    sp.set_defaults(func=cmd_report)
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)
