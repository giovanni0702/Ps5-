"""Modalità --fixture: le fonti leggono le pagine salvate in tests/fixtures invece della rete."""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

from .config import SourceConfig
from .http import FixtureFetcher

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def fixture_setup(cfg, base: Path = FIXTURE_DIR):
    """Restituisce (config modificata, fetcher): solo le fonti con fixture restano abilitate."""
    spec = yaml.safe_load((base / "fixtures.yaml").read_text(encoding="utf-8")) or {}
    fonti = spec.get("fonti") or {}
    cfg = copy.deepcopy(cfg)
    mapping: dict[str, str] = {}
    for sid in list(cfg.fonti):
        sc = cfg.fonti[sid]
        f = fonti.get(sid)
        if not f:
            cfg.fonti[sid] = SourceConfig(False, [], sc.ricerca, sc.ricerca_ogni_cicli)
            continue
        url = sc.ricerca or f"https://fixture.invalid/{sid}/ricerca"
        cfg.fonti[sid] = SourceConfig(True, [], url, sc.ricerca_ogni_cicli)
        mapping[url] = f["ricerca"]
        for page_url, file in (f.get("pagine") or {}).items():
            mapping[page_url] = file
    return cfg, FixtureFetcher(mapping, base)
