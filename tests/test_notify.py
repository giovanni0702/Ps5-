"""Canali di notifica con richieste simulate (R10.8)."""
from datetime import datetime, timezone


from ps5monitor.messages import Message, prova_message
from ps5monitor.notify import Notifier, mask
from ps5monitor.notify.email import EmailChannel

TOPIC = "topic-di-prova-abcdefghijkl"   # valore finto, solo per i test
ENV = {"NTFY_TOPIC": TOPIC, "TELEGRAM_BOT_TOKEN": "123:finto", "TELEGRAM_CHAT_ID": "4242",
       "SMTP_HOST": "smtp.test", "SMTP_PORT": "587", "SMTP_USER": "mittente", "SMTP_PASSWORD": "pw-finta",
       "EMAIL_TO": "destinatario"}


class Resp:
    def __init__(self, code):
        self.status_code = code


class FakeSession:
    def __init__(self, codes=None):
        self.calls = []
        self.codes = list(codes or [])
        self.headers = {}

    def post(self, url, json=None, timeout=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return Resp(self.codes.pop(0) if self.codes else 200)


def msg(**kw):
    base = dict(kind="sconto", title="[SCONTO -14,7%] PS5 Digital a 469,00 € su Amazon.it",
                blocks=["Riga con € e …"], priority=5, click="https://www.amazon.it/dp/B0TEST0001",
                tags=["rotating_light"])
    base.update(kw)
    return Message(**base)


def notifier(cfg, channels, session=None, sleeps=None, env=ENV):
    cfg.canali = channels
    return Notifier(cfg, env=env, session=session, sleeper=(sleeps.append if sleeps is not None else lambda s: None))


def test_ntfy_json(cfg):
    s = FakeSession()
    res = notifier(cfg, ["ntfy"], s).send(msg())
    assert res == {"ntfy": (True, "inviato")}
    call = s.calls[0]
    assert call["url"] == "https://ntfy.sh" and call["headers"] is None   # nessun testo negli header
    j = call["json"]
    assert j["topic"] == TOPIC and j["title"].startswith("[SCONTO") and j["priority"] == 5
    assert j["click"] == "https://www.amazon.it/dp/B0TEST0001" and "€ e …" in j["message"]
    assert j["tags"] == ["rotating_light"]


def test_telegram(cfg):
    s = FakeSession()
    notifier(cfg, ["telegram"], s).send(msg())
    call = s.calls[0]
    assert call["url"].endswith("/sendMessage") and call["json"]["chat_id"] == "4242"
    assert call["json"]["text"].startswith("[SCONTO -14,7%]") and "https://www.amazon.it/dp/" not in call["json"]["text"][:60]
    assert call["json"]["disable_notification"] is False


class FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        self.tls = True

    def login(self, u, p):
        assert (u, p) == ("mittente", "pw-finta")

    def send_message(self, m):
        FakeSMTP.sent.append(m)


def test_email(cfg):
    ch = EmailChannel(cfg, ENV, smtp_factory=FakeSMTP)
    ch.send(msg())
    m = FakeSMTP.sent[-1]
    assert m["To"] == "destinatario" and m["Subject"].startswith("[SCONTO")
    assert "https://www.amazon.it/dp/B0TEST0001" in m.get_content()


def test_tre_tentativi_poi_successo(cfg):
    s = FakeSession([500, 500, 500, 200])
    sleeps = []
    res = notifier(cfg, ["ntfy"], s, sleeps).send(msg())
    assert res["ntfy"][0] is True and len(s.calls) == 4 and sleeps == [2, 4, 8]


def test_fallimento_dopo_tre_tentativi(cfg):
    s = FakeSession([500] * 10)
    sleeps = []
    res = notifier(cfg, ["ntfy"], s, sleeps).send(msg())
    assert res["ntfy"][0] is False and "HTTP 500" in res["ntfy"][1]
    assert len(s.calls) == 4 and sleeps == [2, 4, 8]


def test_tutti_i_canali_falliti_avviso_conservato(cfg, clock):
    from conftest import T0, make_offer
    from ps5monitor.runner import Monitor
    from ps5monitor.state import State
    from conftest import FakeSource
    s = FakeSession([500] * 100)
    n = notifier(cfg, ["ntfy", "telegram"], s)
    st = State()
    st.data.update(avviato=True, ultimo_report="2026-11-24", avviato_il=T0.isoformat())
    mon = Monitor(cfg, st, [FakeSource(cfg, [make_offer()])], n, now=clock, out=lambda x: None)
    mon.cycle()
    pend = st.data["non_consegnati"]
    assert len(pend) == 1 and sorted(pend[0]["canali"]) == ["ntfy", "telegram"]
    s.codes = []  # da ora tutto ok
    clock.advance(minutes=1)
    mon.cycle()
    assert st.data["non_consegnati"] == []


def test_ritentativo_solo_sul_canale_fallito(cfg):
    s = FakeSession()
    n = notifier(cfg, ["ntfy", "telegram"], s)
    n.send(msg(), only=["telegram"])
    assert len(s.calls) == 1 and "telegram" in s.calls[0]["url"]


def test_secret_mancante(cfg):
    res = notifier(cfg, ["ntfy"], FakeSession(), env={}).send(msg())
    assert res["ntfy"] == (False, "manca il secret NTFY_TOPIC")


def test_mascheramento():
    assert mask(f"errore con {TOPIC} e 123:finto", ENV) == "errore con *** e ***"


def test_errore_telegram_non_espone_token(cfg):
    import requests

    class Boom(FakeSession):
        def post(self, url, **kw):
            raise requests.ConnectionError(f"impossibile raggiungere {url}")

    res = notifier(cfg, ["telegram"], Boom()).send(msg())
    assert res["telegram"][0] is False and "123:finto" not in res["telegram"][1]


def test_dry_run_stampa(cfg):
    out = []
    cfg.canali = ["ntfy"]
    n = Notifier(cfg, env={}, dry_run=True, out=out.append)
    res = n.send(prova_message(datetime(2026, 11, 24, tzinfo=timezone.utc)))
    assert res["ntfy"][0] and "[PROVA]" in out[0]


def test_messaggio_lungo_diviso_ntfy(cfg):
    s = FakeSession()
    big = msg(blocks=[("riga lunga € " * 40) for _ in range(20)])
    notifier(cfg, ["ntfy"], s).send(big)
    assert len(s.calls) >= 2
    assert all(len(c["json"]["message"].encode()) <= 4096 for c in s.calls)
