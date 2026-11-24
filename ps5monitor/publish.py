"""Pubblicazione di state.json sul branch orfano "stato" (R6.3).

Ogni pubblicazione crea un commit senza genitori (sovrascritto) e lo invia con push forzato:
il branch contiene sempre un solo commit con un solo file. 3 tentativi.
"""
from __future__ import annotations

import os
import subprocess
import time

BRANCH = "stato"
AUTHOR = {"GIT_AUTHOR_NAME": "ps5-monitor", "GIT_AUTHOR_EMAIL": "ps5-monitor@localhost",
          "GIT_COMMITTER_NAME": "ps5-monitor", "GIT_COMMITTER_EMAIL": "ps5-monitor@localhost"}


def _git(args, input_text=None, cwd=None):
    env = dict(os.environ, **AUTHOR)
    r = subprocess.run(["git", *args], input=input_text, capture_output=True, text=True, cwd=cwd, env=env, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"git {args[0]} non riuscito")
    return r.stdout.strip()


def publish_state(path: str, remote: str = "origin", attempts: int = 3, cwd=None, sleeper=time.sleep) -> bool:
    for i in range(attempts):
        try:
            blob = _git(["hash-object", "-w", path], cwd=cwd)
            tree = _git(["mktree"], input_text=f"100644 blob {blob}\tstate.json\n", cwd=cwd)
            commit = _git(["commit-tree", tree, "-m", "Aggiorna lo stato del monitor"], cwd=cwd)
            _git(["push", "--force", "--quiet", remote, f"{commit}:refs/heads/{BRANCH}"], cwd=cwd)
            return True
        except Exception:
            if i < attempts - 1:
                sleeper(2 * (i + 1))
    return False
