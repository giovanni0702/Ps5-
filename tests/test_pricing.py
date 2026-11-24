"""Test di prezzi, sconto e priorità (G10, R3.7)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from ps5monitor.config import load_config
from ps5monitor.models import Offer
from ps5monitor.pricing import (discount, fmt_eur, fmt_pct, history_median, parse_price, priority,
                                prezzo_totale, reference_price, score, sort_key)


@pytest.fixture
def cfg():
    c = load_config("config.yaml")
    c.listino_ufficiale = {"standard_disc": D("549.99"), "digital": D("449.99"), "pro": D("799.99")}
    return c


def offer(**kw):
    base = dict(source_id="x", offer_id="1", url_canonico="https://e.it/p/1", titolo="PS5 Slim",
                prezzo=D("469.00"), modello="standard_disc", condizione="nuovo",
                disponibilita="disponibile", venditore_tipo="negozio", spedizione_eur=D("0"))
    base.update(kw)
    return Offer(**base)


@pytest.mark.parametrize("testo,atteso", [
    ("1.099,00 €", "1099.00"), ("€ 469", "469.00"), ("469,00", "469.00"), ("469.00", "469.00"),
    ("EUR 1.099", "1099.00"), ("549,99 €", "549.99"), (469, "469.00"), ("1,099.50", "1099.50"),
    ("Prezzo: 399,9 €", "399.90"),
])
def test_parse_price(testo, atteso):
    assert parse_price(testo) == D(atteso)


@pytest.mark.parametrize("testo", ["", "gratis", None, "n.d."])
def test_parse_price_non_leggibile(testo):
    assert parse_price(testo) is None


def test_formati():
    assert fmt_eur(D("469")) == "469,00 €"
    assert fmt_eur(D("1099")) == "1.099,00 €"
    assert fmt_eur(D("0.005")) == "0,01 €"  # ROUND_HALF_UP
    assert fmt_pct(D("14.65")) == "14,7%"


def test_r37_sconto_14_7(cfg):
    eur, pct = discount(D("469.00"), D("549.99"))
    assert eur == D("80.99") and pct == D("14.7")
    s = score(offer(), cfg)
    assert s.riferimento.fonte == "listino" and s.in_sconto and s.priorita == 1


def test_r37_sconto_5_5(cfg):
    eur, pct = discount(D("520.00"), D("549.99"))
    assert eur == D("29.99") and pct == D("5.5")
    assert score(offer(prezzo=D("520.00")), cfg).in_sconto


def test_r37_riferimento_gonfiato(cfg):
    o = offer(prezzo_barrato=D("700.00"))
    ref = reference_price(o, cfg, None)
    assert ref.fonte == "listino" and ref.valore == D("549.99")
    assert any("gonfiato" in n for n in ref.note)


def test_barrato_accettato(cfg):
    ref = reference_price(offer(prezzo_barrato=D("599.99")), cfg, None)
    assert ref.fonte == "dichiarato" and ref.valore == D("599.99")


def test_barrato_senza_listino(cfg):
    cfg.listino_ufficiale["digital"] = None
    o = offer(modello="digital", prezzo=D("400"), prezzo_barrato=D("700"))
    assert reference_price(o, cfg, None).fonte is None  # 700 > 1,5 × 400
    o = offer(modello="digital", prezzo=D("400"), prezzo_barrato=D("450"))
    assert reference_price(o, cfg, None).fonte == "dichiarato"


def test_r37_terzo_sempre_p2(cfg):
    s = score(offer(prezzo=D("330.00"), venditore_tipo="terzo"), cfg)
    assert s.sconto_pct >= D("40") and s.priorita == 2


def test_listino_non_usato_per_usato(cfg):
    s = score(offer(condizione="usato", venditore_tipo="privato"), cfg)
    assert s.riferimento.valore is None and not s.in_sconto and s.priorita == 4


def test_storico_mediana():
    now = datetime(2026, 11, 24, 12, tzinfo=timezone.utc)
    obs = [(now - timedelta(days=d, hours=1), D(p)) for d, p in
           [(1, "500"), (2, "510"), (3, "490"), (4, "520"), (5, "505")]]
    assert history_median(obs, now) == D("505.00")
    assert history_median(obs[:4], now) is None  # meno di 5
    recenti = [(now - timedelta(hours=h), D("500")) for h in range(1, 10)]
    assert history_median(recenti, now) is None  # tutte più recenti di 24 ore
    stesso_giorno = [(datetime(2026, 11, 20, h, tzinfo=timezone.utc), D("500")) for h in range(5)]
    assert history_median(stesso_giorno, now) is None  # un solo giorno di calendario


def test_storico_prima_del_listino(cfg):
    ref = reference_price(offer(), cfg, D("500.00"))
    assert ref.fonte == "storico"


def test_prezzo_sopra_riferimento(cfg):
    s = score(offer(prezzo=D("560")), cfg)
    assert s.sconto_eur == D("0.00") and not s.in_sconto and s.priorita == 3


def test_sconto_non_valutabile(cfg):
    cfg.listino_ufficiale["pro"] = None
    s = score(offer(modello="pro"), cfg)
    assert s.riferimento.valore is None and s.priorita == 3


def test_prezzo_sospetto(cfg):
    s = score(offer(prezzo=D("199.00")), cfg)
    assert "prezzo_sospetto" in s.offer.flags


def test_spedizione_ignota():
    o = offer(spedizione_eur=None, prezzo=D("699.00"))
    assert prezzo_totale(o) == D("699.00") and "spedizione_da_verificare" in o.flags


def test_priorita_non_disponibile():
    assert priority("in_arrivo", True, "negozio") is None
    assert priority("sconosciuta", True, "negozio") is None
    assert priority("ultime_unita", False, "amazon") == 3


def test_ordinamento_tre_offerte(cfg):
    a = score(offer(offer_id="a", prezzo=D("520.00")), cfg)                       # P1 5,5%
    b = score(offer(offer_id="b", prezzo=D("469.00")), cfg)                       # P1 14,7%
    c = score(offer(offer_id="c", prezzo=D("330.00"), venditore_tipo="terzo"), cfg)  # P2 40%
    assert [s.offer.offer_id for s in sorted([c, a, b], key=sort_key)] == ["b", "a", "c"]
