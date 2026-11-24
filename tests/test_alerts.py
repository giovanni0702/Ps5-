"""Scenari degli avvisi (R4.8), stato vecchio (R6.7), soglia (R7.6), marketplace (R9.6), verifica (R4.5)."""
from datetime import timedelta
from decimal import Decimal as D

from conftest import T0, alerts, make_offer

from ps5monitor.alerts import alert_eligible, validate_offer
from ps5monitor.config import load_config
from ps5monitor.fixture_mode import FIXTURE_DIR, fixture_setup
from ps5monitor.pricing import score, sort_key
from ps5monitor.sources import ALL_SOURCES
from ps5monitor.state import State


def run(mon, src, clock, offers, minutes=1):
    src.offers = offers
    clock.advance(minutes=minutes)
    mon.cycle()


# --- R4.8: ogni scenario dichiara il numero esatto di avvisi attesi -------------------------

def test_scenario_nuova_offerta(harness, clock):
    mon, src, n = harness([make_offer()])
    mon.cycle()
    assert len(alerts(n)) == 1                      # atteso: 1 avviso
    assert alerts(n)[0].title == "[DISPONIBILE] PS5 Standard a 499,00 € su Negozio Test"


def test_scenario_stesso_prezzo_ripetuto(harness, clock):
    mon, src, n = harness([make_offer()])
    mon.cycle()
    for _ in range(5):
        run(mon, src, clock, [make_offer()])
    assert len(alerts(n)) == 1                      # atteso: 1 (solo il primo)


def test_scenario_calo_10_euro(harness, clock):
    mon, src, n = harness([make_offer(prezzo="499.00")])
    mon.cycle()
    run(mon, src, clock, [make_offer(prezzo="489.00")])
    assert len(alerts(n)) == 2                      # atteso: 2 (nuova + calo, anche nel cooldown)
    assert "489,00 €" in alerts(n)[1].title


def test_scenario_calo_3_euro(harness, clock):
    mon, src, n = harness([make_offer(prezzo="489.00")])
    mon.cycle()
    run(mon, src, clock, [make_offer(prezzo="486.00")], minutes=200)
    assert len(alerts(n)) == 1                      # atteso: 1 (3 € e 0,6% sotto i delta)


def test_scenario_esaurita_e_tornata(harness, clock):
    mon, src, n = harness([make_offer()])
    mon.cycle()
    run(mon, src, clock, [make_offer(disp="non_disponibile")])
    assert not mon.state.record("negozio_test:1")["esaurita"]   # 1 solo controllo: non ancora esaurita
    run(mon, src, clock, [make_offer(disp="non_disponibile")])
    assert mon.state.record("negozio_test:1")["esaurita"]
    run(mon, src, clock, [make_offer()], minutes=130)
    assert len(alerts(n)) == 2                      # atteso: 2 (nuova + tornata disponibile)
    assert "tornata disponibile" in alerts(n)[1].blocks[0]


def test_scenario_flapping_non_genera_tornata(harness, clock):
    mon, src, n = harness([make_offer()])
    mon.cycle()
    run(mon, src, clock, [make_offer(disp="non_disponibile")], minutes=130)
    run(mon, src, clock, [make_offer()])
    assert len(alerts(n)) == 1                      # atteso: 1 (un solo "non disponibile" non basta)


def test_scenario_sconto_che_compare(harness, clock, cfg):
    cfg.listino_ufficiale["standard_disc"] = D("549.99")
    mon, src, n = harness([make_offer(prezzo="540.00")])
    mon.cycle()
    assert alerts(n)[0].kind == "disponibile"       # sconto 1,8%: non in sconto, P3
    run(mon, src, clock, [make_offer(prezzo="499.00")])
    assert len(alerts(n)) == 2                      # atteso: 2
    m = alerts(n)[1]
    assert m.kind == "sconto" and m.priority == 5
    assert m.title == "[SCONTO -9,3%] PS5 Standard a 499,00 € su Negozio Test"


def test_scenario_sopra_700(harness, clock):
    mon, src, n = harness([make_offer(prezzo="750.00")])
    mon.cycle()
    assert len(alerts(n)) == 0                      # atteso: 0
    assert mon.state.record("negozio_test:1")      # ma resta nello stato (R7.3)


def test_scenario_12_offerte(harness, clock):
    offers = [make_offer(oid=str(i), prezzo=str(450 + i)) for i in range(12)]
    mon, src, n = harness(offers)
    mon.cycle()
    assert len(alerts(n)) == 1                      # atteso: 1 messaggio con 10 offerte
    m = alerts(n)[0]
    assert len(m.blocks) == 10 and m.footer == "+2 altre offerte" and m.title.endswith("+11 altre")
    assert mon.state.data["coda"] == ["negozio_test:10", "negozio_test:11"]
    assert mon.state.record("negozio_test:11")["notificato_il"] is None
    run(mon, src, clock, offers)
    assert len(alerts(n)) == 2                      # atteso: 2 (il secondo con le 2 escluse)
    assert len(alerts(n)[1].blocks) == 2 and "461,00 €" in alerts(n)[1].blocks[1]


def test_scenario_primo_avvio_zero_offerte(harness):
    mon, src, n = harness([], started=False)
    mon.cycle()
    assert len(n.sent) == 1                         # atteso: 1 messaggio [AVVIO]
    assert n.sent[0].title == "[AVVIO] Monitor avviato"
    assert "Nessuna offerta sotto il prezzo massimo al momento" in n.sent[0].text()
    assert not mon.state.is_new


def test_primo_avvio_con_offerte(harness, clock, cfg):
    cfg.listino_ufficiale["standard_disc"] = D("549.99")
    offers = [make_offer(oid="a", prezzo="469.00"), make_offer(oid="b", prezzo="520.00"),
              make_offer(oid="c", prezzo="800.00")]
    mon, src, n = harness(offers, started=False)
    mon.cycle()
    assert len(n.sent) == 1 and n.sent[0].kind == "avvio"   # nessun invio immediato P1
    assert len(n.sent[0].blocks) == 2                       # 800 € escluso
    run(mon, src, clock, offers)
    assert len(alerts(n)) == 0                              # già notificate all'avvio


def test_p1_messaggio_dedicato_immediato(harness, clock, cfg):
    cfg.listino_ufficiale["digital"] = D("449.99")
    mon, src, n = harness([make_offer(oid="d", prezzo="399.00", modello="digital", titolo="PS5 Digital"),
                           make_offer(oid="e", prezzo="499.00")])
    mon.cycle()
    kinds = [m.kind for m in alerts(n)]
    assert kinds == ["sconto", "disponibile"]       # P1 subito, P3 a fine ciclo


# --- R6.7: esecuzione saltata, stato vecchio di 3 ore ------------------------------------

def test_stato_vecchio_tre_ore(cfg, clock, harness):
    mon, src, n = harness([make_offer(prezzo="499.00")])
    mon.cycle()
    saved = State(mon.state.data)
    clock.advance(hours=3)
    mon2, src2, n2 = harness([make_offer(prezzo="480.00")], state=saved)
    mon2.cycle()
    mon2.cycle()
    assert len(alerts(n2)) == 1                     # una sola volta
    assert "480,00 €" in alerts(n2)[0].title


# --- R7.6: confini di prezzo -------------------------------------------------------------

def test_soglia_700(harness, clock):
    cases = [
        (make_offer(oid="a", prezzo="700.00"), 1),
        (make_offer(oid="b", prezzo="700.01"), 0),
        (make_offer(oid="c", prezzo="699.99", spedizione_eur=D("5.00")), 0),
        (make_offer(oid="d", prezzo="249.99", titolo="PS5 Slim Digital"), 0),
        (make_offer(oid="e", prezzo="699.00", spedizione_eur=None), 1),
    ]
    mon, src, n = harness([o for o, _ in cases])
    mon.cycle()
    m = alerts(n)[0]
    assert len(m.blocks) == 2
    assert any("700,00 €" in b for b in m.blocks)
    flagged = next(b for b in m.blocks if "699,00 €" in b)
    assert "Spedizione: da verificare" in flagged
    rec = mon.state.record("negozio_test:e")
    assert "spedizione_da_verificare" in rec["offerta"]["flags"]
    assert mon.state.record("negozio_test:d") is None     # 249,99 €: non è console
    assert any("sotto il minimo" in r for _, _, r in mon.log.scartate)


def test_valuta_e_prezzo_non_leggibile(cfg):
    assert validate_offer(make_offer(valuta="GBP"), cfg) == (False, "valuta_non_eur")
    o = make_offer()
    o.prezzo = None
    assert validate_offer(o, cfg) == (False, "prezzo_non_leggibile")


# --- R4.5: verifica sulla pagina prodotto ------------------------------------------------

def test_verifica_non_confermata(harness, clock):
    o = make_offer(verificata_su_pagina_prodotto=False)
    mon, src, n = harness([o], verify_override=make_offer(prezzo="519.00"))
    mon.cycle()
    assert src.verify_calls == 1
    assert len(alerts(n)) == 0 and mon.log.non_confermate


def test_verifica_confermata(harness):
    mon, src, n = harness([make_offer(verificata_su_pagina_prodotto=False)])
    mon.cycle()
    assert src.verify_calls == 1 and len(alerts(n)) == 1


def test_nessuna_verifica_se_letta_su_pagina_prodotto(harness):
    mon, src, n = harness([make_offer()])
    mon.cycle()
    assert src.verify_calls == 0


# --- R9.6: tre fixture marketplace -------------------------------------------------------

def test_marketplace_r96():
    cfg, fetcher = fixture_setup(load_config("config.yaml"))
    amazon = ALL_SOURCES["amazon"](cfg, fetcher)
    a = amazon.parse_product((FIXTURE_DIR / "amazon_prodotto_B0TEST0002.html").read_text(),
                             "https://www.amazon.it/dp/B0TEST0002")[0]
    sa = score(a, cfg)
    assert sa.in_sconto and sa.priorita == 2 and alert_eligible(sa, cfg, "marketplace")[0]

    ebay = ALL_SOURCES["ebay"](cfg, fetcher)
    e = ebay.parse_product((FIXTURE_DIR / "ebay_prodotto_111111111111.html").read_text(),
                           "https://www.ebay.it/itm/111111111111")[0]
    se = score(e, cfg)
    assert e.venditore_tipo == "terzo" and se.priorita == 2 and alert_eligible(se, cfg, "marketplace")[0]

    subito = ALL_SOURCES["subito"](cfg, fetcher)
    s = next(o for o in subito.fetch_offers(cfg) if o.offer_id == "90000001")
    ss = score(s, cfg)
    assert s.venditore_tipo == "privato" and ss.priorita == 4
    assert alert_eligible(ss, cfg, "classificati") == (False, "solo_ritiro_fuori_raggio")
    vicino = next(o for o in subito.fetch_offers(cfg) if o.offer_id == "90000005")
    assert alert_eligible(score(vicino, cfg), cfg, "classificati")[0]   # Rho, solo ritiro nel raggio
    senza_foto = next(o for o in subito.fetch_offers(cfg) if o.offer_id == "90000003")
    assert validate_offer(senza_foto, cfg) == (False, "annuncio privato senza foto")
    ricambi = next(o for o in subito.fetch_offers(cfg) if o.offer_id == "90000004")
    assert not validate_offer(ricambi, cfg)[0]


def test_preferenze_marketplace(cfg):
    o = make_offer(venditore_tipo="terzo")
    cfg.venditori_terzi = False
    assert alert_eligible(score(o, cfg), cfg) == (False, "venditori_terzi_non_ammessi")
    cfg.marketplace_ammessi = False
    assert alert_eligible(score(make_offer(), cfg), cfg, "marketplace")[0] is False
    cfg.modelli_ammessi = ["pro"]
    assert alert_eligible(score(make_offer(), cfg), cfg) == (False, "modello_non_ammesso")


def test_privato_massimo_p2(cfg):
    cfg.listino_ufficiale["standard_disc"] = D("549.99")
    s = score(make_offer(prezzo="300.00", venditore_tipo="privato", condizione="usato",
                         prezzo_barrato=D("420.00")), cfg)
    assert s.sconto_pct > D("25") and s.priorita == 2


# --- R8.6: ordinamento a parità di sconto ------------------------------------------------

def test_ordinamento_ritiro_milano_prima(cfg):
    a = score(make_offer(oid="a", prezzo="499.00"), cfg)
    b = score(make_offer(oid="b", prezzo="499.00", canale="entrambi"), cfg)
    assert [s.offer.offer_id for s in sorted([a, b], key=sort_key)] == ["b", "a"]


# --- R10.4: avvisi non consegnati -------------------------------------------------------

def test_non_consegnato_e_riprovato(harness, clock):
    mon, src, n = harness([make_offer()], fail=True)
    mon.cycle()
    assert len(mon.state.data["non_consegnati"]) == 1 and mon.log.non_consegnati == 1
    n.fail = False
    run(mon, src, clock, [make_offer()])
    assert mon.state.data["non_consegnati"] == []
    assert len(alerts(n)) == 1                      # consegnato al ciclo dopo, una volta sola


# --- R1.5 / R1.6: stati delle fonti -----------------------------------------------------

def test_fonte_in_errore_non_ferma_le_altre(cfg, clock):
    from conftest import FakeNotifier, FakeSource
    from ps5monitor.runner import Monitor

    class Broken(FakeSource):
        id = "rotta"
        dominio = "rotta.test"

        def fetch_offers(self, *a, **k):
            raise ValueError("pagina cambiata")

    st = State()
    st.data.update(avviato=True, ultimo_report="2026-11-24", avviato_il=T0.isoformat())
    good = FakeSource(cfg, [make_offer()])
    n = FakeNotifier()
    mon = Monitor(cfg, st, [Broken(cfg), good], n, now=clock, out=lambda s: None)
    for _ in range(3):
        mon.cycle()
        clock.advance(minutes=1)
    assert st.source("rotta")["stato"] == "degradata"
    assert st.source("negozio_test")["stato"] == "ok"
    assert len(alerts(n)) == 1


def test_fonte_bloccata_backoff(cfg, clock):
    st = State()
    st.source_blocked("x", "HTTP 403", T0)
    assert st.source("x")["stato"] == "bloccata"
    assert not st.source_can_run("x", T0 + timedelta(minutes=29))
    assert st.source_can_run("x", T0 + timedelta(minutes=30))
    st.source_blocked("x", "HTTP 403", T0 + timedelta(minutes=30))
    assert st.source("x")["bloccata_fino"] == (T0 + timedelta(minutes=90)).isoformat()
    for _ in range(5):
        st.source_blocked("x", "HTTP 429", T0)
    assert st.source("x")["bloccata_fino"] == (T0 + timedelta(minutes=240)).isoformat()
    st.source_ok("x", 3, T0)
    assert st.source("x")["stato"] == "ok" and st.source("x")["livello_blocco"] == 0
    assert [t["a"] for t in st.data["transizioni"]] == ["bloccata", "ok"]


def test_da_riparare_dopo_24_ore(clock):
    st = State()
    st.source_ok("x", 5, T0)
    st.source_ok("x", 0, T0 + timedelta(hours=23))
    assert st.source("x")["stato"] == "ok"
    st.source_ok("x", 0, T0 + timedelta(hours=24))
    assert st.source("x")["stato"] == "da_riparare"
    st.source_ok("x", 2, T0 + timedelta(hours=25))
    assert st.source("x")["stato"] == "ok"


def test_offerte_non_verificate_se_fonte_in_errore(harness, clock):
    mon, src, n = harness([make_offer()])
    mon.cycle()
    mon.state.mark_unverified("negozio_test")
    assert "non_verificata" in mon.state.offer_of("negozio_test:1").flags
