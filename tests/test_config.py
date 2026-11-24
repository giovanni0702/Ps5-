"""Validazione di config.yaml con messaggi in italiano (G7)."""
import copy

import pytest
import yaml

from ps5monitor.config import ConfigError, load_config, parse_config

RAW = yaml.safe_load(open("config.yaml", encoding="utf-8"))

CHIAVI_MINIME = ["prezzo_max_eur", "prezzo_min_console_eur", "modelli_ammessi", "condizioni_ammesse", "marketplace",
                 "soglia_sconto_pct", "listino_ufficiale", "soglia_prezzo_sospetto_pct", "fattore_riferimento_max",
                 "delta_prezzo_min_eur", "delta_prezzo_min_pct", "cooldown_minuti", "durata_run_secondi",
                 "intervallo_ciclo_secondi", "intervallo_dominio_secondi", "area", "notifiche",
                 "parole_escluse_forti", "parole_escluse_deboli", "parole_difetto", "fonti"]


def test_config_predefinita_valida():
    cfg = load_config("config.yaml")
    assert str(cfg.prezzo_max_eur) == "700" and cfg.canali == ["ntfy"]
    assert cfg.citta == "Milano" and cfg.raggio_km == 20
    assert len(cfg.fonti) == 17
    assert cfg.listino_ufficiale == {"standard_disc": None, "digital": None, "pro": None}
    for k in CHIAVI_MINIME:
        assert k in RAW
    for sc in RAW["fonti"].values():
        assert set(sc) == {"abilitata", "prodotti", "ricerca", "ricerca_ogni_cicli"}


@pytest.mark.parametrize("path,valore,frammento", [
    (["prezzo_max_eur"], "tanti", "'prezzo_max_eur' ha valore 'tanti'"),
    (["prezzo_max_eur"], -5, "maggiore di zero"),
    (["modelli_ammessi"], ["ps6"], "'modelli_ammessi' ha valore 'ps6'"),
    (["notifiche", "canali"], ["whatsapp"], "i valori ammessi sono: ntfy, telegram, email"),
    (["notifiche", "report_ora"], "9 di mattina", "notifiche.report_ora"),
    (["intervallo_dominio_secondi"], 5, "deve essere almeno 30"),
    (["fonti", "amazon", "abilitata"], "si", "'fonti.amazon.abilitata'"),
    (["area", "lat"], 300, "'area.lat'"),
    (["listino_ufficiale", "pro"], "caro", "'listino_ufficiale.pro'"),
])
def test_errori_chiari(path, valore, frammento):
    raw = copy.deepcopy(RAW)
    d = raw
    for k in path[:-1]:
        d = d[k]
    d[path[-1]] = valore
    with pytest.raises(ConfigError) as e:
        parse_config(raw)
    assert frammento in str(e.value)
    assert str(e.value).startswith("Errore in config.yaml")


def test_chiave_mancante():
    raw = copy.deepcopy(RAW)
    del raw["cooldown_minuti"]
    with pytest.raises(ConfigError, match="manca la chiave 'cooldown_minuti'"):
        parse_config(raw)


def test_yaml_rotto(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("prezzo_max_eur: [700\n")
    with pytest.raises(ConfigError, match="formato non valido"):
        load_config(p)
