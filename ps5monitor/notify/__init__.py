"""Invio delle notifiche su tutti i canali attivi, con tentativi e mascheramento dei secret (R10)."""
from __future__ import annotations

import os
import time
from typing import Callable

from ..messages import Message
from .email import EmailChannel
from .ntfy import NtfyChannel
from .telegram import TelegramChannel

RETRY_WAITS = (2, 4, 8)   # R10.4: primo invio più 3 tentativi, con attese di 2, 4 e 8 secondi
SECRET_NAMES = ("NTFY_TOPIC", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SMTP_HOST", "SMTP_PORT",
                "SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO")
CHANNELS = {"ntfy": NtfyChannel, "telegram": TelegramChannel, "email": EmailChannel}


class ChannelError(Exception):
    """Errore di un canale, con motivo in italiano e senza valori dei secret."""


def mask(text: str, env=None) -> str:
    """Sostituisce con *** ogni valore preso dai secret (G3)."""
    env = os.environ if env is None else env
    out = str(text)
    for name in SECRET_NAMES:
        val = env.get(name)
        if val and len(val) >= 3:
            out = out.replace(val, "***")
    return out


def split_message(msg: Message, limit: int, measure: Callable[[str], int]) -> list[tuple[str, str]]:
    """Divide un messaggio troppo lungo in più parti, mantenendo l'ordine dei blocchi (R5.7)."""
    if measure(msg.text()) <= limit:
        return [(msg.title, msg.text())]
    parts: list[list[str]] = [[]]
    for block in msg.blocks:
        if len(block) and measure(block) > limit - 200:
            block = block[: max(100, limit // 2)] + "…"
        candidate = parts[-1] + [block]
        probe = Message(msg.kind, msg.title, candidate, msg.header if len(parts) == 1 else "", msg.footer)
        if parts[-1] and measure(probe.text()) > limit:
            parts.append([block])
        else:
            parts[-1] = candidate
    n = len(parts)
    out = []
    for i, blocks in enumerate(parts, 1):
        m = Message(msg.kind, msg.title, blocks, msg.header if i == 1 else "", msg.footer if i == n else "")
        out.append((f"{msg.title} ({i}/{n})", m.text()))
    return out


class Notifier:
    def __init__(self, cfg, env=None, session=None, sleeper=time.sleep, dry_run: bool = False,
                 out: Callable[[str], None] = print):
        self.cfg = cfg
        self.env = os.environ if env is None else env
        self.sleeper = sleeper
        self.dry_run = dry_run
        self.out = out
        self.channels = [CHANNELS[name](cfg, self.env, session) for name in cfg.canali]

    def missing(self) -> dict[str, str]:
        """Canali attivi senza i loro secret → messaggio in italiano."""
        out = {}
        for ch in self.channels:
            miss = [s for s in ch.required if not self.env.get(s)]
            if miss:
                out[ch.name] = f"manca il secret {miss[0]}"
        return out

    def send(self, msg: Message, only: list[str] | None = None) -> dict[str, tuple[bool, str]]:
        """Invia su tutti i canali (o solo su `only`). Restituisce {canale: (inviato, motivo)}."""
        results: dict[str, tuple[bool, str]] = {}
        if self.dry_run:
            self.out("=" * 70 + f"\n{msg.title}\n" + "-" * 70 + f"\n{msg.text()}\n")
            return {ch.name: (True, "dry-run: non inviato") for ch in self.channels if not only or ch.name in only}
        missing = self.missing()
        for ch in self.channels:
            if only is not None and ch.name not in only:
                continue
            if ch.name in missing:
                results[ch.name] = (False, missing[ch.name])
                continue
            reason = ""
            for attempt in range(len(RETRY_WAITS) + 1):
                try:
                    ch.send(msg)
                    results[ch.name] = (True, "inviato")
                    break
                except Exception as exc:  # qualsiasi errore del canale: riprova
                    reason = mask(f"{exc}", self.env) or type(exc).__name__
                    if attempt < len(RETRY_WAITS):
                        self.sleeper(RETRY_WAITS[attempt])
            else:
                results[ch.name] = (False, reason)
        return results
