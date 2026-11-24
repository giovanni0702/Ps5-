"""Richieste HTTP rispettose dei siti (G4, R6.9) e lettura da fixture.

- al massimo 1 richiesta ogni `intervallo_dominio_secondi` per dominio, con variazione casuale
  solo in aumento (0..+10 s);
- timeout 15 s;
- nessun login, captcha, proxy o rotazione di IP: un blocco viene solo riconosciuto e segnalato.
"""
from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import requests

TIMEOUT_S = 15
JITTER_MAX_S = 10.0
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/130.0 Safari/537.36")
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9",
}

# Segni di una pagina di verifica/captcha. Il monitor non prova mai a superarla.
BLOCK_MARKERS = (
    "/errors/validatecaptcha", "inserisci i caratteri che vedi", "type the characters you see",
    "robot check", "sei un robot", "are you a robot", "verify you are a human", "verifica di essere un umano",
    "captcha-delivery.com", "px-captcha", "<title>just a moment...</title>", "cf-chl-widget",
    "access denied</title>", "attention required! | cloudflare", "pardon our interruption",
)


class FetchError(Exception):
    """Errore di rete o risposta non valida."""
    kind = "errore"


class BlockedError(FetchError):
    """Il sito ha bloccato la richiesta (403, 429, captcha)."""
    kind = "bloccata"


class BudgetExceeded(Exception):
    """Non c'è tempo nel ciclo per un'altra richiesta a questo dominio."""


@dataclass
class Response:
    url: str
    status: int
    text: str
    ms: int


def domain_of(url: str) -> str:
    return urlsplit(url).netloc.lower()


def detect_block(status: int, text: str) -> str | None:
    if status in (403, 429):
        return f"HTTP {status}"
    low = text[:200_000].lower()
    for marker in BLOCK_MARKERS:
        if marker in low:
            return f"pagina di verifica ('{marker}')"
    return None


class DomainScheduler:
    """Una coda per dominio: tra due richieste almeno `interval` secondi più una variazione 0..+10 s."""

    def __init__(self, interval: float, jitter_max: float = JITTER_MAX_S, last: dict[str, float] | None = None,
                 clock=time.time, sleeper=time.sleep, rng: random.Random | None = None):
        self.interval = float(interval)
        self.jitter_max = jitter_max
        self.last: dict[str, float] = dict(last or {})
        self.clock = clock
        self.sleeper = sleeper
        self.rng = rng or random.Random()
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock(self, domain: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(domain, threading.Lock())

    def acquire(self, domain: str, deadline: float | None = None) -> float:
        """Attende il proprio turno; restituisce i secondi attesi. BudgetExceeded se oltre la scadenza."""
        with self._lock(domain):
            now = self.clock()
            prev = self.last.get(domain)
            wait = 0.0
            if prev is not None:
                wait = max(0.0, prev + self.interval + self.rng.uniform(0, self.jitter_max) - now)
            if deadline is not None and now + wait + TIMEOUT_S > deadline:
                raise BudgetExceeded(domain)
            if wait > 0:
                self.sleeper(wait)
            self.last[domain] = self.clock()
            return wait


class HttpFetcher:
    def __init__(self, scheduler: DomainScheduler, session: requests.Session | None = None):
        self.scheduler = scheduler
        self.session = session or requests.Session()
        self.session.headers.update(HEADERS)

    def get(self, url: str, deadline: float | None = None) -> Response:
        self.scheduler.acquire(domain_of(url), deadline)
        t0 = time.monotonic()
        try:
            r = self.session.get(url, timeout=TIMEOUT_S, allow_redirects=True)
        except requests.RequestException as exc:
            raise FetchError(f"errore di rete: {type(exc).__name__}") from None
        ms = int((time.monotonic() - t0) * 1000)
        text = r.text or ""
        block = detect_block(r.status_code, text)
        if block:
            raise BlockedError(block)
        if r.status_code >= 400:
            raise FetchError(f"HTTP {r.status_code}")
        return Response(r.url, r.status_code, text, ms)


class FixtureFetcher:
    """Legge le pagine da tests/fixtures (nessun accesso alla rete)."""

    def __init__(self, mapping: dict[str, str | Path], base: Path):
        self.mapping = {k: Path(base) / v for k, v in mapping.items()}
        self.requests: list[str] = []

    def get(self, url: str, deadline: float | None = None) -> Response:
        self.requests.append(url)
        path = self.mapping.get(url)
        if path is None or not path.exists():
            raise FetchError("HTTP 404 (nessuna fixture)")
        text = path.read_text(encoding="utf-8")
        block = detect_block(200, text)
        if block:
            raise BlockedError(block)
        return Response(url, 200, text, 1)
