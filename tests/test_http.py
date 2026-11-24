"""Rispetto dei siti: una richiesta ogni 30 s per dominio, variazione solo in aumento, URL ogni 60 s (G4, R6.2, R6.9)."""
import random

import pytest

from ps5monitor.http import BudgetExceeded, DomainScheduler, FetchError, HttpFetcher


class FakeClock:
    def __init__(self):
        self.t = 1000.0
        self.sleeps = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def sched(clock, **kw):
    return DomainScheduler(30, clock=clock, sleeper=clock.sleep, rng=random.Random(1), **kw)


def test_intervallo_per_dominio_con_variazione_solo_in_aumento():
    c = FakeClock()
    s = sched(c)
    s.acquire("a.it")
    for _ in range(20):
        before = c.t
        s.acquire("a.it")
        gap = c.t - before
        assert 30 <= gap <= 40
    assert s.acquire("b.it") == 0        # domini diversi non si aspettano


def test_url_non_prima_di_60_secondi():
    c = FakeClock()
    s = sched(c)
    s.acquire("a.it", url="https://a.it/p")
    t0 = c.t
    s.acquire("a.it", url="https://a.it/p")
    assert c.t - t0 >= 60


def test_scadenza_del_ciclo():
    c = FakeClock()
    s = sched(c)
    s.acquire("a.it")
    with pytest.raises(BudgetExceeded):
        s.acquire("a.it", deadline=c.t + 20)


def test_stato_dei_domini_tra_esecuzioni():
    c = FakeClock()
    s = sched(c, last={"a.it": c.t - 5})
    assert s.acquire("a.it") >= 25


class Resp:
    def __init__(self, code, text="ok"):
        self.status_code, self.text, self.url = code, text, "https://a.it/x"


class Sess:
    def __init__(self, resp):
        self.resp, self.headers, self.kw = resp, {}, None

    def get(self, url, **kw):
        self.kw = kw
        return self.resp


def test_timeout_15_e_blocchi():
    from ps5monitor.http import BlockedError
    c = FakeClock()
    sess = Sess(Resp(200, "<html>ok</html>"))
    f = HttpFetcher(sched(c), sess)
    assert f.get("https://a.it/x").status == 200 and sess.kw["timeout"] == 15
    for code in (403, 429):
        with pytest.raises(BlockedError):
            HttpFetcher(sched(c), Sess(Resp(code))).get("https://a.it/x")
    with pytest.raises(FetchError):
        HttpFetcher(sched(c), Sess(Resp(500))).get("https://a.it/x")
