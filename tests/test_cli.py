"""Riga di comando (R1.4, R1.7, R6.8, R10.2, R10.3, R11.3)."""
import re
import subprocess
import sys
import time

import pytest

from ps5monitor.cli import build_parser, main

COMANDI = ["run", "diagnostica", "prova-notifica", "scopri", "genera-topic", "report"]


def test_run_fixture_sotto_60_secondi(capsys):
    t0 = time.monotonic()
    assert main(["run", "--once", "--dry-run", "--fixture"]) == 0
    assert time.monotonic() - t0 < 60
    out = capsys.readouterr().out
    titles = re.findall(r"^\[(SCONTO|DISPONIBILE)[^\n]*", out, re.M)
    assert titles[:3] == ["SCONTO", "SCONTO", "SCONTO"] and titles[-1] == "DISPONIBILE"
    avvisi = out.split("Cicli eseguiti")[0]
    for vietato in ("DualSense Controller", "Cuffie", "Cover per", "Base di ricarica", "per ricambi"):
        assert vietato not in avvisi
    blocks = [b for b in avvisi.split("\n\n") if b.startswith("P")]
    assert blocks
    for b in blocks:
        for campo in ("Negozio:", "Modello:", "Prezzo:", "Prezzo di riferimento:", "Spedizione:",
                      "Disponibilità:", "Venditore:", "Rilevata il", "(ora di Roma)", "Link: https://"):
            assert campo in b, f"manca {campo} in:\n{b}"
    assert "Aggiungi al carrello: https://www.amazon.it/gp/aws/cart/add.html?ASIN.1=B0TEST0001&Quantity.1=1" in out


def test_python_m_funziona():
    r = subprocess.run([sys.executable, "-m", "ps5monitor", "--help"], capture_output=True, text=True)
    assert r.returncode == 0 and "uso:" in r.stdout


@pytest.mark.parametrize("cmd", COMANDI)
def test_help_in_italiano(cmd, capsys):
    with pytest.raises(SystemExit):
        build_parser().parse_args([cmd, "--help"])
    out = capsys.readouterr().out
    assert "uso:" in out and "mostra questo aiuto" in out


def test_opzioni_run(capsys):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["run", "--help"])
    out = capsys.readouterr().out
    for opt in ("--dry-run", "--once", "--fonte", "--fixture"):
        assert opt in out


def test_genera_topic(capsys):
    main(["genera-topic"])
    topic = capsys.readouterr().out.strip().splitlines()[-1]
    assert re.fullmatch(r"ps5-[a-z0-9]{24}", topic)


def test_prova_notifica_senza_secret(capsys, monkeypatch):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    assert main(["prova-notifica"]) == 1
    assert "ntfy: fallito (manca il secret NTFY_TOPIC)" in capsys.readouterr().out


def test_run_senza_secret_errore_chiaro(capsys, monkeypatch, tmp_path):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    assert main(["run", "--once", "--stato", str(tmp_path / "s.json")]) == 1
    out = capsys.readouterr().out
    assert "manca il secret NTFY_TOPIC" in out and "Traceback" not in out


def test_diagnostica_fixture_e_summary(capsys, monkeypatch, tmp_path):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert main(["diagnostica", "--fixture"]) == 0
    out = capsys.readouterr().out
    assert "| Fonte | Stato | Offerte trovate | Tempo di risposta (ms) |" in out
    assert re.search(r"\| Amazon\.it \| ok \| 3 \|", out)
    assert "| Fnac | disattivata |" in out
    assert "Diagnostica delle fonti" in summary.read_text()


def test_scopri_fixture(tmp_path, capsys):
    out_file = tmp_path / "cand.md"
    assert main(["scopri", "--fixture", "--output", str(out_file)]) == 0
    text = out_file.read_text()
    assert "ShopTest Elettronica" in text and "Amazon.it |" not in text


def test_report_dry_run(capsys, tmp_path):
    assert main(["report", "--dry-run", "--stato", str(tmp_path / "x.json")]) == 0
    out = capsys.readouterr().out
    assert "[REPORT] Monitor PS5" in out and "Stato delle fonti" in out


def test_config_errata(tmp_path, capsys):
    bad = tmp_path / "c.yaml"
    bad.write_text(open("config.yaml", encoding="utf-8").read().replace("prezzo_max_eur: 700", "prezzo_max_eur: tanti"))
    with pytest.raises(SystemExit):
        main(["run", "--once", "--dry-run", "--config", str(bad)])
    assert "la chiave 'prezzo_max_eur' ha valore 'tanti'" in capsys.readouterr().out
