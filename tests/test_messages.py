"""Snapshot dei messaggi (R5.8) e formati (R5.3, R5.6, R5.7).

Per rigenerare i file di riferimento dopo una modifica voluta: PS5_AGGIORNA_SNAPSHOT=1 pytest tests/test_messages.py
"""
import os
from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path

import pytest
from conftest import T0, make_offer

from ps5monitor.messages import alert_message, batch_message, fmt_age, fmt_dt, offer_block, truncate
from ps5monitor.models import NegozioMilano
from ps5monitor.notify import split_message
from ps5monitor.pricing import score

SNAP = Path(__file__).parent / "snapshots"
NOW = T0 + timedelta(seconds=40)


def check_snapshot(name, text):
    path = SNAP / name
    if os.environ.get("PS5_AGGIORNA_SNAPSHOT") or not path.exists():
        path.write_text(text + "\n", encoding="utf-8")
    assert text + "\n" == path.read_text(encoding="utf-8")


@pytest.fixture
def lcfg(cfg):
    cfg.listino_ufficiale = {"standard_disc": D("549.99"), "digital": D("449.99"), "pro": D("799.99")}
    return cfg


def test_snapshot_p1_amazon(lcfg):
    o = make_offer(source_id="amazon", oid="B0TEST0001", titolo="Sony PlayStation 5 Digital Edition Slim",
                   modello="digital", prezzo="399.00", prezzo_barrato=D("449.99"), venditore="Amazon",
                   venditore_tipo="amazon", consegna_testo="Consegna GRATUITA giovedì 26 novembre",
                   url_canonico="https://www.amazon.it/dp/B0TEST0001")
    sc = score(o, lcfg)
    assert sc.priorita == 1
    msg = alert_message(sc, offer_block(sc, NOW, "Amazon.it", events=["nuova_disponibile"]), "Amazon.it")
    assert msg.title == "[SCONTO -11,3%] PS5 Digital a 399,00 € su Amazon.it"
    assert msg.priority == 5 and msg.click == "https://www.amazon.it/dp/B0TEST0001"
    check_snapshot("p1_amazon.txt", msg.title + "\n\n" + msg.text())


def test_snapshot_p3_ritiro_milano(lcfg):
    o = make_offer(source_id="mediaworld", oid="1000001", titolo="Sony PlayStation 5 Slim Standard Edition",
                   prezzo="549.99", canale="entrambi", venditore="MediaWorld", garanzia_testo="Garanzia legale 24 mesi",
                   url_canonico="https://www.mediaworld.it/it/product/_sony-playstation-5-slim-standard-1000001.html",
                   negozi_milano=[NegozioMilano("Negozio Test Milano Centro", "Milano", "", D("1.3"), "Ritiro in 30 minuti"),
                                  NegozioMilano("Negozio Test Assago", "Assago", "", D("7.2"), "Ritiro domani")])
    sc = score(o, lcfg)
    assert sc.priorita == 3
    block = offer_block(sc, NOW, "MediaWorld", has_physical_stores=True, events=["nuova_disponibile"])
    msg = batch_message([(sc, block, "MediaWorld")], 0)
    assert msg.title == "[DISPONIBILE] PS5 Standard a 549,99 € su MediaWorld"
    check_snapshot("p3_ritiro_milano.txt", msg.title + "\n\n" + msg.text())


def test_snapshot_p4_ebay_privato(lcfg):
    o = make_offer(source_id="ebay", oid="222222222222", titolo="PS5 Standard con lettore usata poco, perfetta",
                   prezzo="340.00", spedizione_eur=D("12.00"), condizione="usato", venditore="utente_test",
                   venditore_tipo="privato", feedback_pct=D("100"), feedback_n=12,
                   url_canonico="https://www.ebay.it/itm/222222222222")
    sc = score(o, lcfg)
    assert sc.priorita == 4
    block = offer_block(sc, NOW, "eBay.it", events=["nuova_disponibile"])
    msg = batch_message([(sc, block, "eBay.it")], 0)
    check_snapshot("p4_ebay_privato.txt", msg.title + "\n\n" + msg.text())


def test_fallback_negozi(lcfg):
    sc = score(make_offer(source_id="unieuro"), lcfg)
    b = offer_block(sc, NOW, "Unieuro", has_physical_stores=True,
                    chain_stores=[{"nome": "Unieuro Test", "comune": "Milano", "telefono": "02 0000009"}])
    assert "Disponibilità nei negozi di Milano non verificabile dal sito: verifica per telefono" in b
    assert "tel. 02 0000009" in b


def test_formati():
    assert fmt_dt(T0) == "24/11/2026 14:00"
    assert fmt_age(40) == "40 secondi fa" and fmt_age(60) == "1 minuto fa" and fmt_age(7200) == "2 ore fa"
    t = truncate("x" * 130)
    assert len(t) == 120 and t.endswith("…")


def test_divisione_messaggi_lunghi(lcfg):
    items = []
    for i in range(10):
        sc = score(make_offer(oid=str(i), titolo="PlayStation 5 " + "molto lungo " * 9), lcfg)
        items.append((sc, offer_block(sc, NOW, "Negozio Test"), "Negozio Test"))
    msg = batch_message(items, 3)
    parts = split_message(msg, 4096, lambda s: len(s.encode("utf-8")))
    assert len(parts) >= 2
    assert all(len(t.encode()) <= 4096 for _, t in parts)
    joined = "".join(t for _, t in parts)
    assert [joined.find(f"/p/{i}") for i in range(10)] == sorted(joined.find(f"/p/{i}") for i in range(10))
    assert parts[-1][1].endswith("+3 altre offerte") and parts[0][0].endswith("(1/%d)" % len(parts))
