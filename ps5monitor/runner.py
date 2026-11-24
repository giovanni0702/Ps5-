"""Ciclo di controllo del monitor (R1.5, R1.6, R4, R6.2, R6.9, R10.4, R10.5)."""
from __future__ import annotations

import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Callable

from .alerts import alert_eligible, compute_events, cooldown_allows, validate_offer
from .http import BlockedError, BudgetExceeded, domain_of
from .messages import (ROME, Message, alert_message, batch_message, blind_alarm_message, offer_block,
                       startup_message)
from .models import Offer, utcnow
from .pricing import Scored, score, sort_key
from .report import daily_report
from .state import State, iso, parse_iso

MAX_PER_MESSAGE = 10
MAX_THREADS = 8
SOURCE_TIMEOUT_S = 60
BLIND_AFTER = timedelta(minutes=60)
BLIND_EVERY = timedelta(hours=6)


@dataclass
class CycleLog:
    scartate: list[tuple[str, str, str]] = field(default_factory=list)
    non_confermate: list[tuple[str, str]] = field(default_factory=list)
    errori: list[tuple[str, str]] = field(default_factory=list)
    diag: dict[str, tuple[int, int]] = field(default_factory=dict)
    inviati: int = 0
    non_consegnati: int = 0
    messaggi: list[Message] = field(default_factory=list)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower().replace(".it", ""))


class Monitor:
    def __init__(self, cfg, state: State, sources: list, notifier, *, now: Callable[[], datetime] = utcnow,
                 out: Callable[[str], None] = print, state_path: str | None = None,
                 publisher: Callable[[str], bool] | None = None, sleeper=time.sleep,
                 source_timeout: float = SOURCE_TIMEOUT_S, stores: dict | None = None):
        self.cfg = cfg
        self.state = state
        self.sources = sources
        self.notifier = notifier
        self.now = now
        self.out = out
        self.state_path = state_path
        self.publisher = publisher
        self.sleeper = sleeper
        self.source_timeout = source_timeout
        self.stores = stores or {}
        self.lock = threading.RLock()
        self.by_id = {s.id: s for s in sources}
        self.batch: list[tuple[Scored, list[str]]] = []
        self.log = CycleLog()
        self.run_logs: list[CycleLog] = []

    # --- esecuzione ----------------------------------------------------------
    def run(self, once: bool = False) -> list[CycleLog]:
        start = time.monotonic()
        while True:
            t0 = time.monotonic()
            self.run_logs.append(self.cycle())
            if once:
                break
            pause = self.cfg.intervallo_ciclo_secondi + random.uniform(-10, 10) - (time.monotonic() - t0)
            next_start = time.monotonic() - start + max(0.0, pause)
            if next_start + 30 > self.cfg.durata_run_secondi:
                break
            self.sleeper(max(0.0, pause))
        return self.run_logs

    def cycle(self) -> CycleLog:
        self.log = CycleLog()
        self.batch = []
        now = self.now()
        st = self.state
        cycle_no = st.vol.get("cicli", 0)
        st.vol["cicli"] = cycle_no + 1
        startup = st.is_new
        if not startup:
            self.retry_undelivered()
        # Un thread per dominio (al massimo 8 insieme), ogni fonte isolata (R1.6, R6.9)
        by_domain: dict[str, list] = {}
        for s in self.sources:
            by_domain.setdefault(s.dominio or s.id, []).append(s)
        deadline = time.time() + self.source_timeout
        if by_domain:
            ex = ThreadPoolExecutor(max_workers=min(MAX_THREADS, len(by_domain)))
            futures = [ex.submit(self._run_domain, srcs, cycle_no, deadline, startup) for srcs in by_domain.values()]
            done, pending = wait(futures, timeout=self.source_timeout + 20)
            for f in pending:
                self.log.errori.append(("?", "tempo massimo del ciclo superato"))
            ex.shutdown(wait=False, cancel_futures=True)
        now = self.now()
        if startup:
            self._send_startup(now)
            st.data["avviato"] = True
            st.data.setdefault("avviato_il", iso(now))
        else:
            self._send_batch(now)
            self._maybe_daily_report(now)
            self._maybe_blind_alarm(now)
        st.prune(now)
        self._persist(now)
        return self.log

    def _run_domain(self, srcs, cycle_no, deadline, startup):
        for s in srcs:
            try:
                self.process_source(s, cycle_no, deadline, startup)
            except Exception as exc:  # nessun adapter ferma gli altri (R1.6)
                with self.lock:
                    self.log.errori.append((s.id, f"errore inatteso: {type(exc).__name__}"))
                    self.state.source_error(s.id, f"errore inatteso: {type(exc).__name__}", self.now())
                    self.state.mark_unverified(s.id)

    # --- una fonte -----------------------------------------------------------
    def score(self, o: Offer) -> Scored:
        with self.lock:
            median = self.state.median_for(o.source_id, o.modello, o.condizione, self.now())
        return score(o, self.cfg, median)

    def _covered_by_source(self, seller: str) -> str | None:
        n = _norm(seller)
        for s in self.sources:
            if s.tipo != "aggregatore" and s.enabled() and n and (_norm(s.nome) == n or _norm(s.dominio) == n
                                                                  or _norm(s.dominio.replace("www.", "")) == n):
                return s.id
        return None

    def process_source(self, src, cycle_no: int, deadline: float, startup: bool) -> None:
        st, sid = self.state, src.id
        now = self.now()
        if not src.enabled():
            with self.lock:
                st.source_disabled(sid, now)
            return
        with self.lock:
            if not st.source_can_run(sid, now):
                return
            rr = st.vol["rr"].get(sid, 0)
            self._sync_domain_clock(src, load=True)
        t0 = time.monotonic()
        try:
            offers = src.fetch_offers(self.cfg, cycle=cycle_no, rr_index=rr, deadline=deadline)
        except BudgetExceeded:
            return
        except BlockedError as exc:
            with self.lock:
                st.source_blocked(sid, str(exc), now)
                st.mark_unverified(sid)
                self.log.errori.append((sid, f"bloccata: {exc}"))
                self.log.diag[sid] = (0, int((time.monotonic() - t0) * 1000))
            return
        except Exception as exc:
            with self.lock:
                motivo = f"{type(exc).__name__}: {exc}"[:200]
                st.source_error(sid, motivo, now)
                st.mark_unverified(sid)
                self.log.errori.append((sid, motivo))
                self.log.diag[sid] = (0, int((time.monotonic() - t0) * 1000))
            return
        ms = int((time.monotonic() - t0) * 1000)
        with self.lock:
            st.vol["rr"][sid] = rr + 1
        valid = []
        for o in offers:
            ok, why = validate_offer(o, self.cfg)
            if ok and src.tipo == "aggregatore":
                cov = self._covered_by_source(o.venditore)
                if cov:
                    ok, why = False, f"già controllata dalla fonte {cov}"
            if not ok:
                with self.lock:
                    self.log.scartate.append((sid, o.titolo, why))
                continue
            valid.append(o)
        with self.lock:
            st.source_ok(sid, len(valid), now)
            self.log.diag[sid] = (len(valid), ms)

        ready: list[tuple[Scored, list[str]]] = []
        needs: list[Scored] = []
        to_check: list[Scored] = []
        for o in valid:
            sc, events, why = self._ingest(src, o, now)
            if events:
                if self._needs_verification(src, sc):
                    needs.append(sc)
                else:
                    ready.append((sc, events))
            elif why == "non_disponibile" and o.disponibilita == "sconosciuta" and sc.totale <= self.cfg.prezzo_max_eur \
                    and src.can_verify(o) and not o.verificata_su_pagina_prodotto:
                to_check.append(sc)

        # Slot riservato alla verifica (R4.5, R6.9): 1 richiesta per dominio per ciclo.
        target, is_alert = None, False
        if needs:
            target, is_alert = sorted(needs, key=sort_key)[0], True
        elif to_check:
            with self.lock:
                checked = st.vol.setdefault("controllo", {})
                target = min(to_check, key=lambda s: checked.get(s.key, ""))
                checked[target.key] = iso(now)
        if target is not None:
            verified = self._verify(src, target, deadline, now)
            if verified is not None:
                vsc, vevents = verified
                if is_alert:
                    same_price = abs(vsc.offer.prezzo - target.offer.prezzo) <= Decimal("0.01")
                    if same_price and vsc.offer.disponibile and vevents:
                        ready.append((vsc, vevents))
                    else:
                        with self.lock:
                            self.log.non_confermate.append((sid, target.offer.titolo))
                elif vevents:
                    ready.append((vsc, vevents))
            elif is_alert:
                with self.lock:
                    self.log.non_confermate.append((sid, target.offer.titolo))
        for sc, events in ready:
            self._dispatch(sc, events, startup)
        with self.lock:
            self._sync_domain_clock(src, load=False)

    def _sync_domain_clock(self, src, load: bool) -> None:
        """Ricorda l'ora dell'ultima richiesta per dominio anche tra due esecuzioni (G4)."""
        sched = getattr(self.sources[0].fetcher, "scheduler", None) if self.sources else None
        if sched is None:
            return
        doms = self.state.vol["domini"]
        if load:
            for d, t in doms.items():
                sched.last[d] = max(sched.last.get(d, 0), t)
        else:
            doms.update(sched.last)

    def _needs_verification(self, src, sc: Scored) -> bool:
        return not sc.offer.verificata_su_pagina_prodotto and src.can_verify(sc.offer)

    def _ingest(self, src, o: Offer, now: datetime) -> tuple[Scored, list[str], str]:
        sc = self.score(o)
        with self.lock:
            rec, _ = self.state.upsert(o, sc.totale, sc.in_sconto, sc.priorita, now)
            ok, why = alert_eligible(sc, self.cfg, src.tipo)
            events = compute_events(rec, sc, self.cfg) if ok else []
        return sc, events, why

    def _verify(self, src, target: Scored, deadline: float, now: datetime):
        try:
            v = src.verify(target.offer, deadline)
        except BudgetExceeded:
            return None
        except BlockedError as exc:
            with self.lock:
                self.state.source_blocked(src.id, str(exc), now)
            return None
        except Exception as exc:
            with self.lock:
                self.log.errori.append((src.id, f"verifica: {type(exc).__name__}"))
            return None
        if v is None:
            return None
        ok, why = validate_offer(v, self.cfg)
        if not ok:
            with self.lock:
                self.log.scartate.append((src.id, v.titolo, why))
            return None
        if v.offer_id != target.offer.offer_id:
            v.offer_id = target.offer.offer_id
        sc, events, _ = self._ingest(src, v, now)
        return sc, events

    # --- invio ---------------------------------------------------------------
    def _block(self, sc: Scored, now: datetime, events: list[str] | None = None) -> str:
        src = self.by_id.get(sc.offer.source_id)
        name = src.nome if src else sc.offer.source_id
        chain = self.stores.get(getattr(src, "catena", None) or "", []) if src else []
        return offer_block(sc, now, name, bool(src and src.ha_negozi_fisici), chain, events)

    def _name(self, sc: Scored) -> str:
        src = self.by_id.get(sc.offer.source_id)
        return src.nome if src else sc.offer.source_id

    def _dispatch(self, sc: Scored, events: list[str], startup: bool) -> None:
        now = self.now()
        with self.lock:
            rec = self.state.record(sc.key)
            if startup:
                self.batch.append((sc, events))
                return
            if not cooldown_allows(rec, sc, events, self.cfg, now):
                return
            if sc.priorita not in (1, 2):
                self.batch.append((sc, events))
                return
        # P1/P2: messaggio dedicato, subito, senza aspettare le altre fonti (R4.4)
        msg = alert_message(sc, self._block(sc, now, events), self._name(sc))
        self.deliver(msg)
        with self.lock:
            self.state.mark_notified(rec, sc.totale, sc.priorita, sc.in_sconto, now)

    def deliver(self, msg: Message) -> bool:
        results = self.notifier.send(msg)
        failed = [ch for ch, (ok, _) in results.items() if not ok]
        with self.lock:
            self.log.messaggi.append(msg)
            if failed:
                self.state.data["non_consegnati"].append({"msg": msg.to_dict(), "canali": failed,
                                                         "creato": iso(self.now())})
                self.log.non_consegnati += 1
                for ch in failed:
                    self.out(f"Invio non riuscito su {ch}: {results[ch][1]}")
            if len(failed) < len(results):
                self.log.inviati += 1
        return not failed

    def retry_undelivered(self) -> None:
        pending = self.state.data["non_consegnati"]
        keep = []
        for entry in pending:
            res = self.notifier.send(Message.from_dict(entry["msg"]), only=entry["canali"])
            failed = [ch for ch, (ok, _) in res.items() if not ok]
            if failed:
                entry["canali"] = failed
                keep.append(entry)
        self.state.data["non_consegnati"] = keep

    def _items(self, entries, now):
        return [(sc, self._block(sc, now, ev), self._name(sc)) for sc, ev in entries]

    def _send_batch(self, now: datetime) -> None:
        coda = set(self.state.data.get("coda", []))
        uniq: dict[str, tuple[Scored, list[str]]] = {}
        for sc, ev in self.batch:
            uniq[sc.key] = (sc, ev)
        entries = sorted(uniq.values(), key=lambda x: (0 if x[0].key in coda else 1, sort_key(x[0])))
        top, rest = entries[:MAX_PER_MESSAGE], entries[MAX_PER_MESSAGE:]
        self.state.data["coda"] = [sc.key for sc, _ in rest]   # R4.3: non notificate, al prossimo ciclo per prime
        if not top:
            return
        self.deliver(batch_message(self._items(top, now), len(rest)))
        with self.lock:
            for sc, _ in top:
                self.state.mark_notified(self.state.record(sc.key), sc.totale, sc.priorita, sc.in_sconto, now)

    def _send_startup(self, now: datetime) -> None:
        uniq = {sc.key: (sc, None) for sc, _ in self.batch}
        entries = sorted(uniq.values(), key=lambda x: sort_key(x[0]))
        top, rest = entries[:MAX_PER_MESSAGE], entries[MAX_PER_MESSAGE:]
        self.deliver(startup_message(self._items(top, now), len(rest)))
        for sc, _ in top:
            self.state.mark_notified(self.state.record(sc.key), sc.totale, sc.priorita, sc.in_sconto, now)
        self.state.data["coda"] = [sc.key for sc, _ in rest]

    def _maybe_daily_report(self, now: datetime) -> None:
        local = now.astimezone(ROME)
        h, m = self.cfg.report_hour_minute
        today = local.date().isoformat()
        if (local.hour, local.minute) >= (h, m) and self.state.data.get("ultimo_report") != today:
            self.deliver(daily_report(self.state, self.cfg, now, self.sources))
            self.state.data["ultimo_report"] = today

    def _maybe_blind_alarm(self, now: datetime) -> None:
        st = self.state
        if not any(s.enabled() for s in self.sources):
            return
        last_ok = parse_iso(st.vol.get("ultimo_ok")) or parse_iso(st.data.get("avviato_il"))
        if last_ok is None or now - last_ok <= BLIND_AFTER:
            return
        last_alarm = parse_iso(st.data.get("ultimo_allarme_cieco"))
        if last_alarm and now - last_alarm < BLIND_EVERY:
            return
        self.deliver(blind_alarm_message(int((now - last_ok).total_seconds() // 60)))
        st.data["ultimo_allarme_cieco"] = iso(now)

    # --- salvataggio (R6.3) ---------------------------------------------------
    def _persist(self, now: datetime) -> None:
        if not self.state_path:
            return
        changed = self.state.needs_publish(now)
        self.state.save(self.state_path)
        if changed and self.publisher:
            if self.publisher(self.state_path):
                self.state.mark_published()
            else:
                self.out("Attenzione: stato non pubblicato dopo 3 tentativi (riprovo al ciclo successivo).")
        elif changed:
            self.state.mark_published()
