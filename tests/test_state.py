"""Stato persistente (R4.1, R6.3) e pubblicazione sul branch "stato"."""
import json
import subprocess
from datetime import timedelta
from decimal import Decimal as D

from conftest import T0, make_offer

from ps5monitor.publish import publish_state
from ps5monitor.state import MAX_BYTES, State


def test_salva_e_ricarica(tmp_path):
    st = State()
    o = make_offer()
    st.upsert(o, D("499.00"), False, 3, T0)
    p = tmp_path / "state.json"
    st.save(p)
    st2 = State.load(p)
    assert st2.record(o.key)["totale"] == "499.00"
    assert st2.offer_of(o.key).prezzo == D("499.00")


def test_file_vuoto_o_corrotto(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("{}")
    assert State.load(p).is_new
    p.write_text("non è json")
    assert State.load(p).is_new
    assert State.load(tmp_path / "manca.json").is_new


def test_osservazioni_storico():
    st = State()
    o = make_offer()
    st.upsert(o, D("499.00"), False, 3, T0)
    st.upsert(o, D("499.00"), False, 3, T0 + timedelta(hours=1))       # stesso prezzo, < 6 ore: no
    st.upsert(o, D("489.00"), False, 3, T0 + timedelta(hours=2))       # prezzo cambiato: sì
    st.upsert(o, D("489.00"), False, 3, T0 + timedelta(hours=8, minutes=1))  # 6 ore passate: sì
    assert len(st.record(o.key)["storico"]) == 3


def test_mediana_storica_usata_dopo_5_osservazioni():
    st = State()
    for d in range(6):
        o = make_offer(oid=f"x{d}")
        st.upsert(o, D("500.00") + d, False, 3, T0 - timedelta(days=d + 1))
    assert st.median_for("negozio_test", "standard_disc", "nuovo", T0) == D("502.50")
    assert st.median_for("negozio_test", "digital", "nuovo", T0) is None


def test_pubblica_solo_se_cambia():
    st = State()
    assert st.needs_publish(T0)
    st.mark_published()
    st.vol["cicli"] = 99                    # dato volatile: nessuna pubblicazione
    assert not st.needs_publish(T0 + timedelta(minutes=5))
    assert st.needs_publish(T0 + timedelta(hours=1))   # battito orario
    st.mark_published()
    st.upsert(make_offer(), D("499.00"), False, 3, T0 + timedelta(hours=1))
    assert st.needs_publish(T0 + timedelta(hours=1, minutes=1))


def test_potatura_30_giorni_e_1mb():
    st = State()
    o = make_offer()
    st.upsert(o, D("499.00"), False, 3, T0 - timedelta(days=40))
    rec = st.record(o.key)
    rec["storico"] = [[(T0 - timedelta(days=40)).isoformat(), "499.00"], [T0.isoformat(), "480.00"]]
    st.vol["visto"][o.key] = T0.isoformat()
    st.prune(T0)
    assert rec["storico"] == [[T0.isoformat(), "480.00"]]      # più vecchie di 30 giorni: rimosse
    for i in range(3000):
        k = f"riempitivo:{i}"
        st.offers[k] = {"fonte": "negozio_test", "storico": [[T0.isoformat(), "1" * 3]] * 30, "primo_visto": T0.isoformat()}
    st.prune(T0)
    assert len(st.dumps().encode()) <= MAX_BYTES


def test_offerta_vecchia_rimossa():
    st = State()
    o = make_offer()
    st.upsert(o, D("499.00"), False, 3, T0 - timedelta(days=31))
    st.vol["visto"][o.key] = (T0 - timedelta(days=31)).isoformat()
    st.prune(T0)
    assert st.record(o.key) is None


def test_publish_su_branch_orfano(tmp_path):
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=work, check=True)
    (work / "state.json").write_text(json.dumps({"a": 1}))
    assert publish_state(str(work / "state.json"), cwd=work)
    (work / "state.json").write_text(json.dumps({"a": 2}))
    assert publish_state(str(work / "state.json"), cwd=work)
    log = subprocess.run(["git", "log", "--format=%H", "stato"], cwd=remote, capture_output=True, text=True).stdout.split()
    assert len(log) == 1                         # un solo commit sovrascritto
    content = subprocess.run(["git", "show", "stato:state.json"], cwd=remote, capture_output=True, text=True).stdout
    assert json.loads(content) == {"a": 2}


def test_publish_fallisce_dopo_3_tentativi(tmp_path):
    work = tmp_path / "w"
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    (work / "state.json").write_text("{}")
    sleeps = []
    assert not publish_state(str(work / "state.json"), cwd=work, sleeper=sleeps.append)
    assert sleeps == [2, 4]
