"""Struttura dei workflow (R6.1, R10.3, R11.4) e yamllint (R6.8)."""
import shutil
import subprocess
import sys

import pytest
import yaml

WF = ".github/workflows/"


def load(name):
    with open(WF + name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_monitor_yml():
    wf = load("monitor.yml")
    on = wf["on"]
    assert on["schedule"] == [{"cron": "*/5 * * * *"}]
    assert on["workflow_dispatch"]["inputs"]["diagnostica"] == {
        "description": on["workflow_dispatch"]["inputs"]["diagnostica"]["description"], "type": "boolean", "default": False}
    assert wf["concurrency"] == {"group": "monitor", "cancel-in-progress": False}
    assert wf["permissions"] == {"contents": "write"}
    job = wf["jobs"]["monitor"]
    assert job["timeout-minutes"] == 7
    steps = job["steps"]
    py = next(s for s in steps if s.get("uses", "").startswith("actions/setup-python"))
    assert py["with"] == {"python-version": "3.12", "cache": "pip"}
    runs = [s.get("run", "") for s in steps]
    assert "python -m ps5monitor run" in runs and "python -m ps5monitor diagnostica" in runs


def test_altri_workflow():
    t = load("test.yml")
    assert "push" in t["on"] and "pull_request" in t["on"]
    n = load("test-notifica.yml")
    assert "workflow_dispatch" in n["on"]
    assert any(s.get("run") == "python -m ps5monitor prova-notifica" for s in n["jobs"]["prova"]["steps"])


def test_yamllint():
    exe = shutil.which("yamllint") or (shutil.which("yamllint", path=sys.prefix + "/bin"))
    if not exe:
        pytest.skip("yamllint non installato (è in requirements.txt)")
    r = subprocess.run([exe, ".github/workflows", "config.yaml", "data/negozi.yaml", "tests/fixtures/fixtures.yaml"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
