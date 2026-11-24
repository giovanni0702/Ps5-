"""Strumenti comuni dei test: fonte finta, notificatore finto, orologio controllato."""
import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from ps5monitor.config import load_config
from ps5monitor.models import Offer
from ps5monitor.runner import Monitor
from ps5monitor.sources.base import Source
from ps5monitor.state import State

T0 = datetime(2026, 11, 24, 13, 0, tzinfo=timezone.utc)   # 14:00 ora di Roma


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, **kw):
        self.t += timedelta(**kw)


class FakeSource(Source):
    id = "negozio_test"
    nome = "Negozio Test"
    tipo = "retailer"
    dominio = "negozio.test"

    def __init__(self, cfg, offers=None, verify_override=None):
        super().__init__(cfg, None)
        self.offers = offers or []
        self.verify_override = verify_override
        self.verify_calls = 0

    def enabled(self):
        return True

    def fetch_offers(self, config=None, cycle=0, rr_index=0, deadline=None):
        return [copy.deepcopy(o) for o in self.offers]

    def verify(self, offer, deadline=None):
        self.verify_calls += 1
        if self.verify_override is not None:
            return copy.deepcopy(self.verify_override)
        for o in self.offers:
            if o.offer_id == offer.offer_id:
                v = copy.deepcopy(o)
                v.verificata_su_pagina_prodotto = True
                return v
        return None


class FakeNotifier:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    def send(self, msg, only=None):
        if self.fail:
            return {"ntfy": (False, "errore simulato")}
        self.sent.append(msg)
        return {"ntfy": (True, "inviato")}


def alerts(notifier):
    """Solo gli avvisi di offerte (esclusi report, avvio, allarmi)."""
    return [m for m in notifier.sent if m.kind in ("sconto", "disponibile")]


def make_offer(oid="1", prezzo="499.00", disp="disponibile", **kw):
    base = dict(source_id="negozio_test", offer_id=oid, url_canonico=f"https://negozio.test/p/{oid}",
                titolo="Sony PlayStation 5 Slim Standard", prezzo=D(prezzo), modello="standard_disc",
                condizione="nuovo", disponibilita=disp, venditore="Negozio Test", venditore_tipo="negozio",
                spedizione_eur=D("0"), verificata_su_pagina_prodotto=True, rilevata_il=T0)
    base.update(kw)
    return Offer(**base)


@pytest.fixture
def cfg():
    return load_config("config.yaml")


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def harness(cfg, clock):
    """Restituisce una funzione che crea (monitor, fonte, notificatore) con stato già avviato."""
    def build(offers=None, started=True, state=None, fail=False, verify_override=None):
        st = state or State()
        if started:
            st.data["avviato"] = True
            st.data["avviato_il"] = T0.isoformat()
            st.data["ultimo_report"] = "2026-11-24"   # niente report giornaliero negli scenari
        src = FakeSource(cfg, offers, verify_override)
        notifier = FakeNotifier(fail)
        mon = Monitor(cfg, st, [src], notifier, now=clock, out=lambda s: None)
        return mon, src, notifier
    return build
