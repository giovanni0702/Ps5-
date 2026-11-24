"""Test degli adapter su fixture sintetiche, senza rete (G8, R1.7, R8.6, R9.6)."""
from decimal import Decimal as D

import pytest

from ps5monitor.config import load_config
from ps5monitor.fixture_mode import FIXTURE_DIR, fixture_setup
from ps5monitor.http import BlockedError, detect_block
from ps5monitor.sources import ALL_SOURCES, build_sources
from ps5monitor.sources.base import canonical_url


@pytest.fixture
def env():
    cfg, fetcher = fixture_setup(load_config("config.yaml"))
    return cfg, fetcher


def src(env, sid):
    cfg, fetcher = env
    return ALL_SOURCES[sid](cfg, fetcher)


def html(name):
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_registro_metadati():
    assert len(ALL_SOURCES) == 17
    for sid, cls in ALL_SOURCES.items():
        assert cls.id == sid and cls.nome and cls.dominio
        assert cls.tipo in ("retailer", "marketplace", "aggregatore", "classificati")
    assert ALL_SOURCES["mediaworld"].solo_nuovo and not ALL_SOURCES["amazon"].solo_nuovo
    assert not ALL_SOURCES["trovaprezzi"].solo_nuovo


def test_canonical_url():
    u = canonical_url("https://www.Example.it/p/1?utm_source=x&ref=y&tag=aff-21&colore=nero#top")
    assert u == "https://www.example.it/p/1?colore=nero"


def test_retailer_mediaworld_ricerca(env):
    offers = src(env, "mediaworld").fetch_offers(env[0])
    titoli = [o.titolo for o in offers]
    assert "Sony PlayStation 5 Slim Standard Edition" in titoli
    o = offers[0]
    assert o.offer_id == "1000001" and o.prezzo == D("499.00")
    assert "utm_source" not in o.url_canonico
    assert o.disponibilita == "sconosciuta"  # in ricerca non c'è il pulsante di acquisto
    assert o.condizione == "nuovo" and o.modello == "standard_disc"


def test_retailer_negozi_milano_r86(env):
    s = src(env, "mediaworld")
    o = s.parse_product(html("mediaworld_prodotto_1000001.html"),
                        "https://www.mediaworld.it/it/product/_sony-playstation-5-slim-standard-1000001.html")[0]
    assert o.disponibilita == "disponibile" and o.verificata_su_pagina_prodotto
    assert o.canale == "entrambi"
    assert [n.nome for n in o.negozi_milano] == ["Negozio Test Milano Centro", "Negozio Test Assago"]
    assert o.negozi_milano[0].distanza_km == D("1.3")
    assert o.negozi_milano[1].distanza_km == D("7.2")
    assert o.categoria == "Console PS5" and o.garanzia_testo.startswith("Garanzia")
    assert o.spedizione_eur == D("0.00")


def test_retailer_senza_negozi(env):
    o = src(env, "unieuro").parse_product(html("unieuro_prodotto_2000001.html"), "https://www.unieuro.it/x")[0]
    assert o.canale == "spedizione" and o.negozi_milano == []
    assert o.prezzo_barrato == D("479.99") and o.spedizione_eur is None


def test_preordine_in_arrivo(env):
    o = src(env, "gamestop").fetch_offers(env[0])[0]
    assert o.disponibilita == "in_arrivo"


def test_amazon_ricerca_e_prodotto(env):
    s = src(env, "amazon")
    offers = s.fetch_offers(env[0])
    assert [o.offer_id for o in offers] == ["B0TEST0001", "B0TEST0002", "B0TEST0003", "B0TEST0004"]
    assert offers[0].url_canonico == "https://www.amazon.it/dp/B0TEST0001"
    v = s.verify(offers[0])
    assert v.venditore_tipo == "amazon" and v.disponibilita == "disponibile"
    assert v.prezzo == D("469.00") and v.prezzo_barrato == D("499.99") and v.spedizione_eur == D("0.00")
    assert v.categoria == "Console" and v.modello == "digital"


def test_amazon_marketplace_terzo_r96(env):
    s = src(env, "amazon")
    v = s.parse_product(html("amazon_prodotto_B0TEST0002.html"), "https://www.amazon.it/dp/B0TEST0002")[0]
    assert v.venditore_tipo == "terzo" and v.venditore == "GiochiTest Srl"
    assert v.disponibilita == "ultime_unita" and v.quantita_disponibile == 2


def test_marketplace_ebay(env):
    offers = src(env, "ebay").fetch_offers(env[0])
    by = {o.offer_id: o for o in offers}
    assert by["111111111111"].venditore_tipo == "terzo"
    assert by["111111111111"].feedback_pct == D("99.6") and by["111111111111"].feedback_n == 2345
    assert by["111111111111"].titolo.startswith("Console Sony")
    assert by["222222222222"].venditore_tipo == "privato" and by["222222222222"].spedizione_eur == D("12.00")
    assert by["333333333333"].valuta == "GBP"
    assert by["111111111111"].url_canonico == "https://www.ebay.it/itm/111111111111"


def test_ebay_pagina_oggetto(env):
    s = src(env, "ebay")
    o = s.parse_product(html("ebay_prodotto_111111111111.html"), "https://www.ebay.it/itm/111111111111")[0]
    assert o.disponibilita == "disponibile" and o.condizione == "nuovo"
    assert o.prezzo_barrato == D("449.99") and o.venditore == "negoziotest_it"


def test_classificati_subito(env):
    offers = src(env, "subito").fetch_offers(env[0])
    by = {o.offer_id: o for o in offers}
    assert len(by) == 5
    bs = by["90000001"]
    assert bs.solo_ritiro and bs.venditore_tipo == "privato" and bs.localita_lat == pytest.approx(45.5416)
    assert by["90000002"].spedizione_eur == D("9.90") and by["90000002"].condizione == "usato"
    assert by["90000003"].ha_foto is False


def test_aggregatore_trovaprezzi(env):
    offers = src(env, "trovaprezzi").fetch_offers(env[0])
    assert len(offers) == 3
    shop = next(o for o in offers if o.venditore == "ShopTest Elettronica")
    assert shop.prezzo == D("419.90") and shop.spedizione_eur == D("9.90")
    assert shop.disponibilita == "disponibile" and "da_verificare_sul_negozio" in shop.flags
    assert not shop.verificata_su_pagina_prodotto
    assert next(o for o in offers if o.venditore.startswith("NegozioEsaurito")).disponibilita == "non_disponibile"


def test_blocco_captcha():
    assert detect_block(403, "") == "HTTP 403"
    assert detect_block(429, "") == "HTTP 429"
    assert detect_block(200, html("captcha.html"))
    assert detect_block(200, html("mediaworld_ricerca.html")) is None


def test_fixture_fetcher_blocco(env):
    _, fetcher = env
    fetcher.mapping["https://www.amazon.it/captcha"] = FIXTURE_DIR / "captcha.html"
    with pytest.raises(BlockedError):
        fetcher.get("https://www.amazon.it/captcha")


def test_build_sources_solo_una(env):
    cfg, fetcher = env
    assert [s.id for s in build_sources(cfg, fetcher, only="ebay")] == ["ebay"]


def test_pianificazione_round_robin():
    from ps5monitor.config import SourceConfig
    cfg = load_config("config.yaml")
    cfg.fonti["mediaworld"] = SourceConfig(True, ["https://a/1", "https://a/2"], "https://a/s", 5)
    s = ALL_SOURCES["mediaworld"](cfg, None)
    plans = [s.plan(c, c).url for c in range(5)]
    assert plans == ["https://a/1", "https://a/2", "https://a/1", "https://a/2", "https://a/s"]
    cfg.fonti["mediaworld"] = SourceConfig(True, [], "https://a/s", 5)
    assert s.plan(0, 0).mode == "ricerca"
