"""Test di is_console (R2.7): 30 console valide e 30 titoli non validi, con commento."""
from decimal import Decimal

import pytest

from ps5monitor.classify import detect_bundle, detect_condition, detect_model, is_console
from ps5monitor.config import load_config

CFG = load_config("config.yaml")


def check(titolo, prezzo, categoria=""):
    return is_console(
        titolo, Decimal(prezzo), categoria,
        forti=CFG.parole_escluse_forti, deboli=CFG.parole_escluse_deboli,
        difetto=CFG.parole_difetto, prezzo_min=CFG.prezzo_min_console_eur,
    )


# (titolo, prezzo, categoria, commento)
POSITIVI = [
    ("PlayStation 5 Standard con controller DualSense", "549.99", "", "controller introdotto da 'con' dopo la console"),
    ("PS5 Slim con lettore disco 1 TB SSD", "499.00", "", "'lettore disco' non è esclusione, SSD dopo la console"),
    ("PS5 Slim + gioco", "529.00", "", "gioco introdotto da '+'"),
    ("PS5 Digital + Disc Drive", "529.00", "", "Digital con modulo lettore in bundle"),
    ("Console PS5 Slim 1TB", "479.00", "", "titolo semplice con 'console'"),
    ("Sony PlayStation 5 Digital Edition Slim", "399.99", "", "Digital Slim"),
    ("Sony PlayStation 5 Pro 2TB", "799.99", "", "Pro (sopra soglia ma è console)"),
    ("PS5 Pro Console 2 TB SSD", "749.00", "", "Pro con SSD dopo la console"),
    ("Console PlayStation®5 Slim Standard Edition", "549.99", "", "simbolo registrato"),
    ("Sony PS5 Slim Digital - Bianco", "429.00", "", "Digital con colore"),
    ("PlayStation 5 Console (Ricondizionato)", "389.00", "", "ricondizionata"),
    ("PS5 Slim Standard - Ricondizionato Eccellente", "419.00", "", "ricondizionata Back Market"),
    ("PlayStation 5 usata perfettamente funzionante", "330.00", "", "usata da privato"),
    ("Ps5 usata come nuova con scontrino", "350.00", "", "usata 'come nuova'"),
    ("PS5 Slim Digital + EA Sports FC 26 Bundle", "449.00", "", "bundle con gioco"),
    ("Console PS5 Slim + Call of Duty Black Ops 7 (codice digitale)", "529.00", "", "bundle con codice gioco"),
    ("PlayStation 5 CFI-2016 Slim", "469.00", "", "codice CFI-2xxx"),
    ("Sony CFI-7016 2TB", "759.00", "", "codice CFI-7xxx = Pro"),
    ("CFI-1216A PlayStation 5 Standard", "450.00", "", "codice CFI-1xxx"),
    ("PlayStation5 Slim 1TB Chassis D", "499.00", "", "'playstation5' attaccato"),
    ("PS-5 Slim Digital Edition", "399.00", "", "trattino nel pattern"),
    ("Sony PlayStation 5 Slim Console - Edizione Fortnite Cobalt Star Bundle", "479.00", "", "bundle edizione speciale"),
    ("PS5 Slim Disc + 2 Controller DualSense", "599.00", "", "controller aggiuntivo introdotto da '+'"),
    ("Console Sony PS5 Slim Standard incluso Astro Bot", "529.00", "", "gioco introdotto da 'incluso'"),
    ("Sony PlayStation 5 Slim (Renewed)", "409.00", "", "Amazon Renewed"),
    ("PS5 Slim Digital Edition 1TB - Usato - Ottimo", "350.00", "", "usato Rebuy"),
    ("PlayStation 5 Slim Edition Standard", "549.99", "Videogiochi > PlayStation 5 > Console", "breadcrumb con 'Console' nella foglia"),
    ("PS5 Slim con base di ricarica e 2 controller", "579.00", "", "accessori introdotti da 'con'"),
    ("PlayStation 5 Pro Console + Gran Turismo 7", "829.00", "", "Pro + gioco"),
    ("PS5 Slim Standard con stand verticale", "559.00", "", "stand introdotto da 'con'"),
]

NEGATIVI = [
    ("Controller DualSense per console PS5", "69.99", "", "controller con 'console' nel titolo"),
    ("SSD 2 TB per PS5", "189.00", "", "SSD prima della console"),
    ("Modulo disc drive per PS5 Digital", "119.99", "", "prezzo sotto soglia"),
    ("Sony DualSense Edge Controller wireless PS5", "229.00", "", "DualSense Edge"),
    ("Cuffie Sony Pulse 3D Wireless per PS5", "99.00", "", "cuffie Pulse"),
    ("Sony PlayStation Portal Remote Player per PS5", "219.99", "", "Portal"),
    ("Samsung 990 Pro SSD 2TB con dissipatore compatibile con PS5", "179.00", "", "SSD compatibile"),
    ("Cover PS5 Slim Digital Midnight Black", "54.99", "", "cover"),
    ("Base di ricarica DualSense per PS5", "34.99", "", "base di ricarica"),
    ("Marvel's Spider-Man 2 gioco per PS5", "59.99", "", "gioco 'per PS5'"),
    ("Abbonamento PlayStation Plus Premium 12 mesi PS5", "151.99", "", "abbonamento"),
    ("PS5 per ricambi non si accende", "120.00", "", "per ricambi"),
    ("Scatola vuota PS5 originale", "15.00", "", "scatola vuota"),
    ("Controller wireless compatibile console PS5 nero", "39.00", "", "accessorio con 'console'"),
    ("PS5 Slim scheda madre non funzionante", "180.00", "", "difetto dichiarato"),
    ("Sony PlayStation VR2 per PS5", "399.00", "", "VR2"),
    ("PlayStation VR2 Horizon Call of the Mountain bundle PS5", "449.00", "", "VR2 bundle"),
    ("Stand verticale per PS5 Slim con ventola di raffreddamento", "29.99", "", "stand"),
    ("Custodia rigida da viaggio per console PS5 Portal", "24.99", "", "custodia"),
    ("Hard disk esterno 4TB per PS5 e PS4", "119.00", "", "hard disk prima della console"),
    ("Cavo HDMI 2.1 8K per PS5", "12.99", "", "cavo"),
    ("Alimentatore di ricambio PS5 ADP-400DR", "49.90", "", "alimentatore"),
    ("PS5 Media Remote Sony", "29.99", "", "telecomando media remote"),
    ("Gift Card PSN 50 euro PS5", "50.00", "", "gift card"),
    ("EA Sports FC 26 Standard Edition PS5", "69.99", "", "gioco senza 'console' (prezzo basso)"),
    ("Faceplate PS5 Slim Volcanic Red", "64.99", "", "faceplate"),
    ("PS5 Slim Standard bloccata ban", "280.00", "", "difetto 'bloccata'"),
    ("Ventola di raffreddamento esterna PS5", "25.00", "", "ventola"),
    ("PS5 DualSense Wireless Controller Cosmic Red", "74.99", "", "controller dopo la console senza 'con'"),
    ("Grand Theft Auto VI PS5", "79.99", "Videogiochi > PS5 > Giochi", "categoria foglia 'Giochi'"),
]


@pytest.mark.parametrize("titolo,prezzo,categoria,commento", POSITIVI)
def test_positivi_singoli(titolo, prezzo, categoria, commento):
    ok, motivo = check(titolo, prezzo, categoria)
    assert motivo
    assert ok, f"{titolo!r} ({commento}) scartato: {motivo}"


@pytest.mark.parametrize("titolo,prezzo,categoria,commento", NEGATIVI)
def test_negativi_singoli(titolo, prezzo, categoria, commento):
    ok, motivo = check(titolo, prezzo, categoria)
    assert motivo.startswith("esclusa")
    assert not ok, f"{titolo!r} ({commento}) accettato per errore"


def test_criterio_complessivo():
    assert len(POSITIVI) == 30 and len(NEGATIVI) == 30
    falsi_positivi = [t for t, p, c, _ in NEGATIVI if check(t, p, c)[0]]
    riconosciuti = [t for t, p, c, _ in POSITIVI if check(t, p, c)[0]]
    assert falsi_positivi == []
    assert len(riconosciuti) >= 28


def test_stand_non_corrisponde_a_standard():
    assert check("PS5 Standard Edition", "549.99")[0]


def test_motivo_parola_esclusa():
    ok, motivo = check("Controller DualSense per console PS5", "300")
    assert not ok and "controller" in motivo


def test_difetto_motivo():
    ok, motivo = check("PS5 Slim per ricambi", "300")
    assert not ok and "difetto dichiarato" in motivo


def test_prezzo_sotto_minimo():
    assert not check("PS5 Slim Digital", "249.99")[0]
    assert check("PS5 Slim Digital", "250.00")[0]


def test_categoria_solo_ultimo_livello():
    assert check("PlayStation 5 Slim", "499", "Videogiochi > PlayStation 5 > Console")[0]
    assert check("PlayStation 5 Slim", "499", "Console")[0]
    assert not check("PlayStation 5 Slim", "499", "Accessori")[0]


@pytest.mark.parametrize("titolo,atteso", [
    ("Sony PlayStation 5 Pro 2TB", "pro"),
    ("Sony CFI-7016", "pro"),
    ("PS5 Slim Digital Edition", "digital"),
    ("PS5 Digital + Disc Drive", "digital"),
    ("PS5 Slim con lettore disco", "standard_disc"),
    ("PlayStation 5 Standard", "standard_disc"),
    ("PS5 Slim 1TB", "standard_disc"),
    ("PS5 Slim Digital o Standard", "sconosciuto"),
    ("PlayStation 5", "sconosciuto"),
    ("PlayStation 5 Edizione Limitata 30° Anniversario", "altro_console"),
])
def test_modello(titolo, atteso):
    assert detect_model(titolo) == atteso


def test_condizione():
    assert detect_condition("PS5 Slim (Renewed)", False) == "ricondizionato"
    assert detect_condition("PS5 usata", False) == "usato"
    assert detect_condition("PS5 come nuova", False, "privato") == "usato"
    assert detect_condition("PS5 Slim", True) == "nuovo"
    assert detect_condition("PS5 Slim", False) == "sconosciuta"
    assert detect_condition("PS5 Slim", False, dichiarata="ricondizionato") == "ricondizionato"


def test_bundle():
    assert "gioco" in detect_bundle("PS5 Slim + gioco")
    assert "Astro Bot" in detect_bundle("Console Sony PS5 Slim Standard incluso Astro Bot")
    assert detect_bundle("PS5 Slim con lettore disco 1 TB SSD") == ""
    assert detect_bundle("Console PS5 Slim 1TB") == ""
