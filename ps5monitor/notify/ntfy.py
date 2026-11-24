"""Canale ntfy: notifica push sul telefono con l'app ntfy, senza account (R10.1).

Pubblica con una POST in JSON all'indirizzo base del server: nessun testo viaggia negli header HTTP.
"""
from __future__ import annotations

import requests

LIMIT_BYTES = 4096


def _bytes(s: str) -> int:
    return len(s.encode("utf-8"))


class NtfyChannel:
    name = "ntfy"
    required = ("NTFY_TOPIC",)

    def __init__(self, cfg, env, session=None):
        self.server = cfg.ntfy_server
        self.env = env
        self.session = session or requests.Session()

    def payloads(self, msg) -> list[dict]:
        from . import split_message
        out = []
        for title, text in split_message(msg, LIMIT_BYTES, _bytes):
            p = {"topic": self.env.get("NTFY_TOPIC", ""), "title": title, "message": text,
                 "priority": msg.priority, "tags": list(msg.tags)}
            if msg.click:
                p["click"] = msg.click
            out.append(p)
        return out

    def send(self, msg) -> None:
        for p in self.payloads(msg):
            r = self.session.post(self.server, json=p, timeout=15)
            if r.status_code >= 300:
                raise RuntimeError(f"ntfy ha risposto HTTP {r.status_code}")
